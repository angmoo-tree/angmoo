"""C recommendation discovery and durable delivery, followed by selected recall."""
from dataclasses import asdict, replace
from datetime import UTC, datetime

from app.domains.social.contracts.world_feed import KeywordClaim, ObservationClaimResult
from app.domains.social.models.feed import WorldCharacterFeedObservation
from app.domains.social.models.posts import Post
from app.domains.social.schemas.feed import WorldFeedCandidateRead
from app.domains.social.service.feed_delivery import FeedDelivery
from app.domains.social.service.world_feed import (
    claim_cycle_keywords, claim_feed_observations, finalize_feed_cycle,
    load_ready_search_profile, search_world_feed_candidates, revalidate_candidate_actions,
)
from app.runtime.autonomous_activity.contracts import Candidate
from app.runtime.autonomous_activity.social_lane import SocialLane, plain
from app.runtime.relationships.experience_metrics import post_revision
from app.runtime.social.world_feed_queries import WorldFeedQueries


class FeedLane(SocialLane):
    def profile(self, *, neutral_weights=True):
        profile = load_ready_search_profile(self.ctx.db, references=WorldFeedQueries(self.ctx.db),
            world_character_id=self.actor.id)
        if profile.imported_world_runtime_locked or not profile.world_character.autonomous_enabled:
            raise ValueError("activity_autonomy_disabled")
        if not neutral_weights:
            return profile
        # In V2 learned preferences inform the model; only explicit permissions,
        # scope and existing reactions remove affordances.
        return replace(profile, action_profile={key: {**(profile.action_profile.get(key) or {}), "weight": 1}
            for key in ("like", "comment", "repost", "follow")})

    async def load(self, state):
        preferences = self.profile(neutral_weights=False).action_profile
        profile = self.profile()
        cycle = f"v2:{state['identity']['activity_id']}:feed"
        claim = claim_cycle_keywords(self.ctx.db, profile=profile, cycle_key=cycle, run_id=self.ctx.run_id)
        self.ctx.db.commit()
        if claim.duplicate_cycle:
            return {"candidates": [], "lane_data": {"duplicate_cycle": True}}
        search = search_world_feed_candidates(self.ctx.db, references=WorldFeedQueries(self.ctx.db),
            profile=profile, keywords=claim.keywords, allowed_policy_actions=self.ctx.activity_policy.allowed_actions,
            now=self.ctx.run_started_at, search_index=self.ctx.social_search_index, search_state=self.ctx.social_search_state)
        claims = claim_feed_observations(self.ctx.db, profile=profile, candidates=search.candidates,
            cycle_key=cycle, run_id=self.ctx.run_id, now=datetime.now(UTC))
        self.ctx.db.commit()
        candidates, data = [], {}
        from app.runtime.activity_proposals.composition import proposal_eligibility
        for candidate in claims.candidates:
            post = self.ctx.db.get(Post, candidate.post_id)
            candidates.append(Candidate(target_id=post.id, counterpart_id=post.author_world_character_id,
                source_ids=[post.id], source_revisions={post.id: post_revision(post)},
                text=f"{post.author_name}: {post.title}\n{post.body}", topic_signature=post.topic_signature,
                allowed_actions=candidate.allowed_actions, proposal_eligible=proposal_eligibility(self.ctx.db, actor_world_character_id=self.actor.id, target_post_id=post.id, now=datetime.now(UTC)).eligible, relationship=self.relationship(post.author_world_character_id)).model_dump())
            data[post.id] = {"post_id": post.id, "candidate_index": candidate.candidate_index}
        data["_feed"] = {"cycle_key": cycle, "claim": plain(asdict(claim)),
            "candidates": [c.model_dump(mode="json") for c in claims.candidates],
            "observation_ids": [o.id for o in claims.observations], "claim_tokens": {o.id: o.claim_token for o in claims.observations},
            "raw_candidate_count": search.raw_candidate_count, "query_latency_ms": search.query_latency_ms}
        return {"candidates": candidates, "lane_data": data,
            "shared_context": {**state["shared_context"], "action_preferences": preferences}}

    def delivery(self, state):
        data = state["lane_data"].get("_feed")
        if not data or not data["candidates"]:
            return None
        claims = ObservationClaimResult(
            candidates=tuple(WorldFeedCandidateRead.model_validate(c) for c in data["candidates"]),
            observations=tuple(self.ctx.db.get(WorldCharacterFeedObservation, i) for i in data["observation_ids"]),
            claim_conflict_count=0)
        delivery = FeedDelivery(self.ctx.db, profile=self.profile(), cycle_key=data["cycle_key"], claims=claims)
        if delivery.row.state in {"uncertain", "dispatched"}:
            raise ValueError("feed_delivery_requires_reconciliation")
        return delivery

    async def guard(self, state):
        await super().guard(state)
        data = state.get("lane_data", {}).get("_feed")
        if data and state.get("stage") in {"TargetSelector", "ActionPlanner", "Writer", "Execute"}:
            for identifier, token in data["claim_tokens"].items():
                row = self.ctx.db.get(WorldCharacterFeedObservation, identifier, populate_existing=True)
                if row is None or row.claim_token != token or row.run_id != self.ctx.run_id:
                    raise ValueError("feed_claim_changed")
        if data and state.get("stage") == "Execute":
            decisions = {d["target_id"]: d for d in state["decision"]["decisions"]}
            for raw in data["candidates"]:
                decision = decisions.get(raw["post_id"])
                if decision is None or decision["action"] == "no_action":
                    continue
                from app.runtime.autonomous_activity.feed_effects import committed
                if committed(self, state, decision):
                    continue
                current = revalidate_candidate_actions(self.ctx.db, references=WorldFeedQueries(self.ctx.db),
                    profile=self.profile(), candidate=WorldFeedCandidateRead.model_validate(raw),
                    allowed_policy_actions=self.ctx.activity_policy.allowed_actions)
                if current is None or decision["action"] not in current[1]:
                    raise ValueError("feed_affordance_changed")
        return {}

    async def execute(self, state):
        from app.runtime.autonomous_activity.feed_effects import execute
        return {"executions": execute(self, state)}

    def observe_delivered(self):
        from sqlalchemy import select
        from app.domains.social.models.topics import RecommendationDelivery
        from app.domains.social.contracts.observations import SocialObservationError
        from app.runtime.social.observations import observe_source
        row = self.ctx.db.scalar(select(RecommendationDelivery).where(
            RecommendationDelivery.world_character_id == self.actor.id,
            RecommendationDelivery.cycle_key == f"v2:{self.ctx.run_id}:feed",
            RecommendationDelivery.state == "delivered"))
        if row is None:
            return
        for identifier in row.post_ids:
            try:
                with self.ctx.db.begin_nested():
                    observe_source(self.ctx.db, world_id=self.actor.world_id,
                        observer_world_character_id=self.actor.id,
                        source_social_event_id=None, source_post_id=identifier,
                        lane="feed", observed_at=row.updated_at)
            except SocialObservationError:
                import logging
                logging.getLogger(__name__).warning("v2_feed_observation_source_unavailable")
        self.ctx.db.commit()

    async def finalize(self, state):
        self.observe_delivered()
        result = await super().finalize(state)
        data = state.get("lane_data", {}).get("_feed")
        if data:
            decisions = state.get("decision", {}).get("decisions", [])
            action = next((d for d in decisions if d["action"] != "no_action"), None)
            reason = "writer_failed" if state.get("failure") else None if action else "no_candidate" if not data["candidates"] else "model_abstained"
            summary = {"engine": "personalized_graph_v2", "run_id": self.ctx.run_id,
                "raw_candidate_count": data["raw_candidate_count"], "claimed_candidate_count": len(data["candidates"]),
                "selected_action": action["action"] if action else None,
                "outcome": "FAILED" if state.get("failure") else "ACTION_SELECTED" if action else "NO_ACTION", "reason_code": reason,
                "query_latency_ms": data["query_latency_ms"], "recall_count": len(state.get("memories", {})),
                "public_action_count": result["result"]["public_action_count"]}
            finalize_feed_cycle(self.ctx.db, profile=self.profile(), claim=KeywordClaim(**data["claim"]),
                observations=tuple(self.ctx.db.get(WorldCharacterFeedObservation, i) for i in data["observation_ids"]),
                selected_index=state["lane_data"][action["target_id"]]["candidate_index"] if action else None,
                selected_action=action["action"] if action else None,
                interaction_intent=action["interaction_intent"] if action else None,
                comment_purpose=action["comment_purpose"] if action else None,
                reason_code=reason, public_action_execution_id=next((r.get("execution_id") for r in state.get("executions", []) if r.get("execution_id")), None),
                summary=summary, now=datetime.now(UTC))
            self.ctx.db.commit()
            result["result"]["feed_summary"] = summary
        return result
