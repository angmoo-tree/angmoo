"""Canonical Feed execution shared with C recommendation; no second write model."""
from datetime import UTC, datetime

from app.core.unit_of_work import deferred_commits
from app.contracts.activity_thought import ActivityThought, parse_activity_thought
from app.domains.social.schemas.feed import FeedReactionDecision, FeedCommentDraft, JointActivityProposalPreview, WorldFeedCandidateRead
from app.domains.social.service.feed_cycle_publishing import _publish_action
from app.domains.social.service.feed_cycle_values import _execution_signature, _brief_hash
from app.runtime.social.feed_cycle import RuntimeWorldFeedWorkflows


def decision_values(state, raw):
    data = state["lane_data"]["_feed"]
    candidate = next(WorldFeedCandidateRead.model_validate(c) for c in data["candidates"] if c["post_id"] == raw["target_id"])
    decision = FeedReactionDecision(selected_candidate_index=candidate.candidate_index,
        selected_action=raw["action"], interaction_intent=raw["interaction_intent"],
        comment_purpose=raw["comment_purpose"], brief=raw["brief"])
    return candidate, decision


def committed(lane, state, raw):
    candidate, decision = decision_values(state, raw)
    signature = _execution_signature(profile=lane.profile(), candidate=candidate, decision=decision,
        cycle_key=state["lane_data"]["_feed"]["cycle_key"])
    row = RuntimeWorldFeedWorkflows.executions.get_public_action_execution_by_signature(lane.ctx.db, signature)
    return row if row is not None and row.status == "succeeded" else None


def execute(lane, state):
    workflows, db = RuntimeWorldFeedWorkflows(), lane.ctx.db
    results = []
    for raw in state["decision"]["decisions"]:
        if raw["action"] == "no_action":
            results.append({"target_id": raw["target_id"], "status": "no_action"})
            continue
        previous = committed(lane, state, raw)
        if previous:
            results.append({"target_id": raw["target_id"], "status": "reused", "execution_id": previous.id})
            continue
        candidate, decision = decision_values(state, raw)
        profile = lane.profile()
        draft, thought = None, parse_activity_thought(raw.get("thought"))
        if raw["action"] == "comment":
            key = next(a["task_id"] for a in state["assignments"] if a["target_post_id"] == candidate.post_id)
            written = next(r for r in state["drafts"] if r["task_id"] == key)
            text = written.get("body")
            if not text or not written.get("writer_node"):
                raise ValueError("feed_writer_result_invalid")
            if raw["interaction_intent"] == "joint_activity_proposal":
                draft = JointActivityProposalPreview.model_validate({**raw["proposal"], "text": text})
                workflows.proposals.validate_preview(db, preview=draft, world_id=profile.world.id,
                    proposer_world_character_id=lane.actor.id, target_post_id=candidate.post_id, now=datetime.now(UTC))
            else:
                draft = FeedCommentDraft(text=text, source_post_id=candidate.post_id,
                    interaction_intent="ordinary_comment", comment_purpose=raw["comment_purpose"])
            thought = ActivityThought(**written["_activity_thought"]) if written.get("_activity_thought") else ActivityThought()
        signature = _execution_signature(profile=profile, candidate=candidate, decision=decision,
            cycle_key=state["lane_data"]["_feed"]["cycle_key"])
        from app.domains.social.models.feed import WorldCharacterFeedObservation
        observations = [db.get(WorldCharacterFeedObservation, key) for key in state["lane_data"]["_feed"]["observation_ids"]]
        observation = next(row for row in observations if row.post_id == candidate.post_id)
        try:
            with deferred_commits():
                row = workflows.executions.create_public_action_execution(db, run_id=lane.ctx.run_id,
                    character_id=lane.ctx.character.id, signature=signature, scope="world_keyword_feed",
                    action_type=decision.selected_action, target_post_id=candidate.post_id,
                    target_profile_type="character" if raw["action"] == "follow" else None,
                    target_profile_id=candidate.author_character_id if raw["action"] == "follow" else None,
                    brief_hash=_brief_hash(decision.brief), world_id=lane.actor.world_id,
                    actor_world_character_id=lane.actor.id, feed_observation_id=observation.id,
                    interaction_intent=decision.interaction_intent, comment_purpose=decision.comment_purpose)
                result = _publish_action(lane.ctx, workflows=workflows.publishing, candidate=candidate, decision=decision, draft=draft)
                applied = workflows.social_apply.apply_successful_world_feed_action(db, profile=profile,
                    candidate=candidate, decision=decision, draft=draft, action_result=result, execution=row, occurred_at=datetime.now(UTC))
                workflows.executions.mark_public_action_execution_finished(db, row, status="succeeded", result=result)
                workflows.record_activity_thought(db, execution=row, event=applied.event,
                    source_post_id=str(result["post_id"]) if draft else None, thought=thought, captured_at=datetime.now(UTC))
            db.commit()
        except Exception:
            db.rollback()
            raise
        results.append({"target_id": raw["target_id"], "status": "succeeded", "execution_id": row.id})
    return results
