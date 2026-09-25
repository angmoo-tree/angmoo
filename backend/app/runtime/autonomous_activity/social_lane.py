"""Shared selected-target stages; domain adapters own candidate and completion rules."""
from dataclasses import asdict
from datetime import UTC, datetime
import json

from app.contracts.activity_thought import parse_activity_thought
from app.domains.social.models.posts import Post
from app.domains.world_characters.schemas.activity_state import StateUpdate
from app.domains.world_characters.service.activity_state import settle_state
from app.runtime.autonomous_activity.contracts import INBOX_TARGET_LIMIT, identity_key
from app.runtime.autonomous_activity.graph import LanePorts
from app.runtime.autonomous_activity.inputs import relationship_snapshot
from app.runtime.autonomous_activity.provider import ActivityProvider
from app.runtime.autonomous_activity.output_recovery import ActivityRetryGuardError
from app.runtime.autonomous_activity.recall import SelectedRecall, context_memories, split_validation
from app.runtime.relationships.experience_metrics import apply_pending_metrics, post_revision
from app.runtime.relationships.social_metrics import prepare_sources, stage_sources, source_prompt


def plain(value):
    return json.loads(json.dumps(value, ensure_ascii=False, default=str))


class SocialLane:
    def __init__(self, ctx, *, actor, lane, tracker, hybrid_service, guard, action_executor=None):
        self.ctx, self.actor, self.lane, self.tracker = ctx, actor, lane, tracker
        self.provider = ActivityProvider(ctx, tracker)
        self.retriever = SelectedRecall(hybrid_service, owner_id=ctx.user_id, world_id=actor.world_id, actor_id=actor.id)
        self.scope_guard = guard
        self.action_executor = action_executor

    def ports(self):
        return LanePorts(self.load, self.select, self.recall, self.context, self.plan,
            self.validate, self.write, self.execute, self.settle, self.finalize, self.guard)

    async def guard(self, state):
        await self.scope_guard(state)
        # Committed effects can change affordances, so do not recheck old target
        # snapshots after Execute. Settlement validates its own source receipts.
        if state.get("stage") in {"TargetSelector", "BuildDecisionContext", "ActionPlanner", "ValidateDecision", "Writer", "Execute"}:
            selected = {s["target_id"] for s in state.get("selections", [])}
            for candidate in state.get("candidates", []):
                if selected and candidate["target_id"] not in selected:
                    continue
                current_relation = self.relationship(candidate.get("counterpart_id"))
                previous_relation = candidate.get("relationship", {})
                if any(current_relation.get(k) != previous_relation.get(k) for k in ("content_hash", "status")):
                    raise ValueError("activity_relationship_changed")
                for identifier, revision in candidate["source_revisions"].items():
                    post = self.ctx.db.get(Post, identifier, populate_existing=True)
                    if post is None or post.world_id != self.actor.world_id or post.deleted_at or post.report_hidden_at or post.visibility != "public" or post_revision(post) != revision:
                        raise ValueError("activity_source_changed")
        return {}

    def selected(self, state):
        ids = {s["target_id"] for s in state.get("selections", [])}
        return [c for c in state["candidates"] if c["target_id"] in ids]

    async def select(self, state):
        async def before_retry(_attempt):
            try:
                await self.guard({**state, "stage": "TargetSelector"})
            except Exception as exc:
                raise ActivityRetryGuardError(exc) from exc
        return await self.provider.select(lane=self.lane, context=state["shared_context"],
            candidates=state["candidates"], limit=INBOX_TARGET_LIMIT if self.lane == "inbox" else 1,
            delivery=self.delivery(state), before_json_retry=before_retry)

    def delivery(self, state):
        return None

    async def recall(self, state):
        return split_validation(await self.retriever.selected(activity_id=state["identity"]["activity_id"],
            targets=self.selected(state), queries=state["queries"]))

    async def context(self, state):
        refreshed = {}
        if any(value.get("packets") and target not in state.get("memory_validations", {})
               for target, value in state.get("memories", {}).items()):
            # Pre-Planner legacy checkpoint: return rebuilt evidence as real
            # State channels, rather than mutating the guard's input dict.
            refreshed = split_validation(await self.retriever.selected(
                activity_id=state["identity"]["activity_id"],
                targets=self.selected(state), queries=state["queries"]))
        candidates = self.selected(state)
        manifest = prepare_sources(self.ctx.db, actor=self.actor,
            post_ids=[ref for c in candidates for ref in c["source_ids"]])
        return {**refreshed, "decision_context": plain({**state["shared_context"],
            "memories": context_memories(refreshed.get("memories", state["memories"])),
            "metric_sources": source_prompt(manifest), "source_manifest": manifest})}

    async def plan(self, state):
        receipt = {}
        async def before_retry(_attempt):
            try:
                await self.guard({**state, "stage": "ActionPlanner"})
            except Exception as exc:
                raise ActivityRetryGuardError(exc) from exc
        decision = await self.provider.plan(lane=self.lane, context=state["decision_context"],
            candidates=self.selected(state), delivery=self.delivery(state),
            on_input_receipt=receipt.update, before_json_retry=before_retry)
        return {"decision": decision, "decision_input_receipt": receipt}

    async def validate(self, state):
        from app.domains.routines.policies.writer_tasks import _reply_task_id
        from functools import partial
        _reply_task_id = partial(_reply_task_id, clip=lambda value, limit: str(value or "")[:limit])
        candidates = {c["target_id"]: c for c in self.selected(state)}
        assignments = []
        for index, decision in enumerate(state["decision"]["decisions"]):
            if decision["action"] != "comment":
                continue
            post_id = state["lane_data"][decision["target_id"]]["post_id"]
            assignments.append({"task_id": _reply_task_id(scope=self.lane, index=index, post_id=post_id),
                "target_post_id": post_id, "scope": self.lane, "action_index": index,
                "brief": decision["brief"], "interaction_intent": decision["interaction_intent"],
                "comment_purpose": decision["comment_purpose"], "source": candidates[decision["target_id"]],
                "thought": decision.get("thought"), "proposal_response": decision.get("proposal_response"), "proposal": decision.get("proposal")})
        return {"assignments": assignments}

    async def write(self, state):
        # Reuse proposal-capable Writer output and canonical writer validation.
        receipts = []
        writing = await self.provider.write(lane=self.lane, context=state["decision_context"],
            assignments=state["assignments"], on_input_receipt=receipts.append)
        return {"drafts": writing.get("reply_task_results", []), "writer_input_receipts": receipts}

    async def execute(self, state):
        if self.action_executor is None and any(d["action"] != "no_action" for d in state["decision"]["decisions"]):
            raise RuntimeError("activity_action_executor_missing")
        results, used = [], {}
        for index, decision in enumerate(state["decision"]["decisions"]):
            if decision["action"] == "no_action":
                results.append({"target_id": decision["target_id"], "status": "no_action"})
                continue
            data = state["lane_data"][decision["target_id"]]
            from sqlalchemy import select
            from app.domains.routines.models import AgentPublicActionExecution
            action_type = "reply" if decision["action"] == "comment" else decision["action"]
            previous = self.ctx.db.scalar(select(AgentPublicActionExecution).where(
                AgentPublicActionExecution.run_id == self.ctx.run_id,
                AgentPublicActionExecution.scope == self.lane,
                AgentPublicActionExecution.action_type == action_type,
                AgentPublicActionExecution.target_post_id == data["post_id"],
                AgentPublicActionExecution.status == "succeeded"))
            if previous is not None:
                results.append({"target_id": decision["target_id"], "status": "reused", "execution_id": previous.id})
                continue
            action = {"action_type": "reply" if decision["action"] == "comment" else decision["action"],
                "post_id": data["post_id"], "notification_id": data.get("notification_id"),
                "interaction_intent": decision.get("interaction_intent"), "comment_purpose": decision.get("comment_purpose"),
                "brief": decision["brief"], "_activity_thought": asdict(parse_activity_thought(decision.get("thought")))}
            result = self.action_executor(self.ctx, action=action, scope=self.lane, index=index,
                writing={"reply_task_results": state.get("drafts", [])}, used_reply_bodies=used)
            results.append({"target_id": decision["target_id"], **result})
        return {"executions": plain(results)}

    async def settle(self, state):
        decision = state["decision"]
        key = identity_key(state["identity"]["activity_id"], self.lane, "decision")
        # Only explicit final decisions were interpreted; omitted selected Inbox
        # conversations remain pending and receive no inferred relationship delta.
        decided = {d["target_id"] for d in decision["decisions"]}
        valid = {ref for c in self.selected(state) if c["target_id"] in decided for ref in c["source_ids"]}
        manifest = [r for r in state["decision_context"]["source_manifest"] if r["post_id"] in valid]
        revisions = {ref: rev for c in self.selected(state) for ref, rev in c["source_revisions"].items()}
        valid = {ref for ref in valid if (post := self.ctx.db.get(Post, ref, populate_existing=True)) is not None
            and post.world_id == self.actor.world_id and not post.deleted_at and not post.report_hidden_at
            and post.visibility == "public" and post_revision(post) == revisions[ref]}
        manifest = [r for r in manifest if r["post_id"] in valid]
        # Frozen revision is revalidated by RuntimeExperienceReferences.
        manifest = [{**r, "created_at": datetime.fromisoformat(r["created_at"]) if isinstance(r["created_at"], str) else r["created_at"]} for r in manifest]
        now = datetime.fromisoformat(decision["judged_at"])
        from app.runtime.social.observations import observe_source
        for ref in valid:
            post = self.ctx.db.get(Post, ref, populate_existing=True)
            if post and post.world_id == self.actor.world_id and not post.deleted_at and not post.report_hidden_at:
                observe_source(self.ctx.db, world_id=self.actor.world_id, observer_world_character_id=self.actor.id,
                    source_social_event_id=None, source_post_id=ref, lane=self.lane, observed_at=now)
        self.ctx.db.commit()
        stage_sources(self.ctx.db, actor=self.actor, manifest=manifest,
            raw=decision.get("relationship_metrics"), decision_key=key, now=now)
        apply_pending_metrics(self.ctx.db, world_id=self.actor.world_id, actor_id=self.actor.id,
            source_kind="post", decision_key=key, source_keys=valid)
        evidence_keys = {ref: identity_key("post", ref, revisions[ref]) for ref in valid}
        outcome = "invalid"
        if decision["state_status"] != "invalid":
            proposal = StateUpdate.model_validate(decision["state_update"]) if decision["state_update"] else None
            outcome = settle_state(self.ctx.db, world_id=self.actor.world_id, actor_id=self.actor.id,
                activity_id=state["identity"]["activity_id"], decision_key=key,
                expected_version=state["shared_context"]["current_state"]["version"],
                proposal=proposal, judged_at=now, source_keys=[evidence_keys.get(ref, "invalid:" + ref) for ref in decision["state_source_refs"]],
                valid_source_keys=set(evidence_keys.values()), context_reassessment=not decision["state_source_refs"])
            self.ctx.db.commit()
        return {"settlement": {"state": outcome, "decision_key": key}}

    async def finalize(self, state):
        return {"result": {"path": self.lane, "status": "failed" if state.get("failure") else "completed" if state.get("executions") else "no_action",
            "failure": state.get("failure"),
            "public_action_count": sum(r["status"] == "succeeded" for r in state.get("executions", [])),
            "selected_ids": [s["target_id"] for s in state.get("selections", [])],
            "recall_status": {key: item["status"] for key, item in state.get("memories", {}).items()},
            "settlement": state.get("settlement", {})}}

    def relationship(self, counterpart_id):
        snapshot = relationship_snapshot(self.ctx, self.actor, counterpart_id=counterpart_id)
        if snapshot and getattr(self.tracker, "observer", None) is not None:
            try:
                self.tracker._notify("relationship_lookup", {
                    "lane": self.lane, "counterpart_id": counterpart_id,
                    "manifest": snapshot.manifest(),
                    "sources": [item.source for item in snapshot.items],
                })
            except Exception:
                pass  # Diagnostic metadata cannot affect relationship recall.
        return plain(snapshot.prompt_view()) if snapshot else {}
