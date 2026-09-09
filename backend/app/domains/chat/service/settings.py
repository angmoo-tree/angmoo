"""Chat preferences, settings admission and selected credential resolution."""

from __future__ import annotations

from sqlalchemy import update
from sqlalchemy.orm import Session

from app.domains.characters.service import profile as character_profile
from app.domains.chat import models, schemas
from app.domains.chat.contracts.context import (
    ChatCharacter,
    ChatCredential,
    ChatUser,
)
from app.domains.chat.contracts.model_binding import MessageModelBindingMode
from app.domains.chat.exceptions import (
    MessageCredentialInvalidError,
    MessageCredentialRequiredError,
    MessageForbiddenError,
    MessageValidationError,
)
from app.domains.chat.policies import (
    API_KEY_INVALID_MESSAGE,
    API_KEY_MISSING_MESSAGE,
    CHARACTER_DISABLED_MESSAGE,
    DEFAULT_MESSAGE_MODEL,
    LOCAL_CHARACTER_MESSAGES_DISABLED_MESSAGE,
    MESSAGE_MODELS,
)
from app.domains.chat.service import profiles
from app.domains.identity.contracts import (
    CredentialMaterial,
    CredentialPurpose,
)
from app.domains.identity.service import message_credentials
from app.domains.identity.service.credential_resolution import (
    CredentialResolutionError,
    CredentialResolver,
)


class MessageSettingsService:
    def get_user_settings(
        self, db: Session, user: ChatUser
    ) -> schemas.MessageSettingsRead:
        preference = self.ensure_user_preference(db, user)
        message_credential = self._get_message_credential(db, user.id)
        agent_credential = self._get_agent_source_credential(db, user, preference)
        return schemas.MessageSettingsRead(
            credential_source=preference.credential_source,
            source_character_id=preference.source_character_id,
            default_model=preference.default_model,
            default_thinking_level=preference.default_thinking_level,
            message_key_fingerprint=message_credential.key_fingerprint
            if message_credential
            else None,
            agent_key_fingerprint=agent_credential.key_fingerprint
            if agent_credential
            else None,
            has_usable_key=self._has_usable_credential(agent_credential)
            if preference.credential_source == "agent_key"
            else self._has_usable_credential(message_credential),
            owned_agents=profiles._owned_agent_refs(db, user),
        )

    def update_user_settings(
        self, db: Session, user: ChatUser, data: schemas.MessageSettingsUpdate
    ) -> schemas.MessageSettingsRead:
        preference = self.ensure_user_preference(db, user)
        if data.default_model is not None or data.default_thinking_level is not None:
            self._ensure_supported_model(data.default_model or preference.default_model)
            preference.default_model = data.default_model or preference.default_model
            preference.default_thinking_level = data.default_thinking_level or "high"
            db.execute(
                update(models.MessageThread)
                .where(
                    models.MessageThread.requester_id == user.id,
                    models.MessageThread.deleted_at.is_(None),
                    models.MessageThread.model_binding_mode
                    == MessageModelBindingMode.DEFAULT.value,
                )
                .values(selected_model=preference.default_model, selected_thinking_level=preference.default_thinking_level)
            )
        if data.credential_source is not None:
            preference.credential_source = data.credential_source
        if data.source_character_id is not None:
            source_character = profiles._get_owned_character(
                db, user, data.source_character_id
            )
            preference.source_character_id = source_character.id
        if preference.credential_source == "agent_key":
            if not preference.source_character_id:
                raise MessageCredentialRequiredError(
                    "재사용할 내 앵무 key를 선택해주세요."
                )
            credential = self._get_agent_source_credential(db, user, preference)
            if not self._has_usable_credential(credential):
                raise MessageCredentialRequiredError(API_KEY_MISSING_MESSAGE)
        if data.api_key is not None:
            self._upsert_message_credential(
                db, user, data.api_key, preference.default_model
            )
            preference.credential_source = "message_key"
        elif data.clear_message_key:
            credential = self._get_message_credential(db, user.id)
            if credential is not None:
                message_credentials.clear_message_credential(credential)
        db.commit()
        db.refresh(preference)
        return self.get_user_settings(db, user)

    def get_character_message_settings(
        self, db: Session, user: ChatUser, character_id: str
    ) -> schemas.CharacterMessageSettingRead:
        character = profiles._get_owned_character(db, user, character_id)
        return schemas.CharacterMessageSettingRead.model_validate(
            self.ensure_character_setting(db, character.id)
        )

    def update_character_message_settings(
        self,
        db: Session,
        user: ChatUser,
        character_id: str,
        data: schemas.CharacterMessageSettingUpdate,
    ) -> schemas.CharacterMessageSettingRead:
        character = profiles._get_owned_character(db, user, character_id)
        if character.execution_mode == "local" and data.enabled:
            raise MessageForbiddenError(LOCAL_CHARACTER_MESSAGES_DISABLED_MESSAGE)
        setting = self.ensure_character_setting(db, character.id)
        setting.enabled = data.enabled
        db.commit()
        db.refresh(setting)
        return schemas.CharacterMessageSettingRead.model_validate(setting)

    def ensure_user_preference(
        self, db: Session, user: ChatUser, *, commit_if_created: bool = True
    ) -> models.UserMessagePreference:
        preference = db.get(models.UserMessagePreference, user.id)
        if preference is not None:
            return preference
        preference = models.UserMessagePreference(
            user_id=user.id,
            credential_source="message_key",
            default_model=DEFAULT_MESSAGE_MODEL,
        )
        db.add(preference)
        if commit_if_created:
            db.commit()
            db.refresh(preference)
        else:
            db.flush()
        return preference

    def ensure_character_setting(
        self, db: Session, character_id: str
    ) -> models.CharacterMessageSetting:
        setting = db.get(models.CharacterMessageSetting, character_id)
        if setting is not None:
            return setting
        setting = models.CharacterMessageSetting(
            character_id=character_id, enabled=False
        )
        db.add(setting)
        db.commit()
        db.refresh(setting)
        return setting

    def _ensure_character_available_for_messages(
        self, db: Session, user: ChatUser, character: ChatCharacter
    ) -> None:
        if character.moderation_status != "active":
            raise MessageForbiddenError(CHARACTER_DISABLED_MESSAGE)
        if character.execution_mode == "local":
            raise MessageForbiddenError(LOCAL_CHARACTER_MESSAGES_DISABLED_MESSAGE)
        if character.owner_id == user.id:
            return
        setting = self.ensure_character_setting(db, character.id)
        if not setting.enabled:
            raise MessageForbiddenError(CHARACTER_DISABLED_MESSAGE)

    def _resolve_message_credential(
        self, db: Session, user: ChatUser
    ) -> tuple[ChatCredential, str]:
        credential, material = self.resolve_message_credential_material(db, user)
        return (credential, material.reveal())

    def resolve_message_credential_material(
        self, db: Session, user: ChatUser
    ) -> tuple[ChatCredential, CredentialMaterial]:
        preference = self.ensure_user_preference(db, user)
        credential = (
            self._get_agent_source_credential(db, user, preference)
            if preference.credential_source == "agent_key"
            else self._get_message_credential(db, user.id)
        )
        try:
            material = CredentialResolver.resolve_llm_credential(
                credential, purpose=CredentialPurpose.MESSAGE_LLM, owner_id=user.id
            )
        except CredentialResolutionError as exc:
            if not self._has_usable_credential(credential):
                raise MessageCredentialRequiredError(API_KEY_MISSING_MESSAGE) from exc
            raise MessageCredentialInvalidError(API_KEY_INVALID_MESSAGE) from exc
        if credential is None:
            raise MessageCredentialRequiredError(API_KEY_MISSING_MESSAGE)
        return (credential, material)

    def _get_message_credential(
        self, db: Session, user_id: str
    ) -> ChatCredential | None:
        return message_credentials.get_message_credential(db, user_id)

    def _get_agent_source_credential(
        self, db: Session, user: ChatUser, preference: models.UserMessagePreference
    ) -> ChatCredential | None:
        if not preference.source_character_id:
            return None
        character = character_profile.get_character(db, preference.source_character_id)
        if character is None or character.owner_id != user.id or character.deleted_at:
            return None
        return message_credentials.get_agent_credential(db, user.id, character.id)

    def _upsert_message_credential(
        self, db: Session, user: ChatUser, api_key: str, model: str
    ) -> ChatCredential:
        return message_credentials.upsert_message_credential(
            db, user.id, api_key, model
        )

    def _has_usable_credential(self, credential: ChatCredential | None) -> bool:
        return bool(
            credential
            and credential.enabled
            and (credential.provider == "google")
            and credential.encrypted_api_key
        )

    def _ensure_supported_model(self, model: str) -> None:
        if model not in MESSAGE_MODELS:
            raise MessageValidationError("지원하지 않는 모델입니다.")
