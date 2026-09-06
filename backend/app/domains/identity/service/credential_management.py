"""Owner-scoped credential changes with explicit shared-Session collaborators."""
from __future__ import annotations
from sqlalchemy.orm import Session
from app.domains.identity import models, schemas
from app.domains.identity.contracts import CharacterCredentialWorkflows, CredentialCharacter


def update_credential(
    db: Session,
    user: models.User,
    character_id: str,
    data: schemas.CredentialUpsert,
    *,
    workflows: CharacterCredentialWorkflows,
) -> schemas.CredentialRead:
    character = workflows.get_owned_character(db, user, character_id)
    workflows.ensure_mutable(user)
    workflows.ensure_llm_mode(character)
    _ensure_credential_world_scope(
        db,
        user=user,
        character=character,
        world_id=data.world_id,
        workflows=workflows,
    )
    current_assigned_slot = workflows.get_assigned_slot(db, character.id)
    if (
        current_assigned_slot is not None
        and current_assigned_slot.status == workflows.running_slot_status
    ):
        raise workflows.slot_busy_error(
            "앵무가 지금 활동 중이라 API key 또는 모델을 바꿀 수 없습니다. 활동이 끝난 뒤 다시 시도해주세요."
        )
    try:
        if data.api_key is not None:
            credential = workflows.upsert_credential(
                db,
                user=user,
                character=character,
                provider=data.provider,
                model=data.model,
                api_key=data.api_key,
                auth_profile_id=None,
                label=data.label,
                commit=current_assigned_slot is None,
            )
            if current_assigned_slot is not None:
                if workflows.sync_enabled():
                    workflows.bind_profile(
                        workflows.slot_read(current_assigned_slot),
                        user_id=user.id,
                        character=character,
                        credential=credential,
                    )
                    workflows.reload_secrets()
                db.commit()
                db.refresh(credential)
        else:
            credential = workflows.get_credential(db, character.id)
            if credential is None or not credential.encrypted_api_key:
                raise workflows.credential_required_error(
                    "Agent credential key is required before changing the model"
                )
            if credential.provider != data.provider:
                raise workflows.credential_required_error(
                    "API key is required before changing the credential provider"
                )
            credential.model = data.model
            if data.label is not None:
                credential.label = data.label
            credential.enabled = True
            db.commit()
            db.refresh(credential)
    except Exception:
        db.rollback()
        raise
    workflows.log_activity(
        db,
        user_id=user.id,
        character_id=character.id,
        action_type="credential_saved",
        target_post_id=None,
        reason="credential_saved",
        result="Credential profile was synchronized for this character.",
    )
    return schemas.CredentialRead.model_validate(credential)


def get_credential_metadata(
    db: Session,
    user: models.User,
    character_id: str,
    *,
    workflows: CharacterCredentialWorkflows,
    world_id: str | None = None,
) -> schemas.CredentialRead | None:
    character = workflows.get_owned_character(db, user, character_id)
    workflows.ensure_llm_mode(character)
    _ensure_credential_world_scope(
        db,
        user=user,
        character=character,
        world_id=world_id,
        workflows=workflows,
    )
    credential = workflows.get_credential(db, character.id)
    if credential is None:
        return None
    if credential.owner_id != user.id:
        raise workflows.character_not_found_error(character_id)
    return schemas.CredentialRead.model_validate(credential)


def delete_credential(
    db: Session,
    user: models.User,
    character_id: str,
    *,
    workflows: CharacterCredentialWorkflows,
    world_id: str | None = None,
) -> None:
    character = workflows.get_owned_character(db, user, character_id)
    workflows.ensure_mutable(user)
    workflows.ensure_llm_mode(character)
    _ensure_credential_world_scope(
        db,
        user=user,
        character=character,
        world_id=world_id,
        workflows=workflows,
    )
    credential = workflows.get_credential(db, character.id)
    if credential is None or (
        not credential.enabled
        and credential.encrypted_api_key is None
        and credential.key_fingerprint is None
    ):
        return

    assigned_slot = workflows.get_assigned_slot(db, character.id)
    if (
        assigned_slot is not None
        and assigned_slot.status == workflows.running_slot_status
    ):
        raise workflows.slot_busy_error(
            "앵무가 지금 활동 중이라 API key를 삭제할 수 없습니다. 활동이 끝난 뒤 다시 시도해주세요."
        )

    try:
        if assigned_slot is not None and workflows.sync_enabled():
            workflows.release_profile(
                assigned_slot,
                user_id=user.id,
                character_id=character.id,
                credential=credential,
            )
            workflows.reload_secrets()
        workflows.release_slot(
            db,
            user_id=user.id,
            character_id=character.id,
            commit=False,
        )
        workflows.disable_auto(db, character.id)
        workflows.set_world_autonomy(
            db,
            character_id=character.id,
            enabled=False,
        )
        workflows.set_character_status(character, status="inactive")
        credential.enabled = False
        credential.encrypted_api_key = None
        credential.key_fingerprint = None
        credential.cooldown_until = None
        db.commit()
    except Exception:
        db.rollback()
        raise


def _ensure_credential_world_scope(
    db: Session,
    *,
    workflows: CharacterCredentialWorkflows,
    user: models.User,
    character: CredentialCharacter,
    world_id: str | None,
) -> None:
    if world_id is None:
        return
    membership_id = workflows.get_membership_id(db, world_id, user.id)
    if membership_id is None:
        raise workflows.character_not_found_error(character.id)
    world_character_id = workflows.get_world_character_id(db, world_id, character.id, membership_id)
    if world_character_id is None:
        raise workflows.character_not_found_error(character.id)
