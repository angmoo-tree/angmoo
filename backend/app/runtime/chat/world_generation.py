"""SQLAlchemy/provider composition for World Chat response generation."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
import logging
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings, settings
from app.domains.chat import schemas
from app.domains.chat.service import (
    BothRetrievalWorkflowCoordinator,
    CanonicalRetrievalPlanningService,
    CharacterResponseGenerationService,
    EvidenceBundleAssembler,
    GraphRetrievalPlanningService,
    ResponseGenerationWorkflowService,
    ResponseWorkflowCommand,
    RetrievalRoutingService,
    TodaySnsActivityAssembler,
)
from app.domains.chat.contracts import (
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
from app.domains.chat.exceptions import (
    MessageCredentialInvalidError,
    MessageCredentialRequiredError,
    MessageForbiddenError,
    MessageInFlightError,
    MessageNotFoundError,
    MessageValidationError,
)
from app.domains.chat.repository import SqlAlchemyResponseLifecycleRepository
from app.domains.chat.contracts import (
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
from app.runtime.social.sqlalchemy_today_activity import (
    SqlAlchemyTodaySocialActivityReader,
)
from app.runtime.chat.today_sns_activity import SqlAlchemyTodaySnsSnapshotValidator


from app.domains.chat.service.generation import RESPONSE_REQUEST_DEADLINE_SECONDS
from app.runtime.chat.message_composition import generation_service
RESPONSE_CONTEXT_MESSAGE_LIMIT = 20
RESPONSE_CONTEXT_CHAR_LIMIT = 8_000


logger = logging.getLogger(__name__)


class SqlAlchemyResponseWorkflowUnitOfWork:
    def __init__(self, session: Session) -> None:
        self._session = session

    def checkpoint(self) -> None:
        self._session.commit()

    def rollback(self) -> None:
        self._session.rollback()












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
    lifecycle = repository
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
    character_labels = _character_labels(db, world_id)
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
        today_snapshot_validator=SqlAlchemyTodaySnsSnapshotValidator(db, character_labels),
    )
    router_context, response_context = _recent_context(
        db,
        thread.id,
        exclude_message_id=message.id,
    )
    today_sns_snapshot = None
    world = db.get(models.World, world_id)
    if world is not None and thread.responding_world_character_id is not None:
        try:
            today_sns_snapshot = TodaySnsActivityAssembler(
                SqlAlchemyTodaySocialActivityReader(db)
            ).assemble(
                owner_id=user.id,
                world_id=world_id,
                subject_world_character_id=thread.responding_world_character_id,
                timezone=world.timezone,
                character_labels=character_labels,
                now=datetime.now(UTC),
            )
        except Exception as exc:
            # Today awareness is an optional deterministic L2.5 context. A
            # scoped read failure must not make ordinary World Chat unusable;
            # the Router guard upgrades an explicit Today query to canonical
            # retrieval when this snapshot is unavailable.
            logger.warning(
                "p8_l_r_today_sns_snapshot_unavailable request_id=%s failure_type=%s",
                record.request_id,
                type(exc).__name__,
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
        character_labels=character_labels,
        today_sns_snapshot=today_sns_snapshot,
        graph_projection_enabled=runtime_settings.graph_projection_enabled,
    )
    async for event in workflow.run(command):
        yield event
























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










__all__ = [
    "RESPONSE_REQUEST_DEADLINE_SECONDS",
    "SqlAlchemyResponseWorkflowUnitOfWork",
    "accept_world_message",
    "get_latest_world_response_request",
    "get_world_response_request",
    "retry_world_response",
    "stream_world_response",
]


# Same-instance aliases for the remaining streaming/evidence composition.
accept_world_message = generation_service.accept_world_message
retry_world_response = generation_service.retry_world_response
get_world_response_request = generation_service.get_world_response_request
get_latest_world_response_request = generation_service.get_latest_world_response_request
_mutation_thread = generation_service._mutation_thread
_recover_if_expired = generation_service._recover_if_expired
_request_read = generation_service._request_read
_record_read = generation_service._record_read
_fail_before_workflow = generation_service._fail_before_workflow
_terminal_event = generation_service._terminal_event
_fence = generation_service._fence
_event = generation_service._event

from app.domains.chat.repository.response_requests import _active_request, _latest_request_row

from app.runtime.chat.message_composition import evidence_service
from app.runtime.chat.evidence_reads import world_character_name as _world_character_name
from app.domains.chat.service.evidence import _optional_datetime, _related_direction, _chat_source_label

get_world_response_evidence = evidence_service.get_world_response_evidence
_chat_evidence_item = evidence_service._chat_evidence_item
