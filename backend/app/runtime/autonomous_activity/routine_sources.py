"""Resolve actual Routine source posts, not imaginary participants of a plan."""
import logging
from datetime import datetime

from sqlalchemy import select
from app.domains.routine_posts.constants import MAX_SOURCE_EVENTS, MAX_EVENT_EXCERPT_CHARS
from app.domains.routine_posts.utils.text import _clip
from app.domains.relationships.models.social import SocialEventEvidence
from app.domains.social.models.posts import Post
from app.runtime.social.manual_inbox import (
    ManualInboxRuntimeError, claimed_observation_post_id, is_manual_inbox_source,
)
from app.runtime.relationships.social_metrics import prepare_sources


class RoutineSourceBindingError(ValueError):
    """Keep the public admission code while retaining a safe local reason."""
    def __init__(self, reason_code):
        self.reason_code = reason_code
        super().__init__("situation_source_not_admitted")


def source_post_id(ctx, *, source_id, world_id, actor_id, beat_id):
    """Read one canonical binding; claim ownership and commit remain with callers."""
    if is_manual_inbox_source(source_id):
        with ctx.db.no_autoflush:
            return claimed_observation_post_id(ctx.db, source_event_id=source_id,
                world_id=world_id, consumer_world_character_id=actor_id,
                target_activity_beat_id=beat_id, claim_run_id=ctx.run_id)
    return ctx.db.scalar(select(SocialEventEvidence.source_post_id).where(
        SocialEventEvidence.social_event_id == source_id,
        SocialEventEvidence.source_post_id.is_not(None)).order_by(SocialEventEvidence.id))


def source_manifest(ctx, prepared):
    ids = []
    for source in prepared.context.source_events:
        identifier = source_post_id(ctx, source_id=source.source_event_id,
            world_id=prepared.world_character.world_id, actor_id=prepared.world_character.id,
            beat_id=prepared.beat.id)
        if identifier:
            ids.append(identifier)
    return prepare_sources(ctx.db, actor=prepared.world_character, post_ids=ids)


def input_source_bindings(ctx, *, scope, records, state):
    """Bind final Routine excerpts to canonical sources, never candidate IDs as events.

    The frozen prepared context is already durable. Resolve only transmitted manual
    sources here, with no new checkpoint format or cache across execution fences.
    Later memory reads use REPLY and delivery proof, not a still-active inbox claim.
    """
    try:
        if len(records) > MAX_SOURCE_EVENTS:
            raise RoutineSourceBindingError("routine_source_limit")
        bindings = []
        prepared = state.get("lane_data", {}).get("prepared", {})
        frozen = {row["source_event_id"]: row for row in prepared.get("source_events", [])}
        seen = set()
        for record in records:
            source_id = record["source_event_id"]
            if source_id in seen:
                raise RoutineSourceBindingError("routine_source_duplicate")
            seen.add(source_id)
            if not is_manual_inbox_source(source_id):
                bindings.append(("SOCIAL_EVENT", source_id))
                continue
            source = frozen.get(source_id)
            refs = prepared.get("refs", {})
            if source is None or source_id not in prepared.get("claimed_manual_source_ids", []):
                raise RoutineSourceBindingError("routine_source_binding_missing")
            if (refs.get("world") != scope.world_id
                    or ctx.user_id != scope.owner_id
                    or refs.get("world_character") != scope.subject_world_character_id
                    or source["world_id"] != scope.world_id
                    or source["consumer_world_character_id"] != scope.subject_world_character_id
                    or state.get("identity", {}).get("activity_id") != ctx.run_id
                    or not prepared.get("beat_id")):
                raise RoutineSourceBindingError("routine_source_scope_mismatch")
            expected = {key: source[key] for key in (
                "source_event_id", "actor_world_character_id", "excerpt", "occurred_at", "relationship_band")}
            # Checkpoints serialize datetimes with str(); the prompt uses ISO T.
            expected["occurred_at"] = datetime.fromisoformat(source["occurred_at"]).isoformat()
            if record != expected:
                raise RoutineSourceBindingError("routine_source_fragment_mismatch")
            identifier = source_post_id(ctx, source_id=source_id, world_id=scope.world_id,
                actor_id=scope.subject_world_character_id, beat_id=prepared["beat_id"])
            with ctx.db.no_autoflush:
                reply = ctx.db.get(Post, identifier)
            if (reply is None or not reply.reply_to_post_id
                    or reply.author_world_character_id != source["actor_world_character_id"]
                    or _clip(reply.body, MAX_EVENT_EXCERPT_CHARS) != source["excerpt"]):
                raise RoutineSourceBindingError("routine_source_changed")
            bindings.append(("REPLY", identifier))
        return bindings
    except ManualInboxRuntimeError as exc:
        # The owning service emits fixed codes, not source text or SQL arguments.
        reason = str(exc)
        logging.getLogger(__name__).warning(
            "Routine source admission failed: phase=freeze class=manual_inbox reason=%s", reason)
        raise RoutineSourceBindingError(reason) from exc
    except RoutineSourceBindingError as exc:
        logging.getLogger(__name__).warning(
            "Routine source admission failed: phase=freeze reason=%s", exc.reason_code)
        raise
