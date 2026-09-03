"""SQLAlchemy/provider composition for World Chat response generation."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, settings
from app.domains.chat.api import schemas
from app.domains.chat.application import (
    BothRetrievalWorkflowCoordinator,
    CanonicalRetrievalPlanningService,
    CharacterResponseGenerationService,
    EvidenceBundleAssembler,
    GenerationLifecycleService,
    GraphRetrievalPlanningService,
    ResponseGenerationWorkflowService,
    ResponseWorkflowCommand,
    RetrievalRoutingService,
)
from app.domains.chat.domain import (
    CHAT_GENERATION_STREAM_VERSION,
    CreateResponseRequest,
    GenerationEvent,
    GenerationEventType,
    GenerationFence,
    ResponseRequestState,
    ResponseTerminalReason,
    TERMINAL_STATES,
    build_request_scope_hash,
)
from app.domains.chat.domain.errors import (
    MessageCredentialInvalidError,
    MessageCredentialRequiredError,
    MessageForbiddenError,
    MessageInFlightError,
    MessageNotFoundError,
    MessageValidationError,
)
from app.domains.chat.infrastructure import SqlAlchemyResponseLifecycleRepository
from app.domains.chat.ports import (
    CharacterResponseContextMessage,
    CharacterResponseProfile,
    RetrievalPreflightCommand,
    RetrievalRouterContextMessage,
)
from app.domains.identity.public import CredentialMaterial
from app.domains.memory.infrastructure import SqlAlchemyMemoryRepository
from app.domains.memory.public import (
    CanonicalRetrievalPlanExecutor,
    MemoryEvidenceAvailability,
    MemoryLifecycle,
    MemoryNotFoundError,
    MemoryReadService,
    MemoryScope,
    MemorySourceTypeV1,
)
from app.domains.relationships.infrastructure.sqlalchemy_social_models import (
    RelationshipState,
)
from app.domains.relationships.public import (
    GraphRecallService,
    GraphRetrievalPlanExecutor,
)
from app.integrations.llm import (
    DirectLlmCanonicalRetrievalPlannerProvider,
    DirectLlmCharacterResponseGenerator,
    DirectLlmGraphRetrievalPlannerProvider,
    DirectLlmRetrievalRouterProvider,
)
from app.runtime.chat import model_bindings as models
from app.runtime.chat.memory_producer import SqlAlchemySuccessfulChatMemoryProducer
from app.runtime.chat import sqlalchemy_service
from app.runtime.chat.retrieval_policy import SqlAlchemyRetrievalPolicyResolver
from app.runtime.memory.sqlalchemy_source_reader import (
    SqlAlchemyMemorySourceEvidenceReader,
)
from app.runtime.graph_projection.relationship_graph_read import (
    SqlAlchemyRelationshipGraphReadGateway,
)


RESPONSE_REQUEST_DEADLINE_SECONDS = 180
RESPONSE_CONTEXT_MESSAGE_LIMIT = 20
RESPONSE_CONTEXT_CHAR_LIMIT = 8_000


class SqlAlchemyResponseWorkflowUnitOfWork:
    def __init__(self, session: Session) -> None:
        self._session = session

    def checkpoint(self) -> None:
        self._session.commit()

    def rollback(self) -> None:
        self._session.rollback()


def accept_world_message(
    db: Session,
    user: models.User,
    world_id: str,
    thread_id: str,
    data: schemas.WorldChatMessageCreate,
) -> schemas.WorldChatMessageAcceptRead:
    thread = _mutation_thread(db, user, world_id, thread_id)
    content = data.content.strip()
    if not content:
        raise MessageValidationError("메시지 내용을 입력해 주세요.")
    idempotency_key = data.idempotency_key.strip()
    if len(idempotency_key) < 16:
        raise MessageValidationError("message_idempotency_key_invalid")

    existing = db.scalar(
        select(models.ChatResponseRequest).where(
            models.ChatResponseRequest.thread_id == thread.id,
            models.ChatResponseRequest.idempotency_key == idempotency_key,
        )
    )
    if existing is not None:
        message = db.get(models.MessageMessage, existing.user_message_id)
        if message is None or message.content != content:
            raise MessageValidationError("message_idempotency_conflict")
        return schemas.WorldChatMessageAcceptRead(
            outcome="replayed",
            user_message=schemas.MessageMessageRead.model_validate(message),
            response_request=_request_read(db, existing),
        )

    if _active_request(db, thread.id) is not None:
        raise MessageInFlightError("이미 답장을 만들고 있어요.")

    selected_model = sqlalchemy_service.resolve_world_thread_response_model(
        db, user, thread
    )

    now = datetime.now(UTC)
    message = models.MessageMessage(
        thread_id=thread.id,
        role="user",
        content=content,
        model=None,
        status="ok",
    )
    db.add(message)
    db.flush()
    thread.last_message_at = now
    request_id = f"request-{uuid4().hex}"
    generation_id = f"generation-{uuid4().hex}"
    response_slot_id = f"response-{uuid4().hex}"
    scope_hash = build_request_scope_hash(
        owner_id=user.id,
        world_id=world_id,
        thread_id=thread.id,
        user_message_id=message.id,
        requester_world_character_id=thread.requester_world_character_id or "",
        responding_world_character_id=thread.responding_world_character_id or "",
    )
    lifecycle = GenerationLifecycleService(SqlAlchemyResponseLifecycleRepository(db))
    record = lifecycle.accept(
        CreateResponseRequest(
            request_id=request_id,
            thread_id=thread.id,
            user_message_id=message.id,
            response_slot_id=response_slot_id,
            request_scope_hash=scope_hash,
            idempotency_key=idempotency_key,
            generation_id=generation_id,
            attempt_number=1,
            selected_model=selected_model,
            deadline_at=now + timedelta(seconds=RESPONSE_REQUEST_DEADLINE_SECONDS),
        )
    )
    db.commit()
    db.refresh(message)
    return schemas.WorldChatMessageAcceptRead(
        outcome="accepted",
        user_message=schemas.MessageMessageRead.model_validate(message),
        response_request=_record_read(db, record),
    )


def retry_world_response(
    db: Session,
    user: models.User,
    world_id: str,
    thread_id: str,
    data: schemas.WorldChatRetryCreate,
) -> schemas.WorldChatMessageAcceptRead:
    thread = _mutation_thread(db, user, world_id, thread_id)
    idempotency_key = data.idempotency_key.strip()
    existing = db.scalar(
        select(models.ChatResponseRequest).where(
            models.ChatResponseRequest.thread_id == thread.id,
            models.ChatResponseRequest.idempotency_key == idempotency_key,
        )
    )
    if existing is not None:
        if existing.retry_of_request_id != data.failed_request_id:
            raise MessageValidationError("retry_idempotency_conflict")
        message = db.get(models.MessageMessage, existing.user_message_id)
        if message is None:
            raise MessageNotFoundError("원래 메시지를 찾을 수 없습니다.")
        return schemas.WorldChatMessageAcceptRead(
            outcome="replayed",
            user_message=schemas.MessageMessageRead.model_validate(message),
            response_request=_request_read(db, existing),
        )

    prior = db.get(models.ChatResponseRequest, data.failed_request_id)
    latest = _latest_request_row(db, thread.id)
    if prior is None or prior.thread_id != thread.id or latest is None:
        raise MessageNotFoundError("다시 시도할 응답을 찾을 수 없습니다.")
    if latest.request_id != prior.request_id:
        raise MessageValidationError("latest_retryable_response_required")
    if (
        prior.state not in {state.value for state in TERMINAL_STATES}
        or not prior.retryable
        or prior.committed_assistant_message_id is not None
    ):
        raise MessageValidationError("response_not_retryable")
    if _active_request(db, thread.id) is not None:
        raise MessageInFlightError("이미 답장을 만들고 있어요.")
    message = db.get(models.MessageMessage, prior.user_message_id)
    if message is None or message.role != "user":
        raise MessageNotFoundError("원래 메시지를 찾을 수 없습니다.")
    later_user_message = db.scalar(
        select(models.MessageMessage.id)
        .where(
            models.MessageMessage.thread_id == thread.id,
            models.MessageMessage.role == "user",
            models.MessageMessage.id > message.id,
        )
        .limit(1)
    )
    if later_user_message is not None:
        raise MessageValidationError("latest_retryable_response_required")

    selected_model = sqlalchemy_service.resolve_world_thread_response_model(
        db, user, thread
    )

    now = datetime.now(UTC)
    record = GenerationLifecycleService(
        SqlAlchemyResponseLifecycleRepository(db)
    ).accept(
        CreateResponseRequest(
            request_id=f"request-{uuid4().hex}",
            thread_id=thread.id,
            user_message_id=prior.user_message_id,
            response_slot_id=prior.response_slot_id,
            request_scope_hash=prior.request_scope_hash,
            idempotency_key=idempotency_key,
            generation_id=f"generation-{uuid4().hex}",
            attempt_number=prior.attempt_number + 1,
            retry_of_request_id=prior.request_id,
            selected_model=selected_model,
            deadline_at=now + timedelta(seconds=RESPONSE_REQUEST_DEADLINE_SECONDS),
        )
    )
    db.commit()
    return schemas.WorldChatMessageAcceptRead(
        outcome="accepted",
        user_message=schemas.MessageMessageRead.model_validate(message),
        response_request=_record_read(db, record),
    )


def get_world_response_request(
    db: Session,
    user: models.User,
    world_id: str,
    thread_id: str,
    request_id: str,
) -> schemas.WorldChatGenerationRequestRead:
    _mutation_thread(db, user, world_id, thread_id)
    row = db.get(models.ChatResponseRequest, request_id)
    if row is None or row.thread_id != thread_id:
        raise MessageNotFoundError("응답 요청을 찾을 수 없습니다.")
    record = _recover_if_expired(
        db,
        SqlAlchemyResponseLifecycleRepository(db).get_request(row.request_id),
    )
    return _record_read(db, record)


def get_latest_world_response_request(
    db: Session,
    user: models.User,
    world_id: str,
    thread_id: str,
) -> schemas.WorldChatLatestRequestRead:
    _mutation_thread(db, user, world_id, thread_id)
    row = _latest_request_row(db, thread_id)
    record = (
        None
        if row is None
        else _recover_if_expired(
            db,
            SqlAlchemyResponseLifecycleRepository(db).get_request(row.request_id),
        )
    )
    return schemas.WorldChatLatestRequestRead(
        response_request=None if record is None else _record_read(db, record)
    )


def get_world_response_evidence(
    db: Session,
    user: models.User,
    world_id: str,
    thread_id: str,
    request_id: str,
) -> schemas.WorldChatEvidenceRead:
    # The inspector is a read surface. Reuse the same ownership, World, role,
    # membership, and block checks as mutations without taking PostgreSQL row
    # locks that are reserved for generation/model-binding serialization.
    sqlalchemy_service._require_world_chat_owner_scope(db, user.id, world_id)
    thread = sqlalchemy_service._get_owned_world_thread(
        db,
        user,
        world_id,
        thread_id,
    )
    sqlalchemy_service._world_thread_read(
        db,
        thread,
        include_messages=False,
    )
    row = db.get(models.ChatResponseRequest, request_id)
    if (
        row is None
        or row.thread_id != thread.id
        or row.state != ResponseRequestState.COMMITTED.value
        or row.committed_assistant_message_id is None
    ):
        raise MessageNotFoundError("확인할 근거를 찾을 수 없습니다.")
    record = SqlAlchemyResponseLifecycleRepository(db).get_request(request_id)
    metadata = record.response_metadata
    capability = metadata.get("evidence_capability")
    snapshot = metadata.get("_evidence_inspector_v1")
    if capability not in {"available", "degraded"} or not isinstance(snapshot, dict):
        raise MessageNotFoundError("확인할 근거를 찾을 수 없습니다.")
    raw_items = snapshot.get("items")
    if snapshot.get("version") != "evidence-inspector.v1" or not isinstance(raw_items, list):
        raise MessageNotFoundError("확인할 근거를 찾을 수 없습니다.")
    scope = MemoryScope(
        owner_id=user.id,
        world_id=world_id,
        subject_world_character_id=thread.responding_world_character_id,
    )
    source_reader = SqlAlchemyMemorySourceEvidenceReader(db)
    items = [
        _chat_evidence_item(db, scope, raw, source_reader=source_reader)
        for raw in raw_items[:12]
        if isinstance(raw, dict)
    ]
    current_capability = (
        "available"
        if capability == "available"
        and items
        and all(item.availability == "available" for item in items)
        else "degraded"
    )
    return schemas.WorldChatEvidenceRead(
        request_id=request_id,
        route=str(metadata.get("route") or "unknown"),
        retrieval_outcome=str(metadata.get("retrieval_outcome") or "unknown"),
        capability=current_capability,
        items=items,
    )


async def stream_world_response(
    db: Session,
    user: models.User,
    world_id: str,
    thread_id: str,
    request_id: str,
    *,
    memory_recall_service: Any | None,
    runtime_settings: Settings = settings,
) -> AsyncIterator[GenerationEvent]:
    thread = _mutation_thread(db, user, world_id, thread_id)
    repository = SqlAlchemyResponseLifecycleRepository(db)
    record = repository.get_request(request_id)
    if record.thread_id != thread.id:
        raise MessageNotFoundError("응답 요청을 찾을 수 없습니다.")
    record = _recover_if_expired(db, record)
    if record.state in TERMINAL_STATES:
        yield _terminal_event(record)
        return
    if record.state is not ResponseRequestState.ACCEPTED:
        raise MessageInFlightError("이 응답은 이미 처리 중입니다.")

    message = db.get(models.MessageMessage, record.user_message_id)
    responding_character = db.get(models.Character, thread.character_id)
    if message is None or message.role != "user" or responding_character is None:
        async for event in _fail_before_workflow(
            db,
            record,
            failure_class="canonical_context_missing",
            retryable=False,
            reason=ResponseTerminalReason.CONTRACT_INVALID,
        ):
            yield event
        return
    if memory_recall_service is None:
        async for event in _fail_before_workflow(
            db,
            record,
            failure_class="local_runtime_unavailable",
            retryable=True,
            reason=ResponseTerminalReason.RETRIEVAL_FAILURE,
        ):
            yield event
        return
    try:
        _credential, base_material = sqlalchemy_service.resolve_message_credential_material(
            db,
            user,
        )
    except MessageCredentialRequiredError:
        async for event in _fail_before_workflow(
            db,
            record,
            failure_class="credential_required",
            retryable=False,
            reason=ResponseTerminalReason.POLICY_DENIED,
        ):
            yield event
        return
    except MessageCredentialInvalidError:
        async for event in _fail_before_workflow(
            db,
            record,
            failure_class="credential_invalid",
            retryable=False,
            reason=ResponseTerminalReason.POLICY_DENIED,
        ):
            yield event
        return

    material = CredentialMaterial(
        credential_id=base_material.credential_id,
        provider=base_material.provider,
        model=record.selected_model,
        fingerprint=base_material.fingerprint,
        purpose=base_material.purpose,
        _secret=base_material.reveal(),
    )
    lifecycle = GenerationLifecycleService(repository)
    canonical = CanonicalRetrievalPlanningService(
        planner=DirectLlmCanonicalRetrievalPlannerProvider(material),
        executor=CanonicalRetrievalPlanExecutor(memory_recall_service),
    )
    graph_recall = GraphRecallService(
        SqlAlchemyRelationshipGraphReadGateway(
            db,
            config=runtime_settings,
            graph_provider="ladybug",
        )
    )
    graph = GraphRetrievalPlanningService(
        planner=DirectLlmGraphRetrievalPlannerProvider(material),
        executor=GraphRetrievalPlanExecutor(graph_recall),
    )
    workflow = ResponseGenerationWorkflowService(
        lifecycle=lifecycle,
        router=RetrievalRoutingService(
            router=DirectLlmRetrievalRouterProvider(material),
            policy=SqlAlchemyRetrievalPolicyResolver(db),
        ),
        canonical=canonical,
        graph=graph,
        both=BothRetrievalWorkflowCoordinator(canonical=canonical, graph=graph),
        evidence=EvidenceBundleAssembler(),
        character_response=CharacterResponseGenerationService(
            DirectLlmCharacterResponseGenerator(material)
        ),
        unit_of_work=SqlAlchemyResponseWorkflowUnitOfWork(db),
        memory_producer=SqlAlchemySuccessfulChatMemoryProducer(db),
    )
    router_context, response_context = _recent_context(
        db,
        thread.id,
        exclude_message_id=message.id,
    )
    command = ResponseWorkflowCommand(
        request=record,
        preflight=RetrievalPreflightCommand(
            request_id=record.request_id,
            owner_id=user.id,
            world_id=world_id,
            thread_id=thread.id,
            requester_world_character_id=thread.requester_world_character_id or "",
            responding_world_character_id=thread.responding_world_character_id or "",
            user_message=message.content,
        ),
        profile=_profile(responding_character),
        router_context=router_context,
        response_context=response_context,
        character_labels=_character_labels(db, world_id),
        graph_projection_enabled=runtime_settings.graph_projection_enabled,
    )
    async for event in workflow.run(command):
        yield event


def _mutation_thread(
    db: Session,
    user: models.User,
    world_id: str,
    thread_id: str,
) -> models.MessageThread:
    sqlalchemy_service._require_world_chat_owner_scope(db, user.id, world_id)
    # Serialize generation acceptance/retry with the World Chat model PATCH.
    # The accepted request owns an immutable model snapshot, so both mutations
    # must observe one unambiguous thread binding order on PostgreSQL.
    thread = sqlalchemy_service._get_owned_world_thread(
        db,
        user,
        world_id,
        thread_id,
        lock_thread=True,
    )
    sqlalchemy_service._world_thread_read(
        db,
        thread,
        include_messages=False,
        lock_scope=True,
    )
    return thread


def _active_request(db: Session, thread_id: str) -> models.ChatResponseRequest | None:
    return db.scalar(
        select(models.ChatResponseRequest)
        .where(
            models.ChatResponseRequest.thread_id == thread_id,
            models.ChatResponseRequest.state.not_in(
                tuple(state.value for state in TERMINAL_STATES)
            ),
        )
        .order_by(models.ChatResponseRequest.created_at.desc())
        .limit(1)
    )


def _latest_request_row(
    db: Session,
    thread_id: str,
) -> models.ChatResponseRequest | None:
    return db.scalar(
        select(models.ChatResponseRequest)
        .where(models.ChatResponseRequest.thread_id == thread_id)
        .order_by(
            models.ChatResponseRequest.created_at.desc(),
            models.ChatResponseRequest.attempt_number.desc(),
        )
        .limit(1)
    )


def _recover_if_expired(db: Session, record):
    now = datetime.now(UTC)
    if record.state in TERMINAL_STATES or record.deadline_at > now:
        return record
    repository = SqlAlchemyResponseLifecycleRepository(db)
    GenerationLifecycleService(repository).recover_expired_requests(
        now=now,
        limit=100,
    )
    db.commit()
    return repository.get_request(record.request_id)


def _request_read(
    db: Session,
    row: models.ChatResponseRequest,
) -> schemas.WorldChatGenerationRequestRead:
    return _record_read(db, SqlAlchemyResponseLifecycleRepository(db).get_request(row.request_id))


def _record_read(
    db: Session,
    record,
) -> schemas.WorldChatGenerationRequestRead:
    user_message = db.get(models.MessageMessage, record.user_message_id)
    if user_message is None:
        raise MessageNotFoundError("원래 메시지를 찾을 수 없습니다.")
    assistant = (
        None
        if record.committed_assistant_message_id is None
        else db.get(models.MessageMessage, record.committed_assistant_message_id)
    )
    return schemas.WorldChatGenerationRequestRead(
        request_id=record.request_id,
        request_scope_hash=record.request_scope_hash,
        generation_id=record.generation_id,
        attempt_number=record.attempt_number,
        response_slot_id=record.response_slot_id,
        state=record.state.value,
        route=None if record.route is None else record.route.value,
        retryable=record.retryable,
        failure_class=(
            record.node_state.get("failure_class")
            or (None if record.terminal_reason is None else record.terminal_reason.value)
        ),
        last_accepted_sequence=record.last_emitted_sequence,
        user_message=schemas.MessageMessageRead.model_validate(user_message),
        assistant_message=(
            None
            if assistant is None
            else schemas.MessageMessageRead.model_validate(assistant)
        ),
        response_metadata={
            key: value
            for key, value in record.response_metadata.items()
            if not key.startswith("_")
        },
    )


def _chat_evidence_item(
    db: Session,
    scope: MemoryScope,
    raw: dict[str, Any],
    *,
    source_reader: SqlAlchemyMemorySourceEvidenceReader,
) -> schemas.WorldChatEvidenceItemRead:
    kind = raw.get("kind")
    if kind not in {"canonical_source", "graph_relationship", "graph_event"}:
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
    label = {
        "canonical_source": "기억 근거",
        "graph_relationship": "현재 관계",
        "graph_event": "관계 사건",
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
    if locator_kind == "canonical_source":
        try:
            source_type = MemorySourceTypeV1(str(locator.get("source_type")))
        except ValueError:
            source_type = None
        source_id = locator.get("source_id")
        fresh = (
            None
            if source_type is None or not isinstance(source_id, str)
            else source_reader.read_evidence(
                scope=scope,
                source_type=source_type,
                source_id=source_id,
            )
        )
        source_revision = locator.get("source_revision")
        if fresh is not None and (
            fresh.source_world_id == scope.world_id
            and (
                source_revision is None
                or fresh.source_digest == source_revision
            )
            and fresh.successful
            and fresh.visible
            and fresh.observed_by_subject
            and fresh.membership_active
            and not fresh.blocked
        ):
            availability = "available"
            occurred_at = fresh.source_created_at
            label = _chat_source_label(source_type)
            related_id, direction = _related_direction(
                scope.subject_world_character_id,
                fresh.actor_world_character_id,
                fresh.target_world_character_id,
                fresh.counterpart_world_character_id,
            )
            related_name = _world_character_name(
                db,
                related_id,
                world_id=scope.world_id,
            )
            if source_type in {MemorySourceTypeV1.POST, MemorySourceTypeV1.REPLY}:
                href = f"/worlds/{scope.world_id}/posts/{source_id}"
            elif source_type in {
                MemorySourceTypeV1.CHAT_MESSAGE,
                MemorySourceTypeV1.OWNER_MEMORY_REQUEST,
            } and fresh.thread_id:
                href = f"/worlds/{scope.world_id}/chat/{fresh.thread_id}"
        elif fresh is not None and source_type in {
            MemorySourceTypeV1.POST,
            MemorySourceTypeV1.REPLY,
        } and not fresh.visible:
            availability = "deleted"
    elif locator_kind == "memory_item":
        memory_id = locator.get("source_id")
        detail = None
        if isinstance(memory_id, str):
            try:
                detail = MemoryReadService(
                    SqlAlchemyMemoryRepository(db),
                    source_reader,
                ).detail(scope, item_id=memory_id)
            except MemoryNotFoundError:
                detail = None
        if detail is not None:
            expected_revision = locator.get("source_revision")
            revision_matches = (
                expected_revision is None
                or str(detail.item.version) == expected_revision
            )
            has_current_evidence = any(
                evidence.availability is MemoryEvidenceAvailability.AVAILABLE
                for evidence in detail.evidence
            )
            if (
                detail.lifecycle is MemoryLifecycle.ACTIVE
                and revision_matches
                and has_current_evidence
            ):
                availability = "available"
                href = (
                    f"/memory?world={scope.world_id}"
                    f"&subject={scope.subject_world_character_id}"
                    f"&memory={memory_id}"
                )
            label = "저장된 기억"
            related_name = _world_character_name(
                db,
                detail.item.counterpart_world_character_id,
                world_id=scope.world_id,
            )
            direction = "contextual" if related_name else None
    elif locator_kind == "graph_relationship":
        state = db.get(RelationshipState, locator.get("source_id"))
        actor = locator.get("actor_world_character_id")
        target = locator.get("target_world_character_id")
        if (
            state is not None
            and state.world_id == scope.world_id
            and state.actor_world_character_id == actor
            and state.target_world_character_id == target
            and (
                locator.get("source_revision") is None
                or str(state.version) == locator.get("source_revision")
            )
        ):
            try:
                sqlalchemy_service._world_chat_role(db, actor, world_id=scope.world_id)
                sqlalchemy_service._world_chat_role(db, target, world_id=scope.world_id)
                blocked = sqlalchemy_service._world_characters_are_blocked(
                    db, scope.world_id, actor, target
                )
            except (MessageNotFoundError, MessageForbiddenError):
                blocked = True
            if not blocked:
                availability = "available"
                related_id, direction = _related_direction(
                    scope.subject_world_character_id, actor, target, None
                )
                related_name = _world_character_name(
                    db,
                    related_id,
                    world_id=scope.world_id,
                )
    return schemas.WorldChatEvidenceItemRead(
        reference=reference,
        kind=kind,
        label=label,
        # The frozen snapshot is useful for provenance, but a source that is no
        # longer visible/current must not leak its former text through the
        # owner-facing inspector.
        excerpt=text[:500] if availability == "available" else None,
        occurred_at=occurred_at,
        availability=availability,
        related_character=related_name,
        direction=direction,
        canonical_href=href,
    )


def _optional_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)


def _related_direction(subject: str, actor: str | None, target: str | None, fallback: str | None):
    if actor == subject:
        return target or fallback, "outgoing"
    if target == subject:
        return actor or fallback, "incoming"
    return fallback, "contextual" if fallback else None


def _world_character_name(
    db: Session,
    world_character_id: str | None,
    *,
    world_id: str,
) -> str | None:
    if world_character_id is None:
        return None
    return db.scalar(
        select(models.Character.name)
        .join(models.WorldCharacter, models.WorldCharacter.character_id == models.Character.id)
        .where(
            models.WorldCharacter.id == world_character_id,
            models.WorldCharacter.world_id == world_id,
        )
    )


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


def _recent_context(
    db: Session,
    thread_id: str,
    *,
    exclude_message_id: int,
) -> tuple[
    tuple[RetrievalRouterContextMessage, ...],
    tuple[CharacterResponseContextMessage, ...],
]:
    rows = list(
        reversed(
            db.scalars(
                select(models.MessageMessage)
                .where(
                    models.MessageMessage.thread_id == thread_id,
                    models.MessageMessage.status == "ok",
                    models.MessageMessage.id != exclude_message_id,
                )
                .order_by(
                    models.MessageMessage.created_at.desc(),
                    models.MessageMessage.id.desc(),
                )
                .limit(RESPONSE_CONTEXT_MESSAGE_LIMIT)
            ).all()
        )
    )
    selected: list[models.MessageMessage] = []
    chars = 0
    for row in reversed(rows):
        if chars + len(row.content) > RESPONSE_CONTEXT_CHAR_LIMIT:
            continue
        selected.append(row)
        chars += len(row.content)
    selected.reverse()
    router = tuple(
        RetrievalRouterContextMessage(role=row.role, content=row.content)
        for row in selected
    )
    response = tuple(
        CharacterResponseContextMessage(role=row.role, content=row.content)
        for row in selected
    )
    return router, response


def _profile(character: models.Character) -> CharacterResponseProfile:
    return CharacterResponseProfile(
        name=character.name,
        handle=character.handle,
        one_liner=character.one_liner,
        personality=character.personality,
        speech_style=character.speech_style,
        worldview=character.worldview,
        topic_preferences=character.topic_preferences,
        safety_rules=character.safety_rules,
    )


def _character_labels(db: Session, world_id: str) -> dict[str, str]:
    rows = db.execute(
        select(models.WorldCharacter.id, models.Character.name)
        .join(models.Character, models.Character.id == models.WorldCharacter.character_id)
        .where(
            models.WorldCharacter.world_id == world_id,
            models.WorldCharacter.status == "active",
            models.Character.deleted_at.is_(None),
            models.Character.moderation_status == "active",
        )
    ).all()
    return {identifier: name for identifier, name in rows}


async def _fail_before_workflow(
    db: Session,
    record,
    *,
    failure_class: str,
    retryable: bool,
    reason: ResponseTerminalReason,
) -> AsyncIterator[GenerationEvent]:
    lifecycle = GenerationLifecycleService(SqlAlchemyResponseLifecycleRepository(db))
    now = datetime.now(UTC)
    record = lifecycle.acquire_lease(
        request_id=record.request_id,
        lease_token=f"lease-{uuid4().hex}",
        now=now,
        lease_expires_at=min(record.deadline_at, now + timedelta(seconds=30)),
    )
    db.commit()
    fence = _fence(record)
    accepted = _event(record, GenerationEventType.ACCEPTED, 0)
    lifecycle.accept_event(fence, accepted, now=datetime.now(UTC))
    db.commit()
    yield accepted
    record = SqlAlchemyResponseLifecycleRepository(db).get_request(record.request_id)
    failed = _event(
        record,
        GenerationEventType.FAILED,
        record.last_emitted_sequence + 1,
        payload={"failure_class": failure_class, "retryable": retryable},
    )
    lifecycle.accept_event(_fence(record), failed, now=datetime.now(UTC))
    record = SqlAlchemyResponseLifecycleRepository(db).get_request(record.request_id)
    lifecycle.mark_terminal(
        _fence(record),
        target=ResponseRequestState.FAILED,
        reason=reason,
        retryable=retryable,
        failure_class=failure_class,
        now=datetime.now(UTC),
    )
    db.commit()
    yield failed


def _terminal_event(record) -> GenerationEvent:
    if record.state is ResponseRequestState.COMMITTED:
        event_type = GenerationEventType.COMPLETED
        payload = {}
    else:
        event_type = GenerationEventType.FAILED
        payload = {
            "failure_class": (
                record.node_state.get("failure_class")
                or (
                    "generation_failed"
                    if record.terminal_reason is None
                    else record.terminal_reason.value
                )
            ),
            "retryable": record.retryable,
        }
    return _event(record, event_type, max(record.last_emitted_sequence, 0), payload=payload)


def _fence(record) -> GenerationFence:
    return GenerationFence(
        request_id=record.request_id,
        thread_id=record.thread_id,
        request_scope_hash=record.request_scope_hash,
        generation_id=record.generation_id,
        attempt_number=record.attempt_number,
        lease_generation=record.lease_generation,
        expected_prior_state=record.state,
    )


def _event(
    record,
    event_type: GenerationEventType,
    sequence: int,
    *,
    payload: dict | None = None,
) -> GenerationEvent:
    return GenerationEvent(
        request_id=record.request_id,
        request_scope_hash=record.request_scope_hash,
        generation_id=record.generation_id,
        attempt_number=record.attempt_number,
        sequence=sequence,
        event_type=event_type,
        payload=payload or {},
        protocol_version=CHAT_GENERATION_STREAM_VERSION,
    )


__all__ = [
    "RESPONSE_REQUEST_DEADLINE_SECONDS",
    "SqlAlchemyResponseWorkflowUnitOfWork",
    "accept_world_message",
    "get_latest_world_response_request",
    "get_world_response_request",
    "retry_world_response",
    "stream_world_response",
]
