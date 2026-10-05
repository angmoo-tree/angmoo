"""Version two generation adapters reuse all canonical execution and settlement ports."""
from copy import deepcopy

from app.runtime.autonomous_activity.combined_provider import CombinedActivityProvider
from app.runtime.autonomous_activity.generation_contracts import parse_routine_draft, parse_social_draft
from app.runtime.autonomous_activity.inbox import InboxLane
from app.runtime.autonomous_activity.feed import FeedLane
from app.runtime.autonomous_activity.routine import RoutineLane


class CombinedGeneration:
    def __init__(self, *args, ledger, policies=None, input_budget=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.provider = CombinedActivityProvider(self.ctx, self.tracker, ledger=ledger, policies=policies, input_budget=input_budget)

    async def plan(self, state):
        mode = state.get("generation_mode")
        if mode not in {"combined", "split"}:
            raise ValueError("activity_generation_mode_invalid")
        self.provider.mode = mode
        self.provider.image_enabled = bool(state.get("decision_context", {}).get("image_output_enabled"))
        async def before_retry(_attempt):
            from app.runtime.autonomous_activity.output_recovery import ActivityRetryGuardError
            try:
                await self.guard({**state, "stage": "DecisionDraft"})
            except Exception as exc:
                raise ActivityRetryGuardError(exc) from exc
        self.provider.retry_guard = before_retry
        self.provider.request_guard = before_retry
        return await super().plan(state)

    async def validate(self, state):
        result = await super().validate(state)
        # Even zero-comment output must validate the empty draft set. Invalid
        # unsolicited text is never allowed to become a public action.
        if state.get("generation_mode") == "combined" and not result["assignments"]:
            try:
                parse_social_draft(state["decision"].get("provisional_draft"),
                    lane=self.lane, assignments=[], policy=self.provider.social_io_policy)
            except ValueError:
                result["failure"] = {"stage": "ValidateDraft", "reason": "unsolicited_or_invalid_draft"}
        return result

    async def write(self, state):
        async def guard_request(_attempt):
            from app.runtime.autonomous_activity.output_recovery import ActivityRetryGuardError
            try:
                await self.guard({**state, "stage": "Writer"})
            except Exception as exc:
                raise ActivityRetryGuardError(exc) from exc
        self.provider.request_guard = guard_request
        mode = state.get("generation_mode")
        if mode == "split" and not isinstance(self, RoutineLane):
            return await super().write(state)
        if mode not in {"combined", "split"}:
            raise ValueError("activity_generation_mode_invalid")
        raw = state["decision"].get("provisional_draft")
        try:
            if mode == "split":
                return await super().write(state)
            if isinstance(self, RoutineLane):
                from app.domains.characters.policies.authored_names import authored_routine_draft
                from app.runtime.autonomous_activity.name_binding import activity_name_binding, observe_output
                names, fields = activity_name_binding(self.ctx), {}
                raw = authored_routine_draft(raw, names, receipt=fields)
                observe_output(self.tracker, names, lane="routine", fields=fields)
                drafts = [parse_routine_draft(raw, image_enabled=bool(state.get("decision_context", {}).get("image_output_enabled")), name_receipt=fields)]
                self.validate_original_draft(drafts[0])
            else:
                from app.runtime.autonomous_activity.name_binding import activity_name_binding, social_draft_names, observe_output
                names, fields = activity_name_binding(self.ctx), {}
                raw = social_draft_names(raw, names,
                    assignments=state["assignments"], combined=True, lane=self.lane, receipt=fields)
                observe_output(self.tracker, names, lane=self.lane, fields=fields)
                drafts = parse_social_draft(raw, lane=self.lane,
                    assignments=state["assignments"], policy=self.provider.social_io_policy, name_receipt=fields)["reply_task_results"]
            from app.runtime.autonomous_activity.name_binding import observe_normalization
            observe_normalization(self.tracker, lane=self.lane,
                receipts=[draft["_auxiliary_normalization"] for draft in drafts])
            return {"drafts": drafts, "writer_input_receipts": [
                {**state["decision_input_receipt"], "shared_with_decision": True}]}
        except ValueError as exc:
            receipt = state.get("decision", {}).get("_json_recovery_receipt")
            if isinstance(receipt, dict) and receipt.get("reason") == "comment_intent_missing":
                # The complete envelope already used its sole regeneration.
                # A split Writer would be a third repair of that same request.
                raise ValueError("combined_missing_recovery_draft_invalid") from exc
            if mode == "split" and str(exc) != "routine_reuses_published_reply" and not str(exc).startswith("name_"):
                raise
            if isinstance(self, RoutineLane):
                self.writer_feedback = {"validation_code": str(exc) if str(exc).startswith("name_") or str(exc) == "routine_reuses_published_reply" else "routine_draft_invalid",
                    "instruction": "Write a new original Routine post from the same validated plan; the previous draft was rejected."}
            elif str(exc).startswith("name_"):
                state = {**state, "decision_context": {**state["decision_context"], "writer_feedback": {
                    "validation_code": str(exc), "instruction": "Use the actual recipient from each assignment. "
                    "Never address another character as the bound World user or copy unresolved macros from history. "
                    "Keep the validated actions and sources unchanged."}}}
            if getattr(self.tracker, "observer", None) is not None:
                import re
                reason = str(exc) if re.fullmatch(r"[a-z][a-z0-9_]{0,80}", str(exc)) else "combined_draft_invalid"
                lane = "routine" if isinstance(self, RoutineLane) else self.lane
                self.tracker._notify("draft_validation_error", {"node": lane.title() + "DecisionDraft",
                    "lane": lane, "status": "writer_recovery", "validation_code": reason, "field_path": "draft"})
            await self.guard({**state, "stage": "Writer"})
            self.provider.repairing = True
            try:
                result = await super().write(state)
                result["writer_input_receipts"] = [
                    {**r, "writer_recovery": True} for r in result.get("writer_input_receipts", [])]
                return result
            finally:
                self.provider.repairing = False


class CombinedInboxLane(CombinedGeneration, InboxLane):
    pass


class CombinedRoutineLane(CombinedGeneration, RoutineLane):
    lane = "routine"


class CombinedFeedLane(CombinedGeneration, FeedLane):
    def save_preparation(self):
        # Claims and their recoverable snapshot must commit together. Version one
        # retains its original commit boundaries through FeedLane's implementation.
        self.ctx.db.flush()

    async def load(self, state):
        from app.domains.world_characters.activity_models import ActivityGraphRun
        from app.runtime.autonomous_activity.social_lane import plain
        run = self.ctx.db.get(ActivityGraphRun, self.ctx.run_id, populate_existing=True)
        saved = (run.result or {}).get("feed_preparation")
        if saved is not None:
            self.reconcile_deliveries()
            return deepcopy(saved)
        result = await super().load(state)
        run.result = {**(run.result or {}), "feed_preparation": plain(result)}
        self.ctx.db.commit()
        return result

    async def guard(self, state):
        await super().guard(state)
        data = state.get("lane_data", {}).get("_feed")
        if data and state.get("stage") in {"TargetSelector", "DecisionDraft", "Writer", "ValidateDraft", "Execute"}:
            from app.domains.social.service.world_feed import renew_owned_feed_claims
            from datetime import UTC, datetime
            renew_owned_feed_claims(self.ctx.db, claim_tokens=data["claim_tokens"],
                run_id=self.ctx.run_id, now=datetime.now(UTC))
            self.ctx.db.commit()

    async def finalize(self, state):
        result = await super().finalize(state)
        self.reconcile_deliveries()
        return result

    def finalize_unavailable(self, reason):
        from datetime import UTC, datetime
        from app.domains.social.contracts.world_feed import KeywordClaim
        from app.domains.social.service.world_feed import finalize_unavailable_feed_cycle
        from app.domains.world_characters.activity_models import ActivityGraphRun
        run = self.ctx.db.get(ActivityGraphRun, self.ctx.run_id)
        saved = (run.result or {}).get("feed_preparation", {})
        data = saved.get("lane_data", {}).get("_feed")
        if not data:
            return None
        summary = {"engine": "personalized_graph_v2", "run_id": self.ctx.run_id,
            "raw_candidate_count": data["raw_candidate_count"],
            "claimed_candidate_count": len(data["candidates"]), "selected_action": None,
            "outcome": "NO_ACTION", "reason_code": "target_stale", "termination_reason": reason,
            "query_latency_ms": data["query_latency_ms"], "public_action_count": 0}
        finalize_unavailable_feed_cycle(self.ctx.db, profile=self.profile(),
            cycle_key=data["cycle_key"], run_id=self.ctx.run_id, claim=KeywordClaim(**data["claim"]),
            claim_tokens=data["claim_tokens"], summary=summary, now=datetime.now(UTC))
        self.ctx.db.commit()
        return summary

    async def refresh_selected(self, state):
        """Keep selection fixed, but read post/relationship/permissions after Inbox."""
        from app.domains.social.models.posts import Post
        from app.domains.social.schemas.feed import WorldFeedCandidateRead
        from app.domains.social.service.world_feed import revalidate_candidate_actions
        from app.runtime.social.world_feed_queries import WorldFeedQueries
        from app.runtime.relationships.experience_metrics import post_revision
        from app.runtime.activity_proposals.composition import proposal_eligibility
        from datetime import UTC, datetime

        result = deepcopy(state)
        result.setdefault("relationship_validation_receipts", {})
        selected = {s["target_id"] for s in state.get("selections", [])}
        data = state.get("lane_data", {}).get("_feed", {})
        raw_by_id = {c["post_id"]: c for c in data.get("candidates", [])}
        for candidate in result.get("candidates", []):
            if candidate["target_id"] not in selected:
                continue
            post = self.ctx.db.get(Post, candidate["target_id"], populate_existing=True)
            if post is None or post_revision(post) != candidate["source_revisions"].get(post.id):
                raise ValueError("feed_target_stale")
            current = revalidate_candidate_actions(self.ctx.db, references=WorldFeedQueries(self.ctx.db),
                profile=self.profile(), candidate=WorldFeedCandidateRead.model_validate(raw_by_id[post.id]),
                allowed_policy_actions=self.ctx.activity_policy.allowed_actions)
            if current is None or not current[1]:
                raise ValueError("feed_target_stale")
            candidate["allowed_actions"] = list(current[1])
            prompt, receipt = self.relationship_preparation(candidate["target_id"], candidate["counterpart_id"])
            candidate["relationship"] = prompt
            result["relationship_validation_receipts"][candidate["target_id"]] = receipt
            candidate["proposal_eligible"] = proposal_eligibility(self.ctx.db,
                actor_world_character_id=self.actor.id, target_post_id=post.id, now=datetime.now(UTC)).eligible
        return result
