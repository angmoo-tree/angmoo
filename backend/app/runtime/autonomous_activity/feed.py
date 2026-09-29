"""C recommendation discovery and durable delivery, followed by selected recall."""
from dataclasses import asdict, replace
from datetime import UTC, datetime
from hashlib import sha256

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
    def save_preparation(self):
        self.ctx.db.commit()

    def profile(self, *, neutral_weights=True):
        profile = load_ready_search_profile(self.ctx.db, references=WorldFeedQueries(self.ctx.db),
            world_character_id=self.actor.id)
        if profile.imported_world_runtime_locked or not profile.world_character.autonomous_enabled:
            raise ValueError("activity_autonomy_disabled")
        if not neutral_weights:
            return profile
        if profile.explicit_actions is not None:
            return profile
        # In V2 learned preferences inform the model; only explicit permissions,
        # scope and existing reactions remove affordances.
        return replace(profile, action_profile={key: {**(profile.action_profile.get(key) or {}), "weight": 1}
            for key in ("like", "comment", "repost", "follow")})

    async def load(self, state):
        self.reconcile_deliveries()
        from app.domains.social.exceptions import WorldFeedReadinessError
        try:
            preferences = self.profile(neutral_weights=False).action_profile
            profile = self.profile()
        except WorldFeedReadinessError as exc:
            if exc.reason_code != "recommendation_topics_required":
                raise
            return {"candidates": [], "lane_data": {"deferred_reason": exc.reason_code}}
        cycle = f"v2:{state['identity']['activity_id']}:feed"
        claim = claim_cycle_keywords(self.ctx.db, profile=profile, cycle_key=cycle, run_id=self.ctx.run_id)
        self.save_preparation()
        if claim.duplicate_cycle:
            return {"candidates": [], "lane_data": {"duplicate_cycle": True}}
        search = search_world_feed_candidates(self.ctx.db, references=WorldFeedQueries(self.ctx.db),
            profile=profile, keywords=claim.keywords, allowed_policy_actions=self.ctx.activity_policy.allowed_actions,
            now=self.ctx.run_started_at, search_index=self.ctx.social_search_index, search_state=self.ctx.social_search_state)
        claims = claim_feed_observations(self.ctx.db, profile=profile, candidates=search.candidates,
            cycle_key=cycle, run_id=self.ctx.run_id, now=datetime.now(UTC))
        self.save_preparation()
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
        shared = dict(state["shared_context"])
        if profile.explicit_actions is None:
            shared["action_preferences"] = preferences
        return {"candidates": candidates, "lane_data": data, "shared_context": shared}

    def delivery(self, state):
        data = state["lane_data"].get("_feed")
        if not data or not data["candidates"]:
            return None
        claims = ObservationClaimResult(
            candidates=tuple(WorldFeedCandidateRead.model_validate(c) for c in data["candidates"]),
            observations=tuple(self.ctx.db.get(WorldCharacterFeedObservation, i) for i in data["observation_ids"]),
            claim_conflict_count=0)
        version_two = state.get("identity", {}).get("contract_version") == 2
        def validate_claims():
            from app.domains.social.service.world_feed import renew_owned_feed_claims
            renew_owned_feed_claims(self.ctx.db, claim_tokens=data["claim_tokens"],
                run_id=self.ctx.run_id, now=datetime.now(UTC))
            self.ctx.db.commit()
        delivery = FeedDelivery(self.ctx.db, profile=self.profile(), cycle_key=data["cycle_key"], claims=claims,
            validate=validate_claims if version_two else None,
            validate_completion=validate_claims if version_two else None, retain_until_observed=version_two)
        if delivery.row.state in {"uncertain", "dispatched"}:
            raise ValueError("feed_delivery_requires_reconciliation")
        return delivery

    async def guard(self, state):
        await super().guard(state)
        data = state.get("lane_data", {}).get("_feed")
        if data and state.get("stage") in {"TargetSelector", "DecisionDraft", "ActionPlanner", "ValidateDraft", "Writer", "Execute"}:
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

    def completed_action(self, state, target_id):
        from app.runtime.autonomous_activity.feed_effects import committed
        decision = next((row for row in state.get("decision", {}).get("decisions", [])
                         if row["target_id"] == target_id), None)
        return committed(self, state, decision) if decision and decision["action"] != "no_action" else None

    def observe_delivered(self):
        from app.runtime.social.feed_observations import settle_delivery
        world_id, actor_id = self.actor.world_id, self.actor.id
        cycle_key = f"v2:{self.ctx.run_id}:feed"
        # This lane owns the preceding boundary. Commit also preserves writes
        # already flushed by its caller, which Session.dirty cannot identify.
        if self.ctx.db.in_transaction():
            self.ctx.db.commit()
        settle_delivery(self.ctx.db, world_id=world_id, actor_id=actor_id,
            cycle_key=cycle_key, verify_replay=True, observer=self.observation_diagnostics(cycle_key, "ObserveDelivered"))

    def observation_diagnostics(self, key, node):
        tracker = getattr(self, "tracker", None)
        if tracker is None:
            return None
        return lambda facts: tracker._notify("sqlite_write", {
            "lane": "feed", "node": node, "unit": "feed_delivery_observation",
            "db_kind": "canonical", "business_key_hash": sha256(key.encode()).hexdigest(), **facts})

    def reconcile_deliveries(self):
        from sqlalchemy import select
        from app.domains.social.models.topics import RecommendationDelivery
        from app.runtime.social.feed_observations import settle_delivery
        world_id, actor_id = self.actor.world_id, self.actor.id
        if self.ctx.db.in_transaction():
            self.ctx.db.commit()
        identifiers = self.ctx.db.scalars(select(RecommendationDelivery.id).where(
            RecommendationDelivery.world_id == world_id,
            RecommendationDelivery.world_character_id == actor_id,
            RecommendationDelivery.state == "delivered",
            RecommendationDelivery.trace["_activity_observation"].as_string() == "pending",
        ).order_by(RecommendationDelivery.updated_at, RecommendationDelivery.id).limit(200)).all()
        self.ctx.db.commit()  # Close this owned ID scan before any writer read.
        for identifier in identifiers:
            # An exhausted/error unit propagates immediately: do not multiply
            # the bounded writer budget by the whole pending batch.
            settle_delivery(self.ctx.db, world_id=world_id, actor_id=actor_id, delivery_id=identifier,
                observer=self.observation_diagnostics(identifier, "ReconcileDeliveries"))

    async def finalize(self, state):
        self.observe_delivered()
        result = await super().finalize(state)
        if state.get("lane_data", {}).get("deferred_reason"):
            result["result"].update(status="deferred", reason=state["lane_data"]["deferred_reason"])
            return result
        data = state.get("lane_data", {}).get("_feed")
        if data:
            decisions = state.get("decision", {}).get("decisions", [])
            action = next((d for d in decisions if d["action"] != "no_action"), None)
            reason = "writer_invalid" if state.get("failure") else None if action else "no_candidate" if not data["candidates"] else "model_abstained"
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
