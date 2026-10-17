"""Owner-facing evidence reads revalidate visibility, revision and World scope."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy.orm import Session

from app.domains.chat import models, schemas
from app.domains.chat.contracts import ResponseRequestState
from app.domains.chat.contracts.context import ChatUser
from app.domains.chat.contracts.evidence_reads import ChatEvidenceReads
from app.domains.chat.contracts.evidence_bundle import validate_evidence_time_provenance
from app.domains.chat.exceptions import MessageNotFoundError
from app.domains.chat.repository.response_lifecycle import (
    SqlAlchemyResponseLifecycleRepository,
)
from app.domains.chat.service.threads import ThreadService
from app.domains.memory.contracts.inspector import MemoryEvidenceAvailability
from app.domains.memory.contracts.inspector import MemoryLifecycle
from app.domains.memory.service.management import MemoryNotFoundError
from app.domains.memory.contracts.scope import MemoryScope
from app.domains.memory.contracts.source_evidence import MemorySourceEvidenceReaderPort
from app.domains.memory.contracts.provenance import MemorySourceTypeV1
from app.domains.chat.contracts.relationship_evidence import (
    DELIVERY_KEY, RelationshipEvidenceBinding, RelationshipCurrentRead, RelationshipEvidenceRead,
)
from app.domains.chat.relationship_evidence_policy import (
    validate_delivery, historical_read, restore_legacy_relationships,
)


class EvidenceService:
    def __init__(self, thread_service: ThreadService, reads: ChatEvidenceReads, *, image_reader=None) -> None:
        self.thread_service = thread_service
        self.reads = reads
        self.image_reader = image_reader

    def get_world_response_evidence(
        self,
        db: Session,
        user: ChatUser,
        world_id: str,
        thread_id: str,
        request_id: str,
    ) -> schemas.WorldChatEvidenceRead:
        self.thread_service._require_world_chat_owner_scope(db, user.id, world_id)
        thread = self.thread_service._get_owned_world_thread(
            db, user, world_id, thread_id
        )
        self.thread_service._world_thread_read(db, thread, include_messages=False)
        row = db.get(models.ChatResponseRequest, request_id)
        if (
            row is None
            or row.thread_id != thread.id
            or row.state != ResponseRequestState.COMMITTED.value
            or (row.committed_assistant_message_id is None)
        ):
            raise MessageNotFoundError("확인할 근거를 찾을 수 없습니다.")
        record = SqlAlchemyResponseLifecycleRepository(db).get_request(request_id)
        metadata = record.response_metadata
        capability = metadata.get("evidence_capability")
        snapshot = metadata.get("_evidence_inspector_v1")
        current_snapshot = metadata.get("_social_context_inspector_v1")
        current_raw = current_snapshot.get("items", []) if isinstance(current_snapshot, dict) else []
        if not isinstance(current_raw, list):
            current_raw = []
        if isinstance(current_raw, list) and current_raw:
            capability = "degraded" if capability == "degraded" else "available"
        if capability not in {"available", "degraded"} or not isinstance(
            snapshot, dict
        ):
            raise MessageNotFoundError("확인할 근거를 찾을 수 없습니다.")
        raw_items = snapshot.get("items")
        if snapshot.get("version") != "evidence-inspector.v1" or not isinstance(
            raw_items, list
        ):
            raise MessageNotFoundError("확인할 근거를 찾을 수 없습니다.")
        scope = MemoryScope(
            owner_id=user.id,
            world_id=world_id,
            subject_world_character_id=thread.responding_world_character_id,
        )
        source_reader = self.reads.source_reader(db)
        relationship_reads, read_limitations = self._relationship_reads(
            db, scope, thread, record, snapshot, current_snapshot)
        items = [
            self._chat_evidence_item(db, scope, raw, source_reader=source_reader, thread_id=thread.id,
                relationship_read=relationship_reads.get(("items", raw.get("ref"))))
            for raw in raw_items[:12]
            if isinstance(raw, dict)
        ]
        current_items = []
        for raw in current_raw[:12]:
            if not isinstance(raw, dict):
                continue
            item = self._chat_evidence_item(db, scope, raw, source_reader=source_reader,
                relationship_read=relationship_reads.get(("current_context", raw.get("ref"))))
            current_items.append(item)
        visible_items = items + current_items
        if any(item.kind != "graph_relationship" and item.availability != "available" for item in visible_items):
            read_limitations.add("current_unavailable")
        current_capability = (
            "available"
            if capability == "available"
            and visible_items
            and all((item.availability == "available" for item in visible_items))
            else "degraded"
        )
        return schemas.WorldChatEvidenceRead(
            request_id=request_id,
            route=str(metadata.get("route") or "unknown"),
            retrieval_outcome=str(metadata.get("retrieval_outcome") or "unknown"),
            capability=current_capability,
            items=items,
            current_context=current_items,
            retrieval_limitations=_retrieval_limitations(metadata),
            read_limitations=sorted(read_limitations),
        )

    def _relationship_reads(self, db, scope, thread, record, snapshot, current_snapshot):
        current_items = current_snapshot.get("items", []) if isinstance(current_snapshot, dict) else []
        sections = {"items": snapshot["items"][:12],
            "current_context": current_items[:12] if isinstance(current_items, list) else []}
        raw_relations = {(section, raw["ref"]): raw for section, values in sections.items()
            for raw in values if isinstance(raw, dict) and raw.get("kind") == "graph_relationship" and isinstance(raw.get("ref"), str)}
        if not raw_relations:
            return {}, set()
        binding = RelationshipEvidenceBinding.for_request(record, owner_id=scope.owner_id,
            world_id=scope.world_id, actor_id=scope.subject_world_character_id,
            requester_id=thread.requester_world_character_id)
        try:
            if DELIVERY_KEY in record.response_metadata:
                proof = validate_delivery(record.response_metadata[DELIVERY_KEY], binding=binding,
                    capture=record.node_state.get("_relationship_delivery_capture"), inspector=snapshot,
                    current_inspector=current_snapshot)
                delivered = {(item.section, item.reference): item for item in proof.items}
            else:
                reader = getattr(self.reads, "legacy_relationship_manifest", None)
                manifest = reader(db, scope, record) if reader else None
                delivered = restore_legacy_relationships(manifest, snapshot, binding)
        except (ValueError, TypeError, KeyError, AttributeError):
            delivered = {}
        locators = tuple(raw_relations[key]["locator"] for key in delivered)
        current = {}
        if locators:
            reader = getattr(self.reads, "relationships_current", None)
            try:
                current = reader(db, scope, locators) if reader else {}
            except Exception:
                current = {}
        reads, reasons = {}, set()
        for key, raw in raw_relations.items():
            item = delivered.get(key)
            value = RelationshipEvidenceRead(reason="historical_unverified") if item is None else historical_read(
                item, current.get(item.state_id, RelationshipCurrentRead(False, reason="read_unavailable")))
            if value.reason:
                reasons.add(value.reason)
            reads[key] = (value, None if value.reason else item.projection)
        return reads, reasons

    def _chat_evidence_item(
        self,
        db: Session,
        scope: MemoryScope,
        raw: dict[str, Any],
        *,
        source_reader: MemorySourceEvidenceReaderPort,
        thread_id: str | None = None,
        relationship_read=None,
    ) -> schemas.WorldChatEvidenceItemRead:
        kind = raw.get("kind")
        if kind not in {
            "canonical_source",
            "graph_relationship",
            "graph_event",
            "today_sns_activity",
            "episode_memory",
            "current_image_analysis",
        }:
            raise MessageNotFoundError("근거 형식이 올바르지 않습니다.")
        reference = raw.get("ref")
        text = raw.get("text")
        locator = raw.get("locator")
        if not isinstance(reference, str) or not isinstance(text, str):
            raise MessageNotFoundError("근거 형식이 올바르지 않습니다.")
        occurred_at = _optional_datetime(raw.get("occurred_at"))
        availability = "unavailable"
        href = None
        related_name = None
        direction = None
        episode = None
        relationship_change = None
        relationship_projection = None
        label = {
            "canonical_source": "기억 근거",
            "graph_relationship": "답변 당시 관계",
            "graph_event": "관계 사건",
            "today_sns_activity": "오늘 SNS 활동",
            "episode_memory": "상황 기억",
            "current_image_analysis": "첨부 이미지의 실제 분석",
        }[kind]
        if not isinstance(locator, dict):
            return schemas.WorldChatEvidenceItemRead(
                reference=reference,
                kind=kind,
                label=label,
                excerpt=None,
                occurred_at=occurred_at,
                availability=availability,
                related_character=None,
                direction=None,
                canonical_href=None,
            )
        locator_kind = locator.get("kind")
        if kind == "today_sns_activity" and locator_kind == "canonical_source":
            current = None
            if occurred_at is not None and isinstance(locator.get("source_id"), str):
                try:
                    read = self.reads.today_reader(db).read(
                        owner_id=scope.owner_id,
                        world_id=scope.world_id,
                        subject_world_character_id=scope.subject_world_character_id,
                        started_at=occurred_at - timedelta(seconds=1),
                        complete_through=occurred_at + timedelta(seconds=1),
                    )
                    current = next(
                        (
                            item
                            for item in read.records
                            if item.source_id == locator["source_id"]
                            and item.source_revision == locator.get("source_revision")
                        ),
                        None,
                    )
                except Exception:
                    current = None
            if current is not None:
                availability = "available"
                occurred_at = current.occurred_at
                if current.source_post_id is not None:
                    href = f"/worlds/{scope.world_id}/posts/{current.source_post_id}"
                related_id, direction = _related_direction(
                    scope.subject_world_character_id,
                    current.actor_world_character_id,
                    current.counterpart_world_character_id,
                    current.counterpart_world_character_id,
                )
                related_name = self.reads.world_character_name(
                    db, related_id, world_id=scope.world_id
                )
        elif locator_kind == "canonical_source":
            try:
                source_type = MemorySourceTypeV1(str(locator.get("source_type")))
            except ValueError:
                source_type = None
            source_id = locator.get("source_id")
            fresh = (
                None
                if source_type is None or not isinstance(source_id, str)
                else source_reader.read_evidence(
                    scope=scope, source_type=source_type, source_id=source_id
                )
            )
            source_revision = locator.get("source_revision")
            if fresh is not None and (
                fresh.source_world_id == scope.world_id
                and (source_revision is None or fresh.source_digest == source_revision)
                and fresh.successful
                and fresh.visible
                and fresh.observed_by_subject
                and fresh.membership_active
                and (not fresh.blocked)
            ):
                availability = "available"
                occurred_at = fresh.source_created_at
                if kind != "today_sns_activity":
                    label = _chat_source_label(source_type)
                related_id, direction = _related_direction(
                    scope.subject_world_character_id,
                    fresh.actor_world_character_id,
                    fresh.target_world_character_id,
                    fresh.counterpart_world_character_id,
                )
                related_name = self.reads.world_character_name(
                    db, related_id, world_id=scope.world_id
                )
                if source_type in {MemorySourceTypeV1.POST, MemorySourceTypeV1.REPLY}:
                    href = f"/worlds/{scope.world_id}/posts/{source_id}"
                elif (
                    source_type
                    in {
                        MemorySourceTypeV1.CHAT_MESSAGE,
                        MemorySourceTypeV1.OWNER_MEMORY_REQUEST,
                    }
                    and fresh.thread_id
                ):
                    href = f"/worlds/{scope.world_id}/chat/{fresh.thread_id}"
            elif (
                fresh is not None
                and source_type in {MemorySourceTypeV1.POST, MemorySourceTypeV1.REPLY}
                and (not fresh.visible)
            ):
                availability = "deleted"
        elif locator_kind == "image_asset":
            if self.image_reader is not None and thread_id and self.image_reader(db, scope.owner_id, thread_id, locator):
                availability = "available"
                href = None  # Pixel reads require runtime authentication; the inspector shows the verified observation.
        elif locator_kind == "memory_item":
            memory_id = locator.get("source_id")
            detail = None
            if isinstance(memory_id, str):
                try:
                    detail = self.reads.memory_detail(
                        db, source_reader, scope, item_id=memory_id
                    )
                except MemoryNotFoundError:
                    detail = None
            if detail is not None:
                expected_revision = locator.get("source_revision")
                revision_matches = (
                    expected_revision is None
                    or str(detail.item.version) == expected_revision
                )
                has_current_evidence = any(
                    (
                        evidence.availability is MemoryEvidenceAvailability.AVAILABLE
                        for evidence in detail.evidence
                    )
                )
                if (
                    detail.lifecycle is MemoryLifecycle.ACTIVE
                    and revision_matches
                    and (has_current_evidence or kind == "episode_memory")
                ):
                    availability = "available"
                    href = f"/memory?world={scope.world_id}&subject={scope.subject_world_character_id}&memory={memory_id}"
                    if kind == "episode_memory":
                        reader = getattr(self.reads, "memory_episode_receipt", None)
                        receipt = None if reader is None else reader(db, scope, item_id=memory_id, text=text)
                        if receipt is None:
                            availability, href = "unavailable", None
                        else:
                            text, episode = receipt
                label = "저장된 기억"
                related_name = self.reads.world_character_name(
                    db,
                    detail.item.counterpart_world_character_id,
                    world_id=scope.world_id,
                )
                direction = "contextual" if related_name else None
        elif locator_kind == "graph_relationship":
            actor = locator.get("actor_world_character_id")
            target = locator.get("target_world_character_id")
            value, projection = relationship_read or (RelationshipEvidenceRead(reason="historical_unverified"), None)
            if value.change is not None:
                availability = "available"
                relationship_change, relationship_projection = value.change, projection
                related_name = value.name
                _, direction = _related_direction(scope.subject_world_character_id, actor, target, None)
                # Private social JSON carries IDs. Expose only the verified safe projection.
                text = (projection.get("perception") or "") if projection is not None else value.excerpt or ""
        return schemas.WorldChatEvidenceItemRead(
            reference=reference,
            kind=kind,
            label=label,
            excerpt=text[:500] if availability == "available" else None,
            occurred_at=occurred_at,
            availability=availability,
            related_character=related_name,
            direction=direction,
            canonical_href=href,
            episode=episode,
            relationship_change=relationship_change,
            relationship_projection=relationship_projection,
            time_provenance=_time_provenance(raw) if availability == "available" else None,
        )


def _time_provenance(raw):
    value = raw.get("time_provenance")
    if value is None:
        return None  # Historical evidence has no verified time semantics.
    try:
        validate_evidence_time_provenance(value)
        return schemas.EvidenceTimeRead.model_validate(value)
    except (ValueError, TypeError):
        return schemas.EvidenceTimeRead(kind="unknown")


def _optional_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return (
        parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)
    )


def _retrieval_limitations(metadata):
    from app.domains.chat.contracts.response_request import RetrievalAxis, DegradedReason
    if "partial_axes" not in metadata or "degraded_reason" not in metadata:
        return None
    axes, reason = metadata["partial_axes"], metadata["degraded_reason"]
    if (type(axes) is not list or len(axes) > 3 or any(type(axis) is not str for axis in axes) or len(set(axes)) != len(axes)
            or any(axis not in {value.value for value in RetrievalAxis} for axis in axes)
            or (reason is not None and reason not in {value.value for value in DegradedReason})):
        return None
    return {"partial_axes": axes, "degraded_reason": reason}


def _related_direction(
    subject: str, actor: str | None, target: str | None, fallback: str | None
):
    if actor == subject:
        return target or fallback, "outgoing"
    if target == subject:
        return actor or fallback, "incoming"
    return fallback, "contextual" if fallback else None


def _chat_source_label(source_type: MemorySourceTypeV1) -> str:
    return {
        MemorySourceTypeV1.CHAT_MESSAGE: "대화",
        MemorySourceTypeV1.OWNER_MEMORY_REQUEST: "기억 요청",
        MemorySourceTypeV1.POST: "지저귐",
        MemorySourceTypeV1.REPLY: "대꾸",
        MemorySourceTypeV1.REACTION: "좋아요",
        MemorySourceTypeV1.SOCIAL_EVENT: "World 사건",
        MemorySourceTypeV1.ACTIVITY_EVENT: "활동",
        MemorySourceTypeV1.RELATIONSHIP_EVENT: "관계 변화",
        MemorySourceTypeV1.JOINT_COMMITMENT: "함께한 약속",
    }[source_type]
