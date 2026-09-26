"""Version two generation adapters reuse all canonical execution and settlement ports."""
from copy import deepcopy

from app.runtime.autonomous_activity.combined_provider import CombinedActivityProvider
from app.runtime.autonomous_activity.generation_contracts import parse_routine_draft, parse_social_draft
from app.runtime.autonomous_activity.inbox import InboxLane
from app.runtime.autonomous_activity.feed import FeedLane
from app.runtime.autonomous_activity.routine import RoutineLane


class CombinedGeneration:
    def __init__(self, *args, ledger, **kwargs):
        super().__init__(*args, **kwargs)
        self.provider = CombinedActivityProvider(self.ctx, self.tracker, ledger=ledger)

    async def plan(self, state):
        mode = state.get("generation_mode")
        if mode not in {"combined", "split"}:
            raise ValueError("activity_generation_mode_invalid")
        self.provider.mode = mode
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
                    lane=self.lane, assignments=[])
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
        if state.get("generation_mode") == "split":
            return await super().write(state)
        if state.get("generation_mode") != "combined":
            raise ValueError("activity_generation_mode_invalid")
        raw = state["decision"].get("provisional_draft")
        try:
            if isinstance(self, RoutineLane):
                drafts = [parse_routine_draft(raw)]
            else:
                drafts = parse_social_draft(raw, lane=self.lane,
                    assignments=state["assignments"])["reply_task_results"]
            return {"drafts": drafts, "writer_input_receipts": [
                {**state["decision_input_receipt"], "shared_with_decision": True}]}
        except ValueError as exc:
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
    pass


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
            candidate["relationship"] = self.relationship(candidate["counterpart_id"])
            candidate["proposal_eligible"] = proposal_eligibility(self.ctx.db,
                actor_world_character_id=self.actor.id, target_post_id=post.id, now=datetime.now(UTC)).eligible
        return result
