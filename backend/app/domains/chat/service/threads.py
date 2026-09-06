"""Thread admission, model selection and canonical World revalidation."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.domains.chat import models, schemas
from app.domains.chat.contracts.context import (
    ChatCharacter,
    ChatScopeQueries,
    ChatUser,
    ChatWorldCharacter,
    WorldCharacterBlockQuery,
)
from app.domains.chat.contracts.generation_lifecycle import TERMINAL_STATES
from app.domains.chat.contracts.model_binding import MessageModelBindingMode
from app.domains.chat.exceptions import (
    MessageForbiddenError,
    MessageInFlightError,
    MessageNotFoundError,
    MessageThreadLimitError,
    MessageValidationError,
)
from app.domains.chat.policies import (
    DEFAULT_MESSAGE_MODEL,
    MAX_ACTIVE_THREADS,
    THREAD_LIMIT_MESSAGE,
)
from app.domains.chat.repository import threads as thread_repository
from app.domains.chat.repository.threads import (
    _find_active_world_thread,
    _is_postgresql_session,
    _lock_message_thread_quota,
    _lock_world_thread_tuple,
)
from app.domains.chat.service import profiles
from app.domains.chat.service.settings import MessageSettingsService

logger = logging.getLogger(__name__)


LEGACY_WORLD_THREAD_MUTATION_MESSAGE = (
    "World가 확정된 대화는 해당 World Chat에서만 변경할 수 있습니다."
)


LEGACY_LOCAL_THREAD_CREATION_MESSAGE = (
    "새 대화는 Character가 속한 World Chat에서 시작해 주세요."
)


class ThreadService:
    def __init__(
        self,
        settings_service: MessageSettingsService,
        scope_queries: ChatScopeQueries,
        blocked_query: WorldCharacterBlockQuery,
    ) -> None:
        self.settings_service = settings_service
        self.scope_queries = scope_queries
        self.blocked_query = blocked_query

    _find_active_world_thread = staticmethod(_find_active_world_thread)
    _lock_world_thread_tuple = staticmethod(_lock_world_thread_tuple)
    _lock_message_thread_quota = staticmethod(_lock_message_thread_quota)
    _is_postgresql_session = staticmethod(_is_postgresql_session)

    def list_world_threads(
        self, db: Session, user: ChatUser, world_id: str
    ) -> schemas.WorldChatThreadListRead:
        self._require_world_chat_owner_scope(db, user.id, world_id)
        threads = thread_repository.list_world_threads(db, user.id, world_id)
        ambiguous_count = thread_repository.count_ambiguous_threads(db, user.id)
        items: list[schemas.WorldChatThreadRead] = []
        for thread in threads:
            try:
                items.append(
                    self._world_thread_read(db, thread, include_messages=False)
                )
            except (
                MessageNotFoundError,
                MessageForbiddenError,
                MessageValidationError,
            ):
                logger.warning(
                    "world_chat_thread_ineligible thread_id=%s world_id=%s",
                    thread.id,
                    world_id,
                )
        return schemas.WorldChatThreadListRead(
            items=items,
            ambiguous_legacy_count=ambiguous_count,
            max_threads=MAX_ACTIVE_THREADS,
        )

    def get_world_thread(
        self, db: Session, user: ChatUser, world_id: str, thread_id: str
    ) -> schemas.WorldChatThreadRead:
        self._require_world_chat_owner_scope(db, user.id, world_id)
        thread = self._get_owned_world_thread(db, user, world_id, thread_id)
        return self._world_thread_read(db, thread, include_messages=True)

    def get_world_chat_entry(
        self, db: Session, user: ChatUser, world_id: str, responding_id: str
    ) -> schemas.WorldChatEntryRead:
        """Resolve the read-only capability behind a World profile letter CTA."""
        self._require_world_chat_owner_scope(db, user.id, world_id)
        responding, _character = self._active_responding_world_character(
            db, world_id, responding_id
        )
        responding_read = self._world_chat_role(db, responding.id, world_id=world_id)
        requester_candidates = self._owner_controlled_world_characters(
            db, user.id, world_id
        )
        if not requester_candidates:
            return schemas.WorldChatEntryRead(
                world_id=world_id,
                responding=responding_read,
                requester_cardinality="zero",
                create_or_get_capability="unavailable",
                disabled_reason="requester_missing",
            )
        if len(requester_candidates) != 1:
            return schemas.WorldChatEntryRead(
                world_id=world_id,
                responding=responding_read,
                requester_cardinality="anomaly",
                create_or_get_capability="unavailable",
                disabled_reason="requester_cardinality_anomaly",
            )
        requester = requester_candidates[0]
        requester_read = self._world_chat_role(
            db, requester.id, world_id=world_id, expected_owner_id=user.id
        )
        if requester.id == responding.id:
            return schemas.WorldChatEntryRead(
                world_id=world_id,
                responding=responding_read,
                requester_cardinality="one",
                requester=requester_read,
                create_or_get_capability="unavailable",
                disabled_reason="self_target",
            )
        if self._world_characters_are_blocked(
            db, world_id, requester.id, responding.id
        ):
            return schemas.WorldChatEntryRead(
                world_id=world_id,
                responding=responding_read,
                requester_cardinality="one",
                requester=requester_read,
                create_or_get_capability="unavailable",
                disabled_reason="blocked",
            )
        return schemas.WorldChatEntryRead(
            world_id=world_id,
            responding=responding_read,
            requester_cardinality="one",
            requester=requester_read,
            create_or_get_capability="available",
        )

    def create_or_get_world_thread(
        self,
        db: Session,
        user: ChatUser,
        world_id: str,
        data: schemas.WorldChatThreadCreate,
        *,
        _integrity_retry_available: bool = True,
    ) -> schemas.WorldChatThreadCreateRead:
        self._require_world_chat_owner_scope(db, user.id, world_id)
        requester_candidates = self._owner_controlled_world_characters(
            db, user.id, world_id
        )
        if not requester_candidates:
            return schemas.WorldChatThreadCreateRead(
                outcome="resolution_required", resolution_code="requester_missing"
            )
        if len(requester_candidates) != 1:
            return schemas.WorldChatThreadCreateRead(
                outcome="resolution_required",
                resolution_code="requester_cardinality_anomaly",
            )
        requester = requester_candidates[0]
        if (
            data.requester_world_character_id is not None
            and data.requester_world_character_id != requester.id
        ):
            raise MessageForbiddenError("요청자 역할을 임의로 바꿀 수 없습니다.")
        responding, character = self._active_responding_world_character(
            db, world_id, data.responding_world_character_id
        )
        if requester.id == responding.id:
            raise MessageValidationError(
                "같은 WorldCharacter와 자기 자신으로 대화할 수 없습니다."
            )
        if self._world_characters_are_blocked(
            db, world_id, requester.id, responding.id
        ):
            raise MessageForbiddenError(
                "이 Character와는 지금 대화를 시작할 수 없습니다."
            )
        self._lock_world_thread_tuple(
            db, user.id, world_id, requester.id, responding.id
        )
        existing = self._find_active_world_thread(
            db, user.id, world_id, requester.id, responding.id
        )
        if existing is not None:
            try:
                if data.selected_model:
                    existing = self._get_owned_world_thread(
                        db, user, world_id, existing.id, lock_thread=True
                    )
                    self._ensure_no_active_world_response_request(db, existing.id)
                    self.settings_service._ensure_supported_model(data.selected_model)
                    existing.selected_model = data.selected_model
                    existing.model_binding_mode = (
                        MessageModelBindingMode.THREAD_OVERRIDE.value
                    )
                    db.flush()
                    thread_read = self._world_thread_read(
                        db, existing, include_messages=True, lock_scope=True
                    )
                    db.commit()
                else:
                    thread_read = self._world_thread_read(
                        db, existing, include_messages=True
                    )
            except Exception:
                db.rollback()
                raise
            return schemas.WorldChatThreadCreateRead(
                outcome="reused", thread=thread_read
            )
        self._lock_message_thread_quota(db, user.id)
        active_count = thread_repository.count_active_threads(db, user.id)
        if active_count >= MAX_ACTIVE_THREADS:
            raise MessageThreadLimitError(THREAD_LIMIT_MESSAGE)
        try:
            preference = self.settings_service.ensure_user_preference(
                db, user, commit_if_created=False
            )
            selected_model = data.selected_model or preference.default_model
            self.settings_service._ensure_supported_model(selected_model)
            thread = models.MessageThread(
                id=f"msg-thread-{uuid4().hex[:12]}",
                requester_id=user.id,
                character_id=character.id,
                world_id=world_id,
                requester_world_character_id=requester.id,
                responding_world_character_id=responding.id,
                world_scope_status="resolved",
                selected_model=selected_model,
                model_binding_mode=MessageModelBindingMode.THREAD_OVERRIDE.value
                if data.selected_model is not None
                else MessageModelBindingMode.DEFAULT.value,
            )
            db.add(thread)
            db.flush()
            db.refresh(thread)
            thread_read = self._world_thread_read(
                db, thread, include_messages=True, lock_scope=True
            )
            db.commit()
        except IntegrityError:
            db.rollback()
            if not _integrity_retry_available:
                raise
            return self.create_or_get_world_thread(
                db, user, world_id, data, _integrity_retry_available=False
            )
        except Exception:
            db.rollback()
            raise
        return schemas.WorldChatThreadCreateRead(outcome="created", thread=thread_read)

    def update_world_thread_model(
        self,
        db: Session,
        user: ChatUser,
        world_id: str,
        thread_id: str,
        data: schemas.WorldChatThreadModelUpdate,
    ) -> schemas.WorldChatThreadRead:
        """Change the next-generation model without mutating accepted snapshots."""
        self._require_world_chat_owner_scope(db, user.id, world_id)
        thread = self._get_owned_world_thread(
            db, user, world_id, thread_id, lock_thread=True
        )
        self._world_thread_read(db, thread, include_messages=False, lock_scope=True)
        self._ensure_no_active_world_response_request(db, thread.id)
        if data.mode is MessageModelBindingMode.DEFAULT:
            thread.model_binding_mode = MessageModelBindingMode.DEFAULT.value
            self.resolve_world_thread_response_model(db, user, thread)
        else:
            if data.selected_model is None:
                raise MessageValidationError("고정할 모델을 선택해 주세요.")
            self.settings_service._ensure_supported_model(data.selected_model)
            thread.model_binding_mode = MessageModelBindingMode.THREAD_OVERRIDE.value
            thread.selected_model = data.selected_model
            db.flush()
        read = self._world_thread_read(
            db, thread, include_messages=True, lock_scope=True
        )
        db.commit()
        return read

    def _ensure_no_active_world_response_request(
        self, db: Session, thread_id: str
    ) -> None:
        active = db.scalar(
            select(models.ChatResponseRequest.request_id)
            .where(
                models.ChatResponseRequest.thread_id == thread_id,
                models.ChatResponseRequest.state.not_in(
                    tuple((state.value for state in TERMINAL_STATES))
                ),
            )
            .limit(1)
        )
        if active is not None:
            raise MessageInFlightError(
                "답장을 만드는 동안에는 모델을 바꿀 수 없습니다."
            )

    def resolve_world_thread_response_model(
        self, db: Session, user: ChatUser, thread: models.MessageThread
    ) -> str:
        """Resolve and persist the model used by the next accepted attempt."""
        if thread.requester_id != user.id or thread.world_scope_status != "resolved":
            raise MessageValidationError("World Chat 모델 범위를 확인할 수 없습니다.")
        try:
            binding = MessageModelBindingMode(thread.model_binding_mode)
        except ValueError as exc:
            raise MessageValidationError(
                "World Chat 모델 binding이 올바르지 않습니다."
            ) from exc
        if binding is MessageModelBindingMode.DEFAULT:
            preference = self.settings_service.ensure_user_preference(
                db, user, commit_if_created=False
            )
            self.settings_service._ensure_supported_model(preference.default_model)
            thread.selected_model = preference.default_model
        else:
            self.settings_service._ensure_supported_model(thread.selected_model)
        db.flush()
        return thread.selected_model

    def _owner_controlled_world_characters(
        self, db: Session, owner_id: str, world_id: str, *, lock_scope: bool = False
    ) -> list[ChatWorldCharacter]:
        return self.scope_queries.owner_controlled_world_characters(
            db, owner_id, world_id, lock_scope=lock_scope
        )

    def _require_world_chat_owner_scope(
        self, db: Session, owner_id: str, world_id: str, *, lock_scope: bool = False
    ) -> None:
        installation = self.scope_queries.local_installation(db, lock_scope=lock_scope)
        if (
            installation is None
            or installation.bootstrap_state != "claimed"
            or installation.owner_user_id != owner_id
        ):
            raise MessageForbiddenError(
                "이 설치의 local owner만 World Chat을 사용할 수 있습니다."
            )
        owned_world = self.scope_queries.owned_world_id(
            db, owner_id, world_id, lock_scope=lock_scope
        )
        if owned_world is None:
            raise MessageNotFoundError("World Chat을 찾을 수 없습니다.")

    def _active_responding_world_character(
        self, db: Session, world_id: str, world_character_id: str
    ) -> tuple[ChatWorldCharacter, ChatCharacter]:
        row = self.scope_queries.responding_world_character(
            db, world_id, world_character_id
        )
        if row is None:
            raise MessageNotFoundError(
                "이 World에서 대화할 Character를 찾을 수 없습니다."
            )
        return (row[0], row[1])

    def _world_characters_are_blocked(
        self, db: Session, world_id: str, first_id: str, second_id: str
    ) -> bool:
        return self.blocked_query(
            db,
            world_id=world_id,
            first_world_character_id=first_id,
            second_world_character_id=second_id,
        )

    def list_threads(
        self, db: Session, user: ChatUser
    ) -> schemas.MessageThreadListRead:
        threads = thread_repository.list_threads(db, user.id)
        return schemas.MessageThreadListRead(
            items=[
                self._legacy_thread_read(db, thread, include_messages=False)
                for thread in threads
            ],
            max_threads=MAX_ACTIVE_THREADS,
        )

    def get_thread(
        self, db: Session, user: ChatUser, thread_id: str
    ) -> schemas.MessageThreadRead:
        return self._legacy_thread_read(
            db, self._get_owned_thread(db, user, thread_id), include_messages=True
        )

    def create_or_get_thread(
        self, db: Session, user: ChatUser, data: schemas.MessageThreadCreate
    ) -> schemas.MessageThreadRead:
        character = profiles._get_character(db, data.character_id)
        self.settings_service._ensure_character_available_for_messages(
            db, user, character
        )
        self._lock_message_thread_quota(db, user.id)
        existing_rows = thread_repository.find_legacy_thread_candidates(
            db, user.id, character.id
        )
        if len(existing_rows) > 1:
            raise MessageValidationError(
                "여러 World에 연결된 대화입니다. 해당 World Chat에서 열어 주세요."
            )
        if existing_rows:
            existing = existing_rows[0]
            if data.selected_model and existing.world_scope_status != "resolved":
                self.settings_service._ensure_supported_model(data.selected_model)
                existing.selected_model = data.selected_model
                db.commit()
                db.refresh(existing)
            return self._legacy_thread_read(db, existing, include_messages=True)
        if self._claimed_local_installation_exists(db):
            raise MessageValidationError(LEGACY_LOCAL_THREAD_CREATION_MESSAGE)
        active_count = thread_repository.count_active_threads(db, user.id)
        if active_count >= MAX_ACTIVE_THREADS:
            raise MessageThreadLimitError(THREAD_LIMIT_MESSAGE)
        preference = self.settings_service.ensure_user_preference(
            db, user, commit_if_created=False
        )
        selected_model = data.selected_model or preference.default_model
        self.settings_service._ensure_supported_model(selected_model)
        thread = models.MessageThread(
            id=f"msg-thread-{uuid4().hex[:12]}",
            requester_id=user.id,
            character_id=character.id,
            world_scope_status="ambiguous",
            selected_model=selected_model,
            model_binding_mode=MessageModelBindingMode.THREAD_OVERRIDE.value,
        )
        db.add(thread)
        db.commit()
        db.refresh(thread)
        return self._thread_read(db, thread, include_messages=True)

    def update_thread(
        self,
        db: Session,
        user: ChatUser,
        thread_id: str,
        data: schemas.MessageThreadUpdate,
    ) -> schemas.MessageThreadRead:
        self.settings_service._ensure_supported_model(data.selected_model)
        thread = self._get_owned_legacy_mutable_thread(db, user, thread_id)
        thread.selected_model = data.selected_model
        thread.model_binding_mode = MessageModelBindingMode.THREAD_OVERRIDE.value
        db.commit()
        db.refresh(thread)
        return self._thread_read(db, thread, include_messages=True)

    def delete_thread(self, db: Session, user: ChatUser, thread_id: str) -> None:
        thread = self._get_owned_legacy_mutable_thread(db, user, thread_id)
        thread.deleted_at = datetime.now(UTC)
        db.commit()

    def _thread_read(
        self,
        db: Session,
        thread: models.MessageThread,
        *,
        include_messages: bool,
        redact_content: bool = False,
    ) -> schemas.MessageThreadRead:
        messages = (
            self._thread_messages(db, thread.id)
            if include_messages and (not redact_content)
            else []
        )
        latest_message = (
            None
            if redact_content
            else messages[-1]
            if messages
            else self._latest_thread_message(db, thread.id)
        )
        return schemas.MessageThreadRead(
            id=thread.id,
            requester=profiles._user_ref(thread.requester),
            character=profiles._character_ref(thread.character),
            selected_model=thread.selected_model,
            model_binding_mode=thread.model_binding_mode,
            last_message_at=thread.last_message_at,
            created_at=thread.created_at,
            latest_message=latest_message,
            messages=messages,
            world_id=thread.world_id,
            requester_world_character_id=thread.requester_world_character_id,
            responding_world_character_id=thread.responding_world_character_id,
            world_scope_status=thread.world_scope_status,
        )

    def _legacy_thread_read(
        self, db: Session, thread: models.MessageThread, *, include_messages: bool
    ) -> schemas.MessageThreadRead:
        """Expose only redirect metadata for resolved World-scoped legacy rows."""
        return self._thread_read(
            db,
            thread,
            include_messages=include_messages,
            redact_content=thread.world_scope_status == "resolved",
        )

    def _world_thread_read(
        self,
        db: Session,
        thread: models.MessageThread,
        *,
        include_messages: bool,
        lock_scope: bool = False,
    ) -> schemas.WorldChatThreadRead:
        if (
            thread.world_scope_status != "resolved"
            or thread.world_id is None
            or thread.requester_world_character_id is None
            or (thread.responding_world_character_id is None)
        ):
            raise MessageValidationError("World를 확정하지 못한 legacy thread입니다.")
        self._require_world_chat_owner_scope(
            db, thread.requester_id, thread.world_id, lock_scope=lock_scope
        )
        requester_candidates = self._owner_controlled_world_characters(
            db, thread.requester_id, thread.world_id, lock_scope=lock_scope
        )
        if (
            len(requester_candidates) != 1
            or requester_candidates[0].id != thread.requester_world_character_id
        ):
            raise MessageValidationError(
                "World Chat 요청자 역할을 고유하게 확인할 수 없습니다."
            )
        requester = self._world_chat_role(
            db,
            thread.requester_world_character_id,
            world_id=thread.world_id,
            expected_owner_id=thread.requester_id,
            lock_scope=lock_scope,
        )
        responding = self._world_chat_role(
            db,
            thread.responding_world_character_id,
            world_id=thread.world_id,
            lock_scope=lock_scope,
        )
        if requester.world_character_id == responding.world_character_id:
            raise MessageValidationError("World Chat 역할이 올바르지 않습니다.")
        if self._world_characters_are_blocked(
            db,
            thread.world_id,
            requester.world_character_id,
            responding.world_character_id,
        ):
            raise MessageForbiddenError("이 Character와는 지금 대화할 수 없습니다.")
        messages = self._thread_messages(db, thread.id) if include_messages else []
        latest_message = (
            messages[-1] if messages else self._latest_thread_message(db, thread.id)
        )
        preference = db.get(models.UserMessagePreference, thread.requester_id)
        default_model = (
            DEFAULT_MESSAGE_MODEL if preference is None else preference.default_model
        )
        self.settings_service._ensure_supported_model(default_model)
        resolved_model = (
            default_model
            if thread.model_binding_mode == MessageModelBindingMode.DEFAULT.value
            else thread.selected_model
        )
        return schemas.WorldChatThreadRead(
            id=thread.id,
            world_id=thread.world_id,
            requester=requester,
            responding=responding,
            selected_model=resolved_model,
            default_model=default_model,
            model_binding_mode=thread.model_binding_mode,
            last_message_at=thread.last_message_at,
            created_at=thread.created_at,
            latest_message=latest_message,
            messages=messages,
            evidence_summaries=self._thread_evidence_summaries(db, thread.id)
            if include_messages
            else [],
        )

    def _thread_evidence_summaries(
        self, db: Session, thread_id: str
    ) -> list[schemas.WorldChatEvidenceSummaryRead]:
        rows = thread_repository.list_committed_response_requests(db, thread_id)
        summaries: list[schemas.WorldChatEvidenceSummaryRead] = []
        for row in rows:
            try:
                metadata = json.loads(row.response_metadata_json)
            except (TypeError, json.JSONDecodeError):
                continue
            if not isinstance(metadata, dict):
                continue
            capability = metadata.get("evidence_capability")
            count = metadata.get("public_evidence_count")
            if (
                capability not in {"available", "degraded"}
                or not isinstance(count, int)
                or count < 1
            ):
                continue
            summaries.append(
                schemas.WorldChatEvidenceSummaryRead(
                    request_id=row.request_id,
                    assistant_message_id=row.committed_assistant_message_id,
                    capability=capability,
                    count=count,
                )
            )
        return summaries

    def _world_chat_role(
        self,
        db: Session,
        world_character_id: str,
        *,
        world_id: str,
        expected_owner_id: str | None = None,
        lock_scope: bool = False,
    ) -> schemas.WorldChatRoleRead:
        row = self.scope_queries.world_chat_role(
            db,
            world_character_id,
            world_id=world_id,
            expected_owner_id=expected_owner_id,
            lock_scope=lock_scope,
        )
        if row is None:
            raise MessageNotFoundError("World Chat 참여자를 찾을 수 없습니다.")
        world_character, character = row
        return schemas.WorldChatRoleRead(
            world_character_id=world_character.id,
            character_id=character.id,
            display_name=character.name,
            handle=character.handle,
            avatar_url=character.avatar_url,
            banner_url=character.banner_url,
            role_key=world_character.role_key,
            control_mode=world_character.control_mode,
            profile_capability="available",
        )

    def _thread_messages(
        self, db: Session, thread_id: str
    ) -> list[schemas.MessageMessageRead]:
        rows = thread_repository.list_thread_messages(db, thread_id)
        return [schemas.MessageMessageRead.model_validate(row) for row in rows]

    def _latest_thread_message(
        self, db: Session, thread_id: str
    ) -> schemas.MessageMessageRead | None:
        row = thread_repository.latest_thread_message(db, thread_id)
        return schemas.MessageMessageRead.model_validate(row) if row else None

    def _get_owned_thread(
        self, db: Session, user: ChatUser, thread_id: str
    ) -> models.MessageThread:
        thread = thread_repository.get_owned_thread(db, user.id, thread_id)
        if thread is None:
            raise MessageNotFoundError("쪽지를 찾을 수 없습니다.")
        return thread

    def _get_owned_legacy_mutable_thread(
        self, db: Session, user: ChatUser, thread_id: str
    ) -> models.MessageThread:
        thread = self._get_owned_thread(db, user, thread_id)
        if thread.world_scope_status == "resolved":
            raise MessageValidationError(LEGACY_WORLD_THREAD_MUTATION_MESSAGE)
        return thread

    def _get_owned_world_thread(
        self,
        db: Session,
        user: ChatUser,
        world_id: str,
        thread_id: str,
        *,
        lock_thread: bool = False,
    ) -> models.MessageThread:
        statement = select(models.MessageThread).where(
            models.MessageThread.id == thread_id,
            models.MessageThread.requester_id == user.id,
            models.MessageThread.world_id == world_id,
            models.MessageThread.world_scope_status == "resolved",
            models.MessageThread.deleted_at.is_(None),
        )
        if lock_thread and self._is_postgresql_session(db):
            statement = statement.with_for_update()
        thread = db.scalar(statement)
        if thread is None:
            raise MessageNotFoundError("World Chat thread를 찾을 수 없습니다.")
        return thread

    def _claimed_local_installation_exists(self, db: Session) -> bool:
        return self.scope_queries.claimed_local_installation_exists(db)
