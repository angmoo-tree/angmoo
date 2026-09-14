"""Construct existing canonical evidence readers with the caller's Session."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domains.characters.models import Character
from app.domains.chat.contracts.evidence_reads import RelationshipEvidenceState
from app.domains.chat.contracts.today_sns_activity import TodaySnsActivityReaderPort
from app.runtime.memory.composition import memory_repository as SqlAlchemyMemoryRepository
from app.domains.memory.contracts.inspector import MemoryItemDetail
from app.domains.memory.service.inspector import MemoryReadService
from app.domains.memory.contracts.scope import MemoryScope
from app.domains.memory.contracts.source_evidence import MemorySourceEvidenceReaderPort
from app.domains.relationships.models.social import (
    RelationshipState,
)
from app.domains.world_characters.models import WorldCharacter
from app.runtime.memory.source_composition import source_evidence_reader as SqlAlchemyMemorySourceEvidenceReader
from app.runtime.social.today_activity import today_social_activity_reader as SqlAlchemyTodaySocialActivityReader


def source_reader(db: Session) -> MemorySourceEvidenceReaderPort:
    return SqlAlchemyMemorySourceEvidenceReader(db)


def today_reader(db: Session) -> TodaySnsActivityReaderPort:
    return SqlAlchemyTodaySocialActivityReader(db)


def memory_detail(
    db: Session,
    source_reader: MemorySourceEvidenceReaderPort,
    scope: MemoryScope,
    *,
    item_id: str,
) -> MemoryItemDetail:
    return MemoryReadService(SqlAlchemyMemoryRepository(db), source_reader).detail(
        scope, item_id=item_id
    )


def relationship_state(
    db: Session, source_id: object
) -> RelationshipEvidenceState | None:
    return db.get(RelationshipState, source_id)


def social_relationship_current(db: Session, scope: MemoryScope, locator: dict) -> bool:
    from app.contracts.read_deadline import bounded_read
    from app.domains.relationships.contracts.graph_recall import GraphRecallQuery, GraphRecallScope, GraphRecallOperation
    from app.domains.relationships.service.graph_recall import GraphRecallService
    from app.runtime.graph_projection.relationship_graph_read import SqlAlchemyRelationshipGraphReadGateway
    if locator.get("actor_world_character_id") != scope.subject_world_character_id:
        return False
    gateway = SqlAlchemyRelationshipGraphReadGateway(db)
    try:
        with bounded_read(1):
            result = GraphRecallService(gateway).execute(GraphRecallQuery(
                GraphRecallOperation.DIRECT_RELATIONSHIP,
                GraphRecallScope(scope.owner_id, scope.world_id, scope.subject_world_character_id),
                counterpart_world_character_id=locator.get("target_world_character_id"), limit=1))
        return any(row.relationship_state_id == locator.get("source_id")
                   and str(row.relationship_version) == locator.get("source_revision") for row in result.relationships)
    except Exception:
        return False
    finally:
        gateway.close_graph_repository()


def world_character_name(
    db: Session,
    world_character_id: str | None,
    *,
    world_id: str,
) -> str | None:
    if world_character_id is None:
        return None
    return db.scalar(
        select(Character.name)
        .join(WorldCharacter, WorldCharacter.character_id == Character.id)
        .where(
            WorldCharacter.id == world_character_id,
            WorldCharacter.world_id == world_id,
        )
    )
