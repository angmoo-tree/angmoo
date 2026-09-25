"""Frozen attention snapshot, with independent Inbox/Feed selection results."""
from copy import deepcopy
import json

from app.providers.gemini import build_gemini_developer_response_schema
from app.runtime.autonomous_activity.contracts import Candidate, INBOX_TARGET_LIMIT
from app.runtime.autonomous_activity.output_recovery import ActivityRetryGuardError
from app.runtime.autonomous_activity.provider import SELECTOR_INSTRUCTIONS, TargetOutput, candidate_previews
from app.runtime.autonomous_activity.queries import validate_selection


class CombinedSelection:
    def __init__(self, adapters, lanes):
        self.adapters, self.lanes = adapters, lanes

    async def prepare(self, state):
        prepared = {}
        for lane in ("inbox", "feed"):
            port = self.lanes[lane]
            try:
                await port.guard({**state, "stage": "LoadCandidates"})
                prepared[lane] = await port.load_candidates(state)
            except Exception as exc:
                if port.on_error is None:
                    raise
                result = await port.on_error(exc)
                prepared[lane] = {"candidates": [], "preparation_error": result}
        return {"prepared_lanes": prepared}

    def request(self, state):
        choices = {}
        for lane, prepared in state["prepared_lanes"].items():
            candidates = prepared.get("candidates", [])
            if len(candidates) > 1 and not prepared.get("preparation_error"):
                choices[lane] = {"candidates": candidate_previews(candidates),
                    "selection_limit": min(INBOX_TARGET_LIMIT if lane == "inbox" else 1, len(candidates)),
                    "action_preferences": prepared.get("shared_context", {}).get("action_preferences", {})}
        return {"context": state["shared_context"], "lanes": choices}

    async def mode(self, state):
        size = len(json.dumps(self.request(state), ensure_ascii=False, default=str))
        return {"selection_mode": "split" if size > 56000 else "combined"}

    async def select(self, state):
        mode = state.get("selection_mode")
        if mode not in {"combined", "split"}:
            raise ValueError("activity_selection_mode_invalid")
        prepared = deepcopy(state["prepared_lanes"])
        for lane, item in prepared.items():
            candidates = item.get("candidates", [])
            item["selections"] = [{"target_id": candidates[0]["target_id"], "memory_query": None}] if len(candidates) == 1 else []
            if candidates and not item.get("preparation_error"):
                try:
                    await self.lanes[lane].guard({**item, "identity": state["identity"],
                        "shared_context": item.get("shared_context", state["shared_context"]), "stage": "TargetSelector"})
                except Exception as exc:
                    item["preparation_error"] = await self.lanes[lane].on_error(exc)
        request = self.request({**state, "prepared_lanes": prepared})
        needed = request["lanes"]
        if len(needed) < 2 or mode == "split":
            for lane in needed:
                try:
                    item = prepared[lane]
                    selected = await self.adapters[lane].select({**item, "identity": state["identity"],
                        "shared_context": item.get("shared_context", state["shared_context"])})
                    item.update(selected)
                except Exception as exc:
                    if isinstance(exc, ActivityRetryGuardError):
                        exc = exc.original
                    prepared[lane]["preparation_error"] = await self.lanes[lane].on_error(exc)
            return {"prepared_lanes": prepared}
        properties = {}
        for lane, details in needed.items():
            schema = build_gemini_developer_response_schema(TargetOutput)
            schema["properties"]["selections"]["maxItems"] = details["selection_limit"]
            fields = schema["properties"]["selections"]["items"]["properties"]
            fields["target_id"]["enum"] = [c["target_id"] for c in details["candidates"]]
            fields["memory_query"].pop("maxLength", None)
            properties[lane] = schema
        def validate(value):
            result = {}
            for lane, details in needed.items():
                try:
                    if not isinstance(value, dict) or lane not in value:
                        raise ValueError("selection_lane_missing")
                    selected = validate_selection(value[lane],
                        [Candidate.model_validate(c) for c in prepared[lane]["candidates"]], details["selection_limit"])
                    result[lane] = {"selections": [s.model_dump() for s in selected]}
                except ValueError:
                    result[lane] = {"preparation_error": {"path": lane, "status": "failed",
                        "reason": "selection_invalid", "public_action_count": 0}}
            return result
        async def guard_retry(_attempt):
            try:
                for lane in needed:
                    await self.lanes[lane].guard({**prepared[lane], "identity": state["identity"],
                        "shared_context": prepared[lane].get("shared_context", state["shared_context"]),
                        "stage": "TargetSelector"})
            except Exception as exc:
                raise ActivityRetryGuardError(exc) from exc
        feed = prepared["feed"]
        delivery = self.adapters["feed"].delivery({**feed, "identity": state["identity"]})
        try:
            result = await self.adapters["inbox"].provider.call(
                node="CombinedTargetSelector", lane="inbox_feed_selector", system=SELECTOR_INSTRUCTIONS +
                    "\nSelect Inbox and Feed independently from their own lists, using the same start-of-activity context. "
                    "Return both lane keys. Never transfer target IDs or queries between lanes.",
                payload=request, schema={"type": "object", "properties": properties,
                    "required": list(properties)},
                validator=validate, max_tokens=4096, recover_truncation=True,
                before_json_retry=guard_retry, delivery=delivery)
            for lane in needed:
                prepared[lane].update(result[lane])
        except Exception as exc:
            if isinstance(exc, ActivityRetryGuardError):
                exc = exc.original
            for lane in needed:
                prepared[lane]["preparation_error"] = await self.lanes[lane].on_error(exc)
        return {"prepared_lanes": prepared}
