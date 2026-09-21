"""Freeze source identities before a planner; apply only at its safe boundary."""

from dataclasses import replace
from datetime import UTC, datetime
from sqlalchemy import select

from app.domains.social.models.posts import Post
from app.domains.relationships.models.personalization import RelationshipExperienceReceipt
from app.domains.relationships.contracts.metric_interpretation import parse_metric_interpretations
from app.domains.relationships.service.personalized_metrics import ExperiencedSource, interpreted_policy, stage_experience
from app.domains.worlds.service.character_entry import get_character_entry_world
from app.runtime.relationships.experience_metrics import post_revision, RuntimeExperienceReferences, apply_pending_metrics


def prepare_sources(db, *, actor, post_ids):
    if actor is None or actor.control_mode != "autonomous" or interpreted_policy(db, actor.world_id) is None:
        return []
    ids = tuple(dict.fromkeys(identifier for identifier in post_ids if identifier))
    if len(ids) > 20:
        raise ValueError("relationship_social_source_limit")
    posts = {p.id: p for p in db.scalars(select(Post).where(Post.id.in_(ids), Post.world_id == actor.world_id,
        Post.deleted_at.is_(None), Post.report_hidden_at.is_(None), Post.visibility == "public"))}
    return [{"post_id": post.id, "target_ref": post.author_world_character_id,
             "revision": post_revision(post), "created_at": post.created_at,
             "excerpt": (post.body or "")[:500]}
            for identifier in ids if (post := posts.get(identifier)) is not None
            and post.author_world_character_id and post.author_world_character_id != actor.id]


def source_prompt(manifest):
    return [{"target_ref": row["target_ref"], "source_ref": row["post_id"], "text": row["excerpt"]} for row in manifest]


def stage_sources(db, *, actor, manifest, raw, decision_key, now):
    if not manifest:
        return
    parsed = parse_metric_interpretations(raw)
    by_post = {row["post_id"]: row for row in manifest}
    changes = {}
    for proposed in parsed.interpretations:
        valid = [ref for ref in proposed.new_evidence_refs if ref in by_post and by_post[ref]["target_ref"] == proposed.target_ref]
        if len(valid) != len(proposed.new_evidence_refs):
            continue
        # One directional proposal per counterpart, even when it cites 3 posts.
        for ref in valid:
            used = db.scalar(select(RelationshipExperienceReceipt.id).where(
                RelationshipExperienceReceipt.world_id == actor.world_id,
                RelationshipExperienceReceipt.actor_world_character_id == actor.id,
                RelationshipExperienceReceipt.source_kind == "post", RelationshipExperienceReceipt.source_key == ref))
            if used is None:
                changes[ref] = replace(proposed, new_evidence_refs=(ref,))
                break
    world = get_character_entry_world(db, actor.world_id)
    references = RuntimeExperienceReferences(db, confirmed_posts={r["post_id"]: r["revision"] for r in manifest})
    for row in manifest:
        try:
            with db.begin_nested():
                source = ExperiencedSource(actor.world_id, actor.id, row["target_ref"], "post", row["post_id"],
                    row["revision"], row["created_at"], now, world.timezone)
                stage_experience(db, references=references, source=source, decision_key=decision_key,
                    interpretation=changes.get(row["post_id"]), metadata_status=parsed.status)
        except ValueError:
            continue  # Deleted/changed or invalid optional metadata cannot erase the action.
    db.commit()


def settle_activity(ctx):
    from app.runtime.social.langgraph_actions import active_world_character
    if not hasattr(ctx, "db"):
        return
    try:
        actor = active_world_character(ctx.db, character_id=ctx.character.id)
        if interpreted_policy(ctx.db, actor.world_id) is not None:
            apply_pending_metrics(ctx.db, world_id=actor.world_id, actor_id=actor.id, source_kind="post")
    except Exception:
        ctx.db.rollback()  # Already committed applications remain pending for replay.


async def invoke_graph(graph, ctx, *args, **kwargs):
    try:
        return await graph.ainvoke(*args, **kwargs)
    finally:
        settle_activity(ctx)
