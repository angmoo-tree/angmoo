"""Owner diagnostics, current source exclusion and canonical response assembly."""
from __future__ import annotations
from datetime import UTC, datetime
from sqlalchemy.orm import Session
from app.config import Settings, settings
from app.domains.relationships import models, schemas
from app.domains.relationships.contracts.diagnostics import DiagnosticsOwner, DiagnosticsReferences
from app.domains.relationships.contracts.graph_read import GraphProvider
from app.domains.relationships.exceptions import SocialMemoryNotFoundError, SocialMemoryForbiddenError
from app.domains.relationships.repository import diagnostics as social_memory_crud
from app.domains.relationships.repository import projection_state as graph_projection_crud
from app.domains.relationships.service import graph_read


def _pair_blocked(references: DiagnosticsReferences, *, event: models.SocialEvent) -> bool:
    if event.target_world_character_id is None:
        return False
    return references.pair_blocked(
        world_id=event.world_id,
        actor_id=event.actor_world_character_id,
        target_id=event.target_world_character_id,
    )


def _source_status(
    db: Session,
    *,
    references: DiagnosticsReferences,
    event: models.SocialEvent,
    evidence: models.SocialEventEvidence,
) -> tuple[str, str | None]:
    if event.retrieval_status != "eligible":
        return "excluded", event.invalidation_reason or "manual_exclusion"
    for world_character_id in (
        event.actor_world_character_id,
        event.target_world_character_id,
    ):
        if world_character_id is None:
            continue
        reason = references.world_character_status(
            world_id=event.world_id, world_character_id=world_character_id
        )
        if reason is not None:
            return "excluded", reason
    if _pair_blocked(references, event=event):
        return "excluded", "blocked"
    post_id = (
        evidence.source_post_id
        or evidence.target_post_id
        or evidence.root_post_id
        or (evidence.source_object_id if evidence.source_object_type == "post" else None)
    )
    if post_id is None:
        return "available", None
    post = references.get_post(post_id)
    if post is None or post.deleted_at is not None:
        return "excluded", "source_deleted"
    if post.world_id != event.world_id:
        return "excluded", "world_mismatch"
    if post.report_hidden_at is not None or post.visibility != "public":
        return "excluded", "source_hidden"
    return "available", None


def get_owner_diagnostics(
    db: Session,
    *,
    character_id: str,
    world_id: str,
    user: DiagnosticsOwner,
    references: DiagnosticsReferences,
    config: Settings = settings,
) -> schemas.SocialMemoryDiagnosticsRead:
    character = references.get_character(character_id)
    if character is None or character.deleted_at is not None:
        raise SocialMemoryNotFoundError(character_id)
    if character.owner_id != user.id:
        raise SocialMemoryForbiddenError(character_id)
    world_character = references.find_world_character(world_id=world_id, character_id=character_id)
    if world_character is None:
        raise SocialMemoryNotFoundError(character_id)

    events = social_memory_crud.list_recent_events(
        db,
        world_id=world_id,
        world_character_id=world_character.id,
    )
    evidence_by_event = social_memory_crud.list_event_evidence(
        db, [event.id for event in events]
    )
    event_reads = []
    for event in events:
        evidence_reads = []
        effective_retrieval_status = event.retrieval_status
        for evidence in evidence_by_event.get(event.id, []):
            source_status, reason = _source_status(db, references=references, event=event, evidence=evidence)
            if source_status == "excluded":
                effective_retrieval_status = "excluded"
            evidence_reads.append(
                schemas.SocialEventEvidenceRead(
                    evidence_kind=evidence.evidence_kind,
                    source_object_type=evidence.source_object_type,
                    source_object_id=evidence.source_object_id,
                    root_post_id=evidence.root_post_id,
                    source_post_id=evidence.source_post_id,
                    target_post_id=evidence.target_post_id,
                    source_status=source_status,
                    exclusion_reason=reason,
                )
            )
        event_reads.append(
            schemas.SocialEventRead(
                id=event.id,
                world_id=event.world_id,
                actor_world_character_id=event.actor_world_character_id,
                target_world_character_id=event.target_world_character_id,
                event_type=event.event_type,
                occurred_at=event.occurred_at,
                retrieval_status=effective_retrieval_status,
                evidence=evidence_reads,
            )
        )

    def relationship_read(row: models.RelationshipState) -> schemas.RelationshipStateRead:
        return schemas.RelationshipStateRead.model_validate(row)

    joint_reads = []
    for activity, participants in references.list_active_joint_activities(
        world_id=world_id,
        world_character_id=world_character.id,
    ):
        joint_reads.append(
            schemas.JointActivityRead(
                id=activity.id,
                proposal_id=activity.proposal_id,
                activity_seed=activity.activity_seed,
                place_key=activity.place_key,
                scheduled_local_date=activity.scheduled_local_date,
                target_daypart=activity.target_daypart,
                timezone_snapshot=activity.timezone_snapshot,
                status=activity.status,
                opening_post_id=activity.opening_post_id,
                opened_by_world_character_id=activity.opened_by_world_character_id,
                started_at=activity.started_at,
                completed_at=activity.completed_at,
                participants=[
                    schemas.JointActivityParticipantRead.model_validate(row)
                    for row in participants
                ],
            )
        )

    outgoing_rows = social_memory_crud.list_relationships(
        db,
        world_id=world_id,
        world_character_id=world_character.id,
        outgoing=True,
    )
    incoming_rows = social_memory_crud.list_relationships(
        db,
        world_id=world_id,
        world_character_id=world_character.id,
        outgoing=False,
    )
    counts = graph_projection_crud.world_counts(db, world_id=world_id)
    oldest_pending = counts.oldest_pending_at
    if oldest_pending is not None:
        if oldest_pending.tzinfo is None:
            oldest_pending = oldest_pending.replace(tzinfo=UTC)
        oldest_pending_age = max(
            0.0,
            (datetime.now(UTC) - oldest_pending).total_seconds(),
        )
    else:
        oldest_pending_age = None

    graph_provider: GraphProvider = "ladybug"
    graph_gateway = references.graph_gateway(
        graph_provider=graph_provider,
    )
    graph = graph_read.get_owner_relationship_graph(
        graph_gateway,
        character_id=character_id,
        world_id=world_id,
        owner_id=user.id,
        view="neighborhood",
        depth=1,
        limit=20,
        graph_projection_enabled=config.graph_projection_enabled,
        graph_provider=graph_provider,
    )
    latest_relationship_version_parity: bool | None = None
    if graph.meta.source == "ladybug" and not graph.meta.truncated:
        graph_versions = {
            edge.relationship_state_id: edge.relationship_version
            for edge in graph.edges
        }
        canonical_rows = [*outgoing_rows, *incoming_rows]
        latest_relationship_version_parity = all(
            graph_versions.get(row.id) == row.version
            for row in canonical_rows
        )

    return schemas.SocialMemoryDiagnosticsRead(
        world_id=world_id,
        world_character_id=world_character.id,
        recent_events=event_reads,
        outgoing_relationships=[relationship_read(row) for row in outgoing_rows],
        incoming_relationships=[relationship_read(row) for row in incoming_rows],
        open_proposals=[
            schemas.ActivityProposalRead.model_validate(row)
            for row in social_memory_crud.list_open_proposals(
                db,
                world_id=world_id,
                world_character_id=world_character.id,
            )
        ],
        active_joint_activities=joint_reads,
        graph_outbox_pending_count=counts.pending,
        graph_outbox_processing_count=counts.processing,
        graph_outbox_dead_count=counts.dead,
        graph_oldest_pending_age_seconds=oldest_pending_age,
        graph_last_succeeded_at=counts.last_succeeded_at,
        relationship_graph_status=graph.meta.graph_status,
        latest_relationship_version_parity=latest_relationship_version_parity,
        graph_replay_active=counts.active_replay,
    )
