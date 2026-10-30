"""Shared selected-target stages; domain adapters own candidate and completion rules."""
from dataclasses import asdict
from datetime import UTC, datetime
from hashlib import sha256
import json

from app.contracts.activity_thought import parse_activity_thought
from app.domains.social.models.posts import Post
from app.domains.world_characters.schemas.activity_state import StateUpdate
from app.domains.world_characters.service.activity_state import settle_state
from app.runtime.autonomous_activity.contracts import INBOX_TARGET_LIMIT, identity_key
from app.runtime.autonomous_activity.graph import LanePorts
from app.runtime.autonomous_activity.inputs import prepare_relationship, validate_relationship, ActivityRelationshipValidationError
from app.domains.relationships.contracts.social_context import (
    RelationshipValidationBinding, SocialContextValidationError, read_currentness_policy,
)
from app.runtime.autonomous_activity.provider import ActivityProvider
from app.runtime.autonomous_activity.output_recovery import ActivityRetryGuardError
from app.runtime.autonomous_activity.recall import SelectedRecall, context_memories, split_validation
from app.runtime.relationships.experience_metrics import apply_pending_metrics, post_revision
from app.runtime.relationships.social_metrics import prepare_sources, stage_sources, source_prompt


def plain(value):
    return json.loads(json.dumps(value, ensure_ascii=False, default=str))


class SocialLane:
    def __init__(self, ctx, *, actor, lane, tracker, hybrid_service, guard,
                 claim_validator=None, action_executor=None):
        self.ctx, self.actor, self.lane, self.tracker = ctx, actor, lane, tracker
        self.provider = ActivityProvider(ctx, tracker)
        self.retriever = SelectedRecall(hybrid_service, owner_id=ctx.user_id, world_id=actor.world_id, actor_id=actor.id)
        self.scope_guard = guard
        self.claim_validator = claim_validator
        self.action_executor = action_executor

    def ports(self):
        return LanePorts(self.load, self.select, self.recall, self.context, self.plan,
            self.validate, self.write, self.execute, self.settle, self.finalize, self.guard,
            prepare_recall=self.prepare_recall, resume=self.resume)

    async def resume(self, state):
        from app.runtime.autonomous_activity.committed_resume import resume
        return await resume(self, state, self.lane)

    async def guard(self, state):
        await self.scope_guard({**state, "_lane": self.lane})
        from app.runtime.autonomous_activity.db_stage import run_db_stage
        await run_db_stage(self, '_guard_selected_sync', state)
        return {}

    def _guard_selected_sync(self, state):
        from app.contracts.read_deadline import bounded_read
        with bounded_read(2.0):
            self.guard_selected_inputs(state)

    def guard_selected_inputs(self, state):
        from app.runtime.autonomous_activity.initial_input import assert_integrity
        assert_integrity(state)
        # Committed effects can change affordances, so do not recheck old target
        # snapshots after Execute. Settlement validates its own source receipts.
        if state.get("stage") in {"TargetSelector", "PrepareImageRecall", "RecallSelected", "BuildDecisionContext", "ActionPlanner", "DecisionDraft", "ValidateDecision", "Writer", "ValidateDraft", "Execute"}:
            selected = {s["target_id"] for s in state.get("selections", [])}
            candidates = [candidate for candidate in state.get("candidates", [])
                if (not selected or candidate["target_id"] in selected) and not self.completed_action(state, candidate["target_id"])]
            self.validate_relationship_candidates(state, candidates)
            for candidate in candidates:
                from app.runtime.media.social_context import assert_current
                frozen_images = state.get("image_recall_snapshots", {}).get(candidate["target_id"], {}).get("images", candidate.get("images", []))
                assert_current(self.ctx.db, self.ctx.user_id, frozen_images)
                self.validate_action_target(state, candidate)

    def validate_action_target(self, state, candidate):
        # Historical conversation excerpts need no live content comparison.
        # The concrete public-action target must still exist and be visible.
        from sqlalchemy import select
        identifier = state.get("lane_data", {}).get(candidate["target_id"], {}).get("post_id")
        post = self.ctx.db.execute(select(Post.id, Post.world_id, Post.deleted_at,
            Post.report_hidden_at, Post.visibility).where(Post.id == identifier)).one_or_none() if identifier else None
        if (post is None or post.world_id != self.actor.world_id or post.deleted_at
                or post.report_hidden_at or post.visibility != "public"):
            raise ValueError("activity_target_unavailable")

    def validate_relationship_candidates(self, state, candidates):
        if not candidates:
            return
        from app.runtime.autonomous_activity.inputs import validate_relationship_batch
        identity = state.get("identity", {})
        if (identity.get("activity_id", self.ctx.run_id) != self.ctx.run_id
                or identity.get("world_id", self.actor.world_id) != self.actor.world_id
                or identity.get("actor_id", self.actor.id) != self.actor.id):
            raise ActivityRelationshipValidationError("receipt_invalid", lane=self.lane)
        from app.runtime.autonomous_activity.relationship_progress import effects
        requests = [{"effects": effects(self, state, row["target_id"]), "binding": RelationshipValidationBinding(self.ctx.run_id, self.lane, row["target_id"], row.get("counterpart_id")),
            "prompt": row.get("relationship", {}), "receipt": state.get("relationship_validation_receipts", {}).get(row["target_id"]),
            "policy": read_currentness_policy(identity)} for row in candidates]
        try:
            for result in validate_relationship_batch(self.ctx, self.actor, requests):
                self.observe_relationship_validation(result.outcome, result.reason, result.checked_count, result.revision)
        except SocialContextValidationError as exc:
            self.observe_relationship_validation("invalid", exc.reason, 0, read_currentness_policy(identity))
            raise ActivityRelationshipValidationError(exc.reason, lane=self.lane, original=exc) from exc
    def validate_relationship_candidate(self, state, candidate):
        binding = RelationshipValidationBinding(self.ctx.run_id, self.lane,
            candidate["target_id"], candidate.get("counterpart_id"))
        try:
            identity = state.get("identity", {})
            if (identity.get("activity_id", self.ctx.run_id) != self.ctx.run_id
                    or identity.get("world_id", self.actor.world_id) != self.actor.world_id
                    or identity.get("actor_id", self.actor.id) != self.actor.id):
                raise SocialContextValidationError("receipt_invalid")
            from app.runtime.autonomous_activity.relationship_progress import effects
            result = validate_relationship(self.ctx, self.actor, binding=binding, effects=effects(self, state, candidate["target_id"]),
                prompt=candidate.get("relationship", {}),
                receipt=state.get("relationship_validation_receipts", {}).get(candidate["target_id"]),
                policy=read_currentness_policy(identity))
        except SocialContextValidationError as exc:
            self.observe_relationship_validation("invalid", exc.reason, 0,
                (state.get("identity") or {}).get("relationship_validation_policy", "social-context-currentness.legacy.v1"))
            raise ActivityRelationshipValidationError(exc.reason, lane=self.lane, original=exc) from exc
        self.observe_relationship_validation(result.outcome, result.reason, result.checked_count, result.revision)

    def observe_relationship_validation(self, outcome, reason, count, revision):
        tracker = getattr(self, "tracker", None)
        if tracker is not None and getattr(tracker, "observer", None) is not None:
            try:
                tracker._notify("relationship_validation", {"lane": self.lane,
                    "revision": revision, "outcome": outcome, "reason": reason, "checked_count": count})
            except Exception:
                pass

    def relationship_preparation(self, target_id, counterpart_id):
        prompt, receipt, snapshot = prepare_relationship(self.ctx, self.actor,
            binding=RelationshipValidationBinding(self.ctx.run_id, self.lane, target_id, counterpart_id))
        if snapshot and getattr(self.tracker, "observer", None) is not None:
            try:
                self.tracker._notify("relationship_lookup", {
                    "lane": self.lane, "counterpart_id": counterpart_id,
                    "manifest": snapshot.manifest(), "sources": [item.source for item in snapshot.items]})
            except Exception:
                pass
        return plain(prompt), receipt

    def completed_action(self, state, target_id):
        """Use the same durable identity for execution and its replay guard."""
        decision = next((row for row in state.get("decision", {}).get("decisions", [])
                         if row["target_id"] == target_id), None)
        if decision is None or decision["action"] == "no_action":
            return None
        from sqlalchemy import select
        from app.domains.routines.models import AgentPublicActionExecution
        receipt = self.ctx.db.scalar(select(AgentPublicActionExecution).where(
            AgentPublicActionExecution.run_id == self.ctx.run_id,
            AgentPublicActionExecution.character_id == self.ctx.character.id,
            AgentPublicActionExecution.world_id == self.actor.world_id,
            AgentPublicActionExecution.actor_world_character_id == self.actor.id,
            AgentPublicActionExecution.scope == self.lane,
            AgentPublicActionExecution.action_type == ("reply" if decision["action"] == "comment" else decision["action"]),
            AgentPublicActionExecution.target_post_id == state["lane_data"][target_id]["post_id"],
            AgentPublicActionExecution.status == "succeeded"))
        from app.runtime.autonomous_activity.committed_resume import public_receipt_current
        if not public_receipt_current(self, receipt):
            return None
        from app.domains.routines.policies.execution_results import _brief_hash, _action_signature
        body = None
        if decision["action"] == "comment":
            from app.domains.routines.policies.writer_tasks import _reply_task_id
            index = state["decision"]["decisions"].index(decision)
            task = _reply_task_id(scope=self.lane, index=index, post_id=receipt.target_post_id,
                clip=lambda value, limit: str(value or "")[:limit])
            body = next((row["body"] for row in state.get("drafts", []) if row.get("task_id") == task), None)
            if body is None:
                raise ValueError("activity_resume_draft_unproven")
        brief = _brief_hash(body or decision.get("brief"), state["lane_data"][target_id].get("notification_id"))
        signature = _action_signature(run_id=self.ctx.run_id, scope=self.lane, action_type=receipt.action_type,
            target_id=receipt.target_post_id, brief_hash=brief)
        if receipt.brief_hash != brief or receipt.signature != signature:
            raise ValueError("activity_resume_decision_changed")
        return receipt

    def selected(self, state):
        ids = {s["target_id"] for s in state.get("selections", [])}
        return [c for c in state["candidates"] if c["target_id"] in ids]

    async def select(self, state):
        async def before_retry(_attempt):
            try:
                await self.guard({**state, "stage": "TargetSelector"})
            except Exception as exc:
                raise ActivityRetryGuardError(exc) from exc
        from app.core.async_session import session_call
        delivery = await session_call(self.ctx.db, lambda: self.delivery({**state, "stage": "TargetSelector"}))
        return await self.provider.select(lane=self.lane, context=state["shared_context"],
            candidates=state["candidates"], limit=INBOX_TARGET_LIMIT if self.lane == "inbox" else 1,
            delivery=delivery, before_json_retry=before_retry)

    def delivery(self, state):
        return None

    async def prepare_recall(self, state):
        from app.runtime.media.social_context import prepare_selected, freeze_query
        snapshots = dict(state.get("image_recall_snapshots", {}))
        by_id = {candidate["target_id"]: candidate for candidate in self.selected(state)}
        queries = []
        for query in state["queries"]:
            target = query["target_id"]
            if target not in snapshots:
                images = await prepare_selected(self.ctx.db, self.ctx.user_id, by_id[target])
                snapshots[target] = freeze_query(query, images)
            queries.append(snapshots[target]["final_query"])
        await self.guard({**state, "image_recall_snapshots": snapshots, "stage": "RecallSelected"})
        return {"image_recall_snapshots": snapshots}

    async def recall(self, state):
        snapshots = state.get("image_recall_snapshots", {})
        queries = [{**snapshots[q["target_id"]]["final_query"], "image_base_text": snapshots[q["target_id"]]["base_query"]["query"],
            "image_hint": snapshots[q["target_id"]]["image_hint"]} if q["target_id"] in snapshots else q for q in state["queries"]]
        return split_validation(await self.retriever.selected(activity_id=state["identity"]["activity_id"],
            targets=self.selected(state), queries=queries))

    async def context(self, state):
        refreshed = {}
        if any(value.get("packets") and target not in state.get("memory_validations", {})
               for target, value in state.get("memories", {}).items()):
            raise ValueError("activity_initial_memory_input_unavailable")
        from app.core.async_session import session_call
        return await session_call(self.ctx.db, lambda: self._context_sync(state, refreshed))

    def _context_sync(self, state, refreshed):
        candidates = self.selected(state)
        ids = {ref for c in candidates for ref in c["source_ids"]}
        if "_metric_sources" not in state["lane_data"]:
            raise ValueError("activity_initial_source_input_unavailable")
        manifest = [row for row in state["lane_data"]["_metric_sources"] if row["post_id"] in ids]
        return {**refreshed, "decision_context": plain({**state["shared_context"],
            "images": {target: value["images"] for target, value in state.get("image_recall_snapshots", {}).items()},
            "memories": context_memories(refreshed.get("memories", state["memories"])),
            "metric_sources": source_prompt(manifest), "source_manifest": manifest})}

    async def plan(self, state):
        receipt = {}
        async def before_retry(_attempt):
            try:
                await self.guard({**state, "stage": "ActionPlanner"})
            except Exception as exc:
                raise ActivityRetryGuardError(exc) from exc
        from app.core.async_session import session_call
        delivery = await session_call(self.ctx.db, lambda: self.delivery(state))
        decision = await self.provider.plan(lane=self.lane, context=state["decision_context"],
            candidates=self.selected(state), delivery=delivery,
            on_input_receipt=receipt.update, before_json_retry=before_retry)
        from app.runtime.autonomous_activity.name_binding import activity_name_binding, decision_names
        names = await session_call(self.ctx.db, lambda: activity_name_binding(self.ctx))
        decision = decision_names(decision, names, candidates=self.selected(state))
        from app.runtime.autonomous_activity.name_binding import observe_normalization
        observe_normalization(self.tracker, lane=self.lane,
            receipts=[row["_auxiliary_normalization"] for row in decision["decisions"]])
        return {"decision": decision, "decision_input_receipt": receipt}

    async def validate(self, state):
        from app.core.async_session import session_call
        return await session_call(self.ctx.db, lambda: self._validate_sync(state))

    def _validate_sync(self, state):
        from app.domains.routines.policies.writer_tasks import _reply_task_id
        from functools import partial
        _reply_task_id = partial(_reply_task_id, clip=lambda value, limit: str(value or "")[:limit])
        candidates = {c["target_id"]: c for c in self.selected(state)}
        assignments = []
        for index, decision in enumerate(state["decision"]["decisions"]):
            if decision["action"] != "comment":
                continue
            if self.completed_action(state, decision["target_id"]) is not None:
                continue
            post_id = state["lane_data"][decision["target_id"]]["post_id"]
            assignments.append({"task_id": _reply_task_id(scope=self.lane, index=index, post_id=post_id),
                "target_post_id": post_id, "scope": self.lane, "action_index": index,
                "brief": decision["brief"], "interaction_intent": decision["interaction_intent"],
                "comment_purpose": decision["comment_purpose"], "source": candidates[decision["target_id"]],
                "activity_proposal": candidates[decision["target_id"]].get("activity_proposal")
                    if decision.get("proposal_response") is not None else None,
                "thought": decision.get("thought"), "proposal_response": decision.get("proposal_response"), "proposal": decision.get("proposal")})
        return {"assignments": assignments}

    async def write(self, state):
        # Reuse proposal-capable Writer output and canonical writer validation.
        receipts = []
        async def before_request(_attempt):
            try:
                await self.guard({**state, "stage": "Writer"})
            except Exception as exc:
                raise ActivityRetryGuardError(exc) from exc
        writing = await self.provider.write(lane=self.lane, context=state["decision_context"],
            assignments=state["assignments"], on_input_receipt=receipts.append, before_provider_request=before_request)
        from app.runtime.autonomous_activity.name_binding import activity_name_binding, social_draft_names, observe_output
        from app.core.async_session import session_call
        names, fields = await session_call(self.ctx.db, lambda: activity_name_binding(self.ctx)), {}
        # Real Provider output is already finalized once, before canonical parsing.
        # Historical/fake adapters without receipts retain the compatibility pass.
        if any("_auxiliary_normalization" not in row for row in writing.get("reply_task_results", [])):
            writing = social_draft_names(writing, names,
                assignments=state["assignments"], lane=self.lane, receipt=fields)
            observe_output(self.tracker, names, lane=self.lane, fields=fields)
        return {"drafts": writing.get("reply_task_results", []), "writer_input_receipts": receipts}

    async def execute(self, state):
        from app.runtime.autonomous_activity.db_stage import run_db_stage
        from app.runtime.social.delivery_recovery import DeliveryStorageWait
        import asyncio
        while True:
            try:
                return await run_db_stage(self, '_execute_sync', state)
            except DeliveryStorageWait as exc:
                # Existing Writer checkpoints/draft receipts survive this wait.
                # Every resumed publication rechecks scope and execution claims.
                await asyncio.sleep(exc.seconds)

    def _execute_sync(self, state):
        if self.action_executor is None and any(d["action"] != "no_action" for d in state["decision"]["decisions"]):
            raise RuntimeError("activity_action_executor_missing")
        results, used = [], {}
        for index, decision in enumerate(state["decision"]["decisions"]):
            if decision["action"] == "no_action":
                results.append({"target_id": decision["target_id"], "status": "no_action"})
                continue
            data = state["lane_data"][decision["target_id"]]
            previous = self.completed_action(state, decision["target_id"])
            if previous is not None:
                results.append({"target_id": decision["target_id"], "status": "reused", "execution_id": previous.id})
                continue
            from app.config import settings
            if settings.DAILY_PREPARATION_ENABLED and state.get("identity", {}).get("contract_version") == 2 and decision["action"] in {"repost", "follow", "unfollow"}:
                raise ValueError("activity_action_disabled")
            action = {"action_type": "reply" if decision["action"] == "comment" else decision["action"],
                "post_id": data["post_id"], "notification_id": data.get("notification_id"),
                "interaction_intent": decision.get("interaction_intent"), "comment_purpose": decision.get("comment_purpose"),
                "brief": decision["brief"], "_activity_thought": decision.get("_activity_thought") or asdict(parse_activity_thought(decision.get("thought"))),
                "_auxiliary_normalization": decision.get("_auxiliary_normalization")}
            from app.runtime.autonomous_activity.situation_memory import participant
            admission = participant(self, state, decision["target_id"])
            result = self.action_executor(self.ctx, action=action, scope=self.lane, index=index,
                writing={"reply_task_results": state.get("drafts", [])}, used_reply_bodies=used,
                **({"situation_admission": admission} if admission is not None else {}),
                relationship_validator=self.effect_relationship_validator(state, decision["target_id"]))
            results.append({"target_id": decision["target_id"], **result})
        return {"executions": plain(results)}

    def effect_relationship_validator(self, state, target_id):
        from app.runtime.autonomous_activity.relationship_progress import capture, record
        before = None
        def validate():
            nonlocal before
            if self.claim_validator is not None:
                self.claim_validator()
            candidate = next((c for c in state.get("candidates", []) if c["target_id"] == target_id), None)
            if candidate is None:
                raise ActivityRelationshipValidationError("receipt_invalid", lane=self.lane)
            self.validate_relationship_candidate(state, candidate)
            from app.runtime.media.social_context import assert_current
            frozen_images = state.get("image_recall_snapshots", {}).get(target_id, {}).get("images", candidate.get("images", []))
            assert_current(self.ctx.db, self.ctx.user_id, frozen_images)
            self.validate_action_target(state, candidate)
            before = capture(self, state)
        def finish(execution, event):
            record(self, state, target_id, before, execution, event)
        validate.finish = finish
        return validate

    async def settle(self, state):
        from app.core.async_session import session_call
        return await session_call(self.ctx.db, lambda: self._settle_sync(state))

    def _settle_sync(self, state):
        decision = state["decision"]
        key = identity_key(state["identity"]["activity_id"], self.lane, "decision")
        def write_event(unit):
            return lambda facts: self.tracker._notify("sqlite_write", {
                "lane": self.lane, "node": "Settle", "unit": unit,
                "db_kind": "canonical", "business_key_hash": sha256(key.encode()).hexdigest(), **facts})
        # Only explicit final decisions were interpreted; omitted selected Inbox
        # conversations remain pending and receive no inferred relationship delta.
        decided = {d["target_id"] for d in decision["decisions"]}
        valid = {ref for c in self.selected(state) if c["target_id"] in decided for ref in c["source_ids"]}
        manifest = [r for r in state["decision_context"]["source_manifest"] if r["post_id"] in valid]
        revisions = {ref: rev for c in self.selected(state) for ref, rev in c["source_revisions"].items()}
        valid = {ref for ref in valid if (post := self.ctx.db.get(Post, ref, populate_existing=True)) is not None
            and post.world_id == self.actor.world_id and not post.deleted_at and not post.report_hidden_at
            and post.visibility == "public"}
        manifest = [r for r in manifest if r["post_id"] in valid]
        # The delivery receipt proves the frozen revision; current access is separate.
        manifest = [{**r, "created_at": datetime.fromisoformat(r["created_at"]) if isinstance(r["created_at"], str) else r["created_at"]} for r in manifest]
        now = datetime.fromisoformat(decision["judged_at"])
        from app.runtime.social.observations import observe_source
        def observe_post(ref):
            observe_source(self.ctx.db, world_id=self.actor.world_id,
                observer_world_character_id=self.actor.id, source_social_event_id=None,
                source_post_id=ref, lane=self.lane, observed_at=now)
        valid = set(stage_sources(self.ctx.db, actor=self.actor, manifest=manifest,
            raw=decision.get("relationship_metrics"), decision_key=key, now=now,
            observed_post_ids={ref: revisions[ref] for ref in valid}, observation_lane=self.lane,
            write_observer=write_event("S1"), scope_validator=self.claim_validator,
            observe_post=observe_post) or ())
        apply_pending_metrics(self.ctx.db, world_id=self.actor.world_id, actor_id=self.actor.id,
            source_kind="post", decision_key=key, source_keys=valid, write_observer=write_event("S2"))
        evidence_keys = {ref: identity_key("post", ref, revisions[ref]) for ref in valid}
        outcome = "invalid"
        if decision["state_status"] != "invalid":
            proposal = StateUpdate.model_validate(decision["state_update"]) if decision["state_update"] else None
            from app.core.activity_transactions import activity_write
            if self.ctx.db.in_transaction():
                self.ctx.db.commit()
            def settle_current_state():
                if self.claim_validator is not None:
                    self.claim_validator()
                current_evidence = {ref: token for ref, token in evidence_keys.items()
                    if (post := self.ctx.db.get(Post, ref, populate_existing=True)) is not None
                    and post.world_id == self.actor.world_id and post.deleted_at is None
                    and post.report_hidden_at is None and post.visibility == "public"}
                return settle_state(self.ctx.db, world_id=self.actor.world_id, actor_id=self.actor.id,
                    activity_id=state["identity"]["activity_id"], decision_key=key,
                    expected_version=state["shared_context"]["current_state"]["version"],
                    proposal=proposal, judged_at=now,
                    source_keys=[evidence_keys.get(ref, "invalid:" + ref) for ref in decision["state_source_refs"]],
                    valid_source_keys=set(current_evidence.values()),
                    context_reassessment=not decision["state_source_refs"])
            outcome = activity_write(self.ctx.db, settle_current_state,
                require_clean=True, observer=write_event("S3"))
        return {"settlement": {"state": outcome, "decision_key": key}}

    async def finalize(self, state):
        return {"result": {"path": self.lane, "status": "failed" if state.get("failure") else "completed" if state.get("executions") else "no_action",
            "failure": state.get("failure"),
            "public_action_count": sum(r["status"] in {"succeeded", "reused"} for r in state.get("executions", [])),
            "new_public_action_count": sum(r["status"] == "succeeded" for r in state.get("executions", [])),
            "selected_ids": [s["target_id"] for s in state.get("selections", [])],
            "recall_status": {key: item["status"] for key, item in state.get("memories", {}).items()},
            "settlement": state.get("settlement", {})}}
