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


def capture_source_bindings(ctx, prepared):
    result = {}
    for source in prepared.context.source_events:
        if not is_manual_inbox_source(source.source_event_id):
            result[source.source_event_id] = ["SOCIAL_EVENT", source.source_event_id]
            continue
        identifier = source_post_id(ctx, source_id=source.source_event_id,
            world_id=prepared.world_character.world_id, actor_id=prepared.world_character.id,
            beat_id=prepared.beat.id)
        reply = ctx.db.get(Post, identifier) if identifier else None
        if (reply is None or not reply.reply_to_post_id or reply.world_id != prepared.world_character.world_id
                or reply.author_world_character_id != source.actor_world_character_id):
            raise RoutineSourceBindingError("routine_source_binding_missing")
        result[source.source_event_id] = ["REPLY", identifier]
    return result


def validate_source_access(ctx, prepared, frozen):
    """Current participants and claim ownership, without reading source prose."""
    if frozen.get("beat_id") != prepared.beat.id:
        raise RoutineSourceBindingError("routine_initial_beat_mismatch")
    from app.domains.relationships.contracts.graph_recall import GraphRecallScope
    from app.domains.relationships.service.social_context_validation import SocialContextValidationService
    from app.runtime.graph_projection.relationship_graph_read import SqlAlchemyRelationshipGraphReadGateway
    from app.domains.social.models.manual_writes import OwnerManualInboxCandidate
    from app.domains.social.utils.manual_inbox import candidate_id
    scope = GraphRecallScope(ctx.user_id, prepared.world_character.world_id, prepared.world_character.id)
    targets = tuple(dict.fromkeys(source.actor_world_character_id for source in prepared.context.source_events
        if source.actor_world_character_id != scope.subject_world_character_id))
    SocialContextValidationService(SqlAlchemyRelationshipGraphReadGateway(ctx.db)).assert_access(scope, targets)
    for identifier in prepared.claimed_manual_source_ids:
        row_id = candidate_id(identifier)
        row = ctx.db.get(OwnerManualInboxCandidate, row_id, populate_existing=True) if row_id else None
        binding = frozen.get("source_bindings", {}).get(identifier)
        if (row is None or row.world_id != scope.world_id or row.target_world_character_id != scope.subject_world_character_id
                or row.target_activity_beat_id != prepared.beat.id or row.claim_run_id != ctx.run_id
                or row.status != "claimed" or binding != ["REPLY", row.source_reply_post_id]):
            raise RoutineSourceBindingError("manual_inbox_claim_mismatch")


def input_source_bindings(ctx, *, scope, records, state):
    """Bind final Routine excerpts to canonical sources, never candidate IDs as events.

    The frozen prepared context contains the first admitted source bindings. Bind
    only transmitted excerpts here without re-reading their current originals.
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
            source = frozen.get(source_id)
            refs = prepared.get("refs", {})
            if source is None or (is_manual_inbox_source(source_id) and source_id not in prepared.get("claimed_manual_source_ids", [])):
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
            binding = prepared.get("source_bindings", {}).get(source_id)
            if (not isinstance(binding, list) or len(binding) != 2
                    or binding[0] not in {"REPLY", "SOCIAL_EVENT"} or not binding[1]):
                raise RoutineSourceBindingError("routine_initial_source_binding_missing")
            bindings.append(tuple(binding))
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
