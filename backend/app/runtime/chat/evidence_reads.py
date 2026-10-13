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
    from app.runtime.memory.situation_detail import situation_detail
    return MemoryReadService(SqlAlchemyMemoryRepository(db), source_reader,
        situation_detail_reader=lambda scope, item_id, now: situation_detail(db, scope, item_id, now)).detail(
        scope, item_id=item_id
    )


def relationship_state(
    db: Session, source_id: object
) -> RelationshipEvidenceState | None:
    return db.get(RelationshipState, source_id)


def memory_episode_receipt(db, scope, *, item_id, text):
    from datetime import UTC, datetime
    from app.runtime.memory.episode_inspector import episode_receipt_view
    return episode_receipt_view(db, scope, item_id, datetime.now(UTC), text)


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


def relationships_current(db: Session, scope: MemoryScope, locators: tuple[dict, ...]):
    """Fresh canonical authorization/facts in the caller's transaction, no graph I/O."""
    from dataclasses import replace
    from app.contracts.read_deadline import bounded_read
    from app.domains.chat.contracts.relationship_evidence import RelationshipCurrentRead
    from app.domains.relationships.contracts.graph_recall import GraphRecallScope
    from app.domains.relationships.contracts.social_context import CanonicalSocialContextReference
    from app.domains.relationships.service.social_context_validation import SocialContextValidationService
    from app.runtime.graph_projection.relationship_graph_read import SqlAlchemyRelationshipGraphReadGateway
    from app.runtime.chat.scope_queries import world_chat_roles

    if len(locators) > 24:
        raise ValueError("chat_relationship_read_limit")
    denied = {str(row.get("source_id")): RelationshipCurrentRead(False, reason="current_unavailable") for row in locators}
    valid = {row["source_id"]: row for row in locators if row.get("actor_world_character_id") == scope.subject_world_character_id
        and isinstance(row.get("source_id"), str) and isinstance(row.get("target_world_character_id"), str)}
    try:
        with bounded_read(2):
            identities = {scope.subject_world_character_id, *(row["target_world_character_id"] for row in valid.values())}
            roles = world_chat_roles(db, identities, world_id=scope.world_id)
            if scope.subject_world_character_id not in roles:
                return denied
            reader = SocialContextValidationService(SqlAlchemyRelationshipGraphReadGateway(db))
            graph_scope = GraphRecallScope(scope.owner_id, scope.world_id, scope.subject_world_character_id)
            targets = tuple(dict.fromkeys(row["target_world_character_id"] for row in valid.values()))
            for offset in range(0, len(targets), 12):
                references = tuple(CanonicalSocialContextReference(target) for target in targets[offset:offset+12])
                facts = reader._canonical(graph_scope, references)
                # Chat's existing role filter permits an inactive owner-controlled persona.
                # Only already-authorized roles are normalized, never membership/deletion/block facts.
                nodes = {key: replace(node, world_character_status="active")
                    if key in roles and roles[key][0].control_mode == "owner_controlled" else node
                    for key, node in facts.nodes.items()}
                facts = replace(facts, nodes=nodes)
                for state_id, locator in valid.items():
                    target = locator["target_world_character_id"]
                    if target not in roles or target not in targets[offset:offset+12]:
                        continue
                    try:
                        item = reader._item(graph_scope, facts, CanonicalSocialContextReference(target, state_id))
                    except ValueError:
                        continue
                    denied[state_id] = RelationshipCurrentRead(True, item.relationship)
    except Exception:
        return {key: RelationshipCurrentRead(False, reason="read_unavailable") for key in denied}
    return denied


def legacy_relationship_manifest(db: Session, scope: MemoryScope, request):
    """Read retained, bound delivery material; processing state isn't authorization."""
    from app.domains.memory.models.activity_situation import MemorySituationManifest, MemorySituationReceipt
    from app.domains.memory.models.items import MemoryScopeSettingModel as MemoryScopeSetting
    from app.domains.memory.contracts.activity_situation import DeliveredInputManifest, stable_digest
    row = db.scalar(select(MemorySituationManifest)
        .join(MemorySituationReceipt, MemorySituationReceipt.manifest_id == MemorySituationManifest.id)
        .join(MemoryScopeSetting, MemoryScopeSetting.id == MemorySituationManifest.scope_setting_id)
        .where(MemoryScopeSetting.owner_id == scope.owner_id, MemoryScopeSetting.world_id == scope.world_id,
            MemoryScopeSetting.subject_world_character_id == scope.subject_world_character_id,
            MemorySituationManifest.call_identity == f"chat:{request.request_scope_hash}",
            MemorySituationReceipt.lane == "chat", MemorySituationReceipt.logical_activity_id == request.response_slot_id,
            MemorySituationReceipt.target_key == request.response_slot_id).limit(1))
    if row is None or stable_digest(row.payload) != row.content_digest:
        return None
    try:
        manifest = DeliveredInputManifest.from_dict(row.payload)
        if manifest.version == 2 and manifest.private_thread_id == request.thread_id and manifest.snapshot.scope == scope:
            return manifest
    except (ValueError, KeyError, TypeError):
        pass
    return None
