"""Freeze source identities before a planner; apply only at its safe boundary."""

from dataclasses import replace
from datetime import UTC, datetime
from collections.abc import Mapping
import logging
from sqlalchemy import select

from app.domains.social.models.posts import Post
from app.domains.world_characters.models import WorldCharacter
from app.core.sqlite_concurrency import run_sqlite_session_immediate
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


def stage_sources(db, *, actor, manifest, raw, decision_key, now,
                  observed_post_ids=(), observation_lane=None, write_observer=None,
                  scope_validator=None, observe_post=None):
    """Commit one SNS experience/observation unit, retrying from fresh rows.

    Legacy callers already relied on this function's commit.  Close their
    preceding unit explicitly so the immediate helper cannot roll it back.
    Chat uses the separate flush-only staging path in experience_metrics.
    """
    if not manifest and not observed_post_ids:
        return
    actor_id, world_id = actor.id, actor.world_id
    if db.in_transaction():
        db.commit()
    parsed = parse_metric_interpretations(raw)
    frozen_manifest = tuple(dict(row) for row in manifest)
    frozen_observed = (dict(observed_post_ids) if isinstance(observed_post_ids, Mapping)
        else {ref: None for ref in observed_post_ids})

    def operation():
        if scope_validator is not None:
            scope_validator()
        current_actor = db.get(WorldCharacter, actor_id, populate_existing=True)
        if (current_actor is None or current_actor.world_id != world_id
                or current_actor.status != "active" or current_actor.control_mode != "autonomous"):
            raise ValueError("relationship_subject_scope_changed")
        current_manifest = []
        for row in frozen_manifest:
            post = db.get(Post, row["post_id"], populate_existing=True)
            if (post is not None and post.world_id == world_id
                    and post.author_world_character_id == row["target_ref"]
                    and post.deleted_at is None and post.report_hidden_at is None
                    and post.visibility == "public" and post_revision(post) == row["revision"]):
                current_manifest.append(row)
        current_observed = []
        if observation_lane is not None:
            if observe_post is None:
                raise ValueError("relationship_observation_writer_missing")
            for ref, revision in sorted(frozen_observed.items()):
                post = db.get(Post, ref, populate_existing=True)
                if (post is not None and post.world_id == world_id
                        and post.deleted_at is None and post.report_hidden_at is None
                        and post.visibility == "public"
                        and (revision is None or post_revision(post) == revision)):
                    observe_post(ref)
                    current_observed.append(ref)
        _stage_sources_in_transaction(db, actor=current_actor, manifest=current_manifest,
            parsed=parsed, decision_key=decision_key, now=now)
        return tuple(current_observed) if observation_lane is not None else tuple(
            row["post_id"] for row in current_manifest)

    return run_sqlite_session_immediate(db, operation, require_clean=True, observer=write_observer)


def _stage_sources_in_transaction(db, *, actor, manifest, parsed, decision_key, now):
    if not manifest:
        return
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


def settle_activity(ctx):
    from app.domains.world_characters.models import CharacterActiveWorld, WorldCharacter
    if not hasattr(ctx, "db"):
        return
    try:
        active = ctx.db.get(CharacterActiveWorld, ctx.character.id)
        actor = ctx.db.get(WorldCharacter, active.world_character_id) if active else None
        if actor is None or actor.status != "active":
            return
        if interpreted_policy(ctx.db, actor.world_id) is not None:
            apply_pending_metrics(ctx.db, world_id=actor.world_id, actor_id=actor.id, source_kind="post")
    except Exception as exc:
        ctx.db.rollback()  # Already committed applications remain pending for replay.
        logging.getLogger(__name__).warning(
            "relationship_pending_apply_deferred error_type=%s", type(exc).__name__)


async def invoke_graph(graph, ctx, *args, **kwargs):
    try:
        return await graph.ainvoke(*args, **kwargs)
    finally:
        settle_activity(ctx)
