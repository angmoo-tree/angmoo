"""Bounded, same-Session history composition after recommendation owner authorization.

Deliveries own list membership. Observations and Routines executions only explain
results. No recommendation eligibility, provider work, writes or history repair.
"""
from datetime import UTC

from sqlalchemy import and_, exists, or_, select
from sqlalchemy.orm import Session, load_only

from app.domains.characters.models import Character
from app.domains.routines.models.resident import AgentPublicActionExecution
from app.domains.social.models.feed import WorldCharacterBlock, WorldCharacterFeedObservation
from app.domains.social.models.posts import Post
from app.domains.social.models.topics import RecommendationDelivery
from app.domains.social.schemas.recommendation import DeliveryHistoryRead, DeliveryPostRead
from app.domains.social.service.feed_cycle_values import execution_signature_values
from app.domains.world_characters.models import WorldCharacter
from app.domains.worlds.models import WorldMembership

LANES = ("latest", "interest", "relation", "explore")
ACTIONS = ("like", "comment", "repost", "follow")


def _post_ids(value):
    if not isinstance(value, list):
        return [], None, True
    # A corrupt oversized receipt must not expand any downstream IN query.
    ids = list(dict.fromkeys(v for v in value[:20] if isinstance(v, str) and 0 < len(v) <= 64))
    partial = len(value) > 20 or len(ids) != len(value)
    return ids, None if partial else len(ids), partial


def _result(observation, execution, *, character_id):
    if observation is None or observation.status != "observed":
        return None, "unrecorded"
    action = observation.selected_action
    if observation.decision_outcome == "action_selected" and action in ACTIONS:
        if execution is None:
            return action, "selected"
        if not (
            execution.world_id == observation.world_id
            and execution.actor_world_character_id == observation.observer_world_character_id
            and execution.character_id == character_id
            and execution.feed_observation_id == observation.id
            and execution.target_post_id == observation.post_id
            and execution.action_type == action
            and execution.scope == "world_keyword_feed"
            and execution.interaction_intent == observation.interaction_intent
        ):
            return None, "unrecorded"
        if execution.run_id != observation.run_id:
            expected = execution_signature_values(
                world_character_id=observation.observer_world_character_id,
                world_id=observation.world_id, action=action, post_id=observation.post_id,
                interaction_intent=observation.interaction_intent, cycle_key=observation.cycle_key,
            )
            if execution.status != "succeeded" or execution.signature != expected:
                return None, "unrecorded"
        if execution.status in ("pending", "succeeded", "failed"):
            return action, execution.status
        return None, "unrecorded"
    if action is not None or observation.public_action_execution_id is not None:
        return None, "unrecorded"
    if observation.decision_outcome == "not_selected":
        return None, "not_selected"
    if observation.decision_outcome == "no_action":
        if observation.reason_code == "model_abstained":
            return None, "no_action"
        if observation.reason_code in (
            "no_searchable_keyword", "no_candidate", "no_allowed_action", "proposal_ineligible",
            "proposal_apply_not_ready", "target_stale", "writer_invalid",
        ):
            return None, "not_performed"
    return None, "unrecorded"


def _visible_posts(db, *, world_id, world_character_id, ids):
    blocked = exists(select(WorldCharacterBlock.id).where(
        WorldCharacterBlock.world_id == world_id,
        or_(and_(WorldCharacterBlock.blocker_world_character_id == world_character_id,
                 WorldCharacterBlock.blocked_world_character_id == Post.author_world_character_id),
            and_(WorldCharacterBlock.blocked_world_character_id == world_character_id,
                 WorldCharacterBlock.blocker_world_character_id == Post.author_world_character_id)),
    ))
    # Author membership is a current read constraint; receipt/unseen/action rules
    # are deliberately absent. Read only titles, never bodies or provider results.
    member = exists(select(WorldMembership.id).where(
        WorldMembership.world_id == world_id, WorldMembership.user_id == Post.author_user_id,
        WorldMembership.status == "active",
    ))
    return dict(db.execute(select(Post.id, Post.title).outerjoin(
        WorldCharacter, WorldCharacter.id == Post.author_world_character_id,
    ).outerjoin(Character, Character.id == WorldCharacter.character_id).where(
        Post.id.in_(ids), Post.world_id == world_id, Post.visibility == "public",
        Post.deleted_at.is_(None), Post.report_hidden_at.is_(None), ~blocked, member,
        or_(and_(Post.author_world_character_id.is_(None), Post.author_character_id.is_(None)),
            and_(WorldCharacter.world_id == world_id, WorldCharacter.status == "active",
                 Character.id == Post.author_character_id, Character.owner_id == Post.author_user_id,
                 Character.deleted_at.is_(None))),
    )).all())


def read_delivery_history(db: Session, *, world_id: str, world_character_id: str):
    """Caller has checked owner + World + character. Never commit or autoflush."""
    with db.no_autoflush:
        deliveries = list(db.scalars(select(RecommendationDelivery).where(
            RecommendationDelivery.world_id == world_id,
            RecommendationDelivery.world_character_id == world_character_id,
            RecommendationDelivery.state == "delivered",
        ).order_by(RecommendationDelivery.updated_at.desc(), RecommendationDelivery.id.desc()).limit(5)))
        if not deliveries:
            return []
        receipts = [(row, *_post_ids(row.post_ids)) for row in deliveries]
        ids = {identity for _, post_ids, _, _ in receipts for identity in post_ids}
        titles = _visible_posts(db, world_id=world_id, world_character_id=world_character_id, ids=ids) if ids else {}
        observations = list(db.scalars(select(WorldCharacterFeedObservation).where(
            WorldCharacterFeedObservation.world_id == world_id,
            WorldCharacterFeedObservation.observer_world_character_id == world_character_id,
            WorldCharacterFeedObservation.cycle_key.in_([row.cycle_key for row in deliveries]),
            WorldCharacterFeedObservation.post_id.in_(titles),
        ))) if titles else []
        by_cycle_post = {(row.cycle_key, row.post_id): row for row in observations}
        execution_ids = {row.public_action_execution_id for row in observations if row.public_action_execution_id is not None}
        executions = {row.id: row for row in db.scalars(select(AgentPublicActionExecution).where(
            AgentPublicActionExecution.id.in_(execution_ids),
        ).options(load_only(
            AgentPublicActionExecution.id, AgentPublicActionExecution.world_id,
            AgentPublicActionExecution.actor_world_character_id, AgentPublicActionExecution.character_id,
            AgentPublicActionExecution.feed_observation_id, AgentPublicActionExecution.target_post_id,
            AgentPublicActionExecution.action_type, AgentPublicActionExecution.scope,
            AgentPublicActionExecution.interaction_intent, AgentPublicActionExecution.run_id,
            AgentPublicActionExecution.signature, AgentPublicActionExecution.status,
        )))} if execution_ids else {}
        character_id = db.scalar(select(WorldCharacter.character_id).where(
            WorldCharacter.id == world_character_id, WorldCharacter.world_id == world_id,
        )) if observations else None
        result = []
        for row, post_ids, count, partial in receipts:
            posts = []
            traces = row.trace if isinstance(row.trace, dict) else {}
            for identity in post_ids:
                if identity not in titles:
                    continue
                trace = traces.get(identity)
                trace = trace if isinstance(trace, dict) else {}
                lane = trace.get("lane")
                sources = trace.get("sources")
                sources = sources if isinstance(sources, list) else []
                obs = by_cycle_post.get((row.cycle_key, identity))
                action, state = _result(obs, executions.get(obs.public_action_execution_id) if obs else None,
                                        character_id=character_id)
                posts.append(DeliveryPostRead(post_id=identity, title=titles[identity][:160],
                    lane=lane if lane in LANES else None,
                    sources=[name for name in LANES if name in sources],
                    selected_action=action, result_state=state))
            stamp = row.updated_at
            stamp = stamp.replace(tzinfo=UTC) if stamp.tzinfo is None else stamp.astimezone(UTC)
            result.append(DeliveryHistoryRead(delivery_id=row.id, recorded_at=stamp.isoformat(),
                recorded_post_count=count, visible_post_count=len(posts),
                unavailable_post_count=count - len(posts) if count is not None else None,
                is_partial=partial, posts=posts).model_dump(mode="json"))
        return result


def legacy_feed(deliveries):
    """Compatibility projection of the SAME verified history, at most 20 posts."""
    rows = {}
    for delivery in deliveries:
        for post in delivery["posts"]:
            state = post["result_state"]
            rows.setdefault(post["post_id"], {
                "post_id": post["post_id"], "title": post["title"],
                "sources": post["sources"], "lane": post["lane"], "action": post["selected_action"],
                "outcome": "action_selected" if post["selected_action"] else
                    "no_action" if state in ("no_action", "not_performed") else
                    "not_selected" if state == "not_selected" else None,
            })
            if len(rows) == 20:
                return list(rows.values())
    return list(rows.values())
