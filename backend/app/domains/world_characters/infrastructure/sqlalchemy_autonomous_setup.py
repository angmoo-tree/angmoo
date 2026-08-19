from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.ids import uuid7_string
from app.domains.identity.public import (
    CredentialMaterial,
    CredentialPurpose,
    CredentialResolutionError,
    CredentialResolver,
)
from app.domains.world_characters.api import setup_schemas as schemas
from app.domains.world_characters.infrastructure import (
    autonomous_setup_contracts as world_character_contracts,
    autonomous_setup_models as models,
    direct_llm_setup_provider as world_character_provider,
)
from app.domains.worlds.public import build_world_generation_context
from app.integrations import direct_llm
from app.providers.registry import get_model_spec


PROFILE_REGENERATION_LIMIT_24H = 2
OWNER_REGENERATION_LIMIT_24H = 5


class WorldCharacterSetupError(Exception):
    reason_code = "world_character_setup_error"


class WorldCharacterSetupNotFoundError(WorldCharacterSetupError):
    reason_code = "world_character_not_found"


class WorldCharacterSetupForbiddenError(WorldCharacterSetupError):
    reason_code = "character_not_owned"


class WorldCharacterSetupConflictError(WorldCharacterSetupError):
    reason_code = "setup_in_progress"

    def __init__(self, reason_code: str | None = None) -> None:
        if reason_code is not None:
            self.reason_code = reason_code
        super().__init__(self.reason_code)


class WorldCharacterSetupValidationError(WorldCharacterSetupError):
    reason_code = "world_character_ineligible"

    def __init__(self, reason_code: str) -> None:
        self.reason_code = reason_code
        super().__init__(reason_code)


@dataclass(frozen=True)
class SetupScope:
    world: models.World
    membership: models.WorldMembership
    world_character: models.WorldCharacter
    character: models.Character


def set_active_world_character_autonomy(
    db: Session,
    *,
    character_id: str,
    enabled: bool,
) -> bool:
    """Align the selected autonomous WorldCharacter with scheduler lifecycle.

    Agent activation is character-scoped, while P4 execution is scoped to the
    selected WorldCharacter. Only that selected autonomous identity may inherit
    the lifecycle switch; owner-controlled identities remain fail-closed.
    """

    active_world = db.get(models.CharacterActiveWorld, character_id)
    if active_world is None:
        return False
    world_character = db.get(models.WorldCharacter, active_world.world_character_id)
    if (
        world_character is None
        or world_character.character_id != character_id
        or world_character.control_mode != "autonomous"
        or world_character.status != "active"
    ):
        return False
    if world_character.autonomous_enabled == enabled:
        return False
    world_character.autonomous_enabled = enabled
    world_character.version += 1
    db.flush()
    return True


def enter_world(
    db: Session,
    *,
    world_id: str,
    user: models.User,
    data: schemas.WorldCharacterEntryCreate,
) -> schemas.WorldCharacterEntryRead:
    world = db.get(models.World, world_id)
    if world is None:
        raise WorldCharacterSetupNotFoundError(world_id)
    if world.status != "published" or world.readiness_status != "publish_ready":
        raise WorldCharacterSetupValidationError("world_not_published")
    character = db.get(models.Character, data.character_id)
    if (
        character is None
        or character.deleted_at is not None
        or character.owner_id != user.id
    ):
        raise WorldCharacterSetupForbiddenError(data.character_id)
    if character.moderation_status != "active":
        raise WorldCharacterSetupValidationError("world_character_ineligible")

    membership = db.scalar(
        select(models.WorldMembership).where(
            models.WorldMembership.world_id == world_id,
            models.WorldMembership.user_id == user.id,
        )
    )
    if membership is None:
        if world.join_policy != "open":
            raise WorldCharacterSetupValidationError("membership_inactive")
        membership = models.WorldMembership(
            id=uuid7_string(),
            world_id=world_id,
            user_id=user.id,
            role="member",
            status="active",
            requested_by_user_id=user.id,
            approved_by_user_id=user.id,
            joined_at=datetime.now(UTC),
        )
        db.add(membership)
        db.flush()
    elif membership.status != "active":
        raise WorldCharacterSetupValidationError("membership_inactive")

    role_statement = select(models.WorldRole).where(
        models.WorldRole.world_id == world_id,
        models.WorldRole.status == "enabled",
        models.WorldRole.autonomous_allowed.is_(True),
    )
    roles = list(db.scalars(role_statement))
    if data.role_key is not None:
        role = next((item for item in roles if item.role_key == data.role_key), None)
        if role is None:
            raise WorldCharacterSetupValidationError("world_reference_invalid")
    elif len(roles) == 1:
        role = roles[0]
    elif not roles:
        role = None
    else:
        raise WorldCharacterSetupValidationError("role_required")

    existing = db.scalar(
        select(models.WorldCharacter).where(
            models.WorldCharacter.world_id == world_id,
            models.WorldCharacter.character_id == character.id,
        )
    )
    if existing is not None:
        if existing.membership_id != membership.id or existing.status not in {
            "pending",
            "inactive",
            "active",
        }:
            raise WorldCharacterSetupValidationError("world_character_ineligible")
        return _entry_read(existing, reused=True)

    local_profile: dict[str, str] = {
        "entry_idempotency_key": data.idempotency_key,
    }
    if data.local_background:
        local_profile["background"] = data.local_background
    world_character = models.WorldCharacter(
        id=uuid7_string(),
        world_id=world_id,
        character_id=character.id,
        membership_id=membership.id,
        role_key=role.role_key if role is not None else None,
        status="pending",
        autonomous_enabled=False,
        local_profile=local_profile,
    )
    db.add(world_character)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        replay = db.scalar(
            select(models.WorldCharacter).where(
                models.WorldCharacter.world_id == world_id,
                models.WorldCharacter.character_id == character.id,
            )
        )
        if replay is not None:
            return _entry_read(replay, reused=True)
        raise WorldCharacterSetupConflictError("idempotency_replay") from exc
    return _entry_read(world_character, reused=False)


def _entry_read(
    world_character: models.WorldCharacter,
    *,
    reused: bool,
) -> schemas.WorldCharacterEntryRead:
    return schemas.WorldCharacterEntryRead(
        id=world_character.id,
        world_id=world_character.world_id,
        character_id=world_character.character_id,
        membership_id=world_character.membership_id,
        role_key=world_character.role_key,
        status=world_character.status,
        autonomous_enabled=world_character.autonomous_enabled,
        version=world_character.version,
        reused=reused,
    )


def get_world_entry(
    db: Session,
    *,
    world_id: str,
    character_id: str,
    user: models.User,
) -> schemas.WorldCharacterEntryRead:
    character = db.get(models.Character, character_id)
    if character is None or character.deleted_at is not None:
        raise WorldCharacterSetupNotFoundError(character_id)
    if character.owner_id != user.id:
        raise WorldCharacterSetupForbiddenError(character_id)

    world_character = db.scalar(
        select(models.WorldCharacter).where(
            models.WorldCharacter.world_id == world_id,
            models.WorldCharacter.character_id == character_id,
        )
    )
    if world_character is None:
        raise WorldCharacterSetupNotFoundError(character_id)

    scope = _load_scope(
        db,
        world_character_id=world_character.id,
        user=user,
    )
    return _entry_read(scope.world_character, reused=True)


def _load_scope(
    db: Session,
    *,
    world_character_id: str,
    user: models.User,
    lock_for_update: bool = False,
) -> SetupScope:
    statement = select(models.WorldCharacter).where(
        models.WorldCharacter.id == world_character_id
    )
    if lock_for_update:
        statement = statement.with_for_update()
    world_character = db.scalar(statement)
    if world_character is None:
        raise WorldCharacterSetupNotFoundError(world_character_id)
    character = db.get(models.Character, world_character.character_id)
    if character is None or character.deleted_at is not None:
        raise WorldCharacterSetupNotFoundError(world_character_id)
    if character.owner_id != user.id:
        raise WorldCharacterSetupForbiddenError(world_character_id)
    if world_character.control_mode != "autonomous":
        raise WorldCharacterSetupValidationError(
            "owner_controlled_automation_disabled"
        )
    membership = db.get(models.WorldMembership, world_character.membership_id)
    if (
        membership is None
        or membership.world_id != world_character.world_id
        or membership.user_id != user.id
        or membership.status != "active"
    ):
        raise WorldCharacterSetupValidationError("membership_inactive")
    world = db.get(models.World, world_character.world_id)
    if world is None:
        raise WorldCharacterSetupNotFoundError(world_character_id)
    if world.status != "published" or world.readiness_status != "publish_ready":
        raise WorldCharacterSetupValidationError("world_not_published")
    if world_character.status not in {"pending", "inactive", "active"}:
        raise WorldCharacterSetupValidationError("world_character_ineligible")
    if character.moderation_status != "active":
        raise WorldCharacterSetupValidationError("world_character_ineligible")
    return SetupScope(world, membership, world_character, character)


def _select_active_world_character(
    db: Session,
    *,
    scope: SetupScope,
    approval_id: str,
    selected_at: datetime,
) -> None:
    active_world = db.scalar(
        select(models.CharacterActiveWorld)
        .where(models.CharacterActiveWorld.character_id == scope.character.id)
        .with_for_update()
    )
    if active_world is None:
        db.add(
            models.CharacterActiveWorld(
                character_id=scope.character.id,
                world_character_id=scope.world_character.id,
                selected_at=selected_at,
                idempotency_key=f"approval:{approval_id}",
                version=1,
            )
        )
        return
    if active_world.world_character_id == scope.world_character.id:
        return
    active_world.world_character_id = scope.world_character.id
    active_world.selected_at = selected_at
    active_world.idempotency_key = f"approval:{approval_id}"
    active_world.version += 1


def _resolve_material(db: Session, scope: SetupScope) -> CredentialMaterial:
    credential = db.scalar(
        select(models.LlmCredential)
        .where(models.LlmCredential.character_id == scope.character.id)
        .where(models.LlmCredential.purpose == "agent")
    )
    try:
        material = CredentialResolver.resolve_llm_credential(
            credential,
            purpose=CredentialPurpose.WORLD_CHARACTER_SETUP_LLM,
            owner_id=scope.character.owner_id,
            character_id=scope.character.id,
        )
        get_model_spec(material.provider, material.model)
    except (CredentialResolutionError, ValueError) as exc:
        raise WorldCharacterSetupValidationError("credential_required") from exc
    cooldown_until = getattr(credential, "cooldown_until", None)
    if cooldown_until is not None:
        cooldown = cooldown_until
        if cooldown.tzinfo is None:
            cooldown = cooldown.replace(tzinfo=UTC)
        if cooldown > datetime.now(UTC):
            raise WorldCharacterSetupValidationError("provider_quota")
    return material


def preflight_setup(
    db: Session,
    *,
    world_character_id: str,
    user: models.User,
) -> schemas.WorldCharacterSetupPreflightRead:
    scope = _load_scope(db, world_character_id=world_character_id, user=user)
    material: CredentialMaterial | None = None
    reason: str | None = None
    try:
        material = _resolve_material(db, scope)
    except WorldCharacterSetupValidationError as exc:
        reason = exc.reason_code
    character_hash = world_character_contracts.character_contract_hash(scope.character)
    reused = _ready_pair(
        db,
        world_character_id=scope.world_character.id,
        character_hash=character_hash,
        world_hash=scope.world.contract_hash,
    ) is not None
    return schemas.WorldCharacterSetupPreflightRead(
        world_character_id=scope.world_character.id,
        world_id=scope.world.id,
        character_id=scope.character.id,
        provider=material.provider if material is not None else None,
        model=material.model if material is not None else None,
        credential_ready=material is not None,
        logical_call_count=0 if reused else 2,
        physical_request_count=0 if reused else 3,
        profile_max_output_tokens=world_character_provider.PROFILE_MAX_OUTPUT_TOKENS,
        repertoire_max_output_tokens=(
            world_character_provider.REPERTOIRE_MAX_OUTPUT_TOKENS
        ),
        reused=reused,
        safe_reason_code=reason,
    )


async def generate_setup(
    db: Session,
    *,
    world_character_id: str,
    user: models.User,
    data: schemas.WorldCharacterSetupGenerateCreate,
    provider: world_character_provider.WorldCharacterSetupProvider | None = None,
) -> schemas.WorldCharacterSetupRead:
    scope = _load_scope(
        db,
        world_character_id=world_character_id,
        user=user,
        lock_for_update=True,
    )
    material = _resolve_material(db, scope)
    character_hash = world_character_contracts.character_contract_hash(scope.character)
    world_hash = scope.world.contract_hash
    if _ready_pair(
        db,
        world_character_id=world_character_id,
        character_hash=character_hash,
        world_hash=world_hash,
    ) is not None:
        return get_setup(db, world_character_id=world_character_id, user=user, reused=True)

    generation_context = build_world_generation_context(
        db, scope.world
    )
    generation_input = world_character_contracts.build_world_character_generation_input(
        character=scope.character,
        world_character=scope.world_character,
        world_context=generation_context,
        previous_candidate_signatures=_recent_candidate_signatures(
            db, world_character_id
        ),
        recent_execution_signatures=[],
    )
    input_hash = world_character_contracts.canonical_sha256(generation_input)
    stage_provider = (
        provider
        if provider is not None
        else world_character_provider.DirectLlmWorldCharacterSetupProvider()
    )

    profile = _matching_profile(
        db,
        world_character_id=world_character_id,
        character_hash=character_hash,
        world_hash=world_hash,
    )
    if profile is None:
        _assert_regeneration_quota(db, scope)
        attempt = _begin_attempt(
            db,
            scope=scope,
            stage="community_profile",
            idempotency_key=data.idempotency_key,
            material=material,
            consent_policy_version=data.consent_policy_version,
            input_hash=input_hash,
        )
        try:
            result = await stage_provider.generate_community_profile(
                material=material,
                character_id=scope.character.id,
                generation_input=generation_input,
            )
            profile_payload = _require_profile_result(result.payload)
            scope = _reload_and_assert_hashes(
                db,
                scope=scope,
                user=user,
                character_hash=character_hash,
                world_hash=world_hash,
            )
            profile = _save_profile_draft(
                db,
                scope=scope,
                material=material,
                payload=profile_payload,
                character_hash=character_hash,
                world_hash=world_hash,
            )
            _finish_attempt_success(db, attempt, result=result, output=profile_payload)
            db.commit()
        except Exception as exc:
            _finish_attempt_failure(db, attempt, exc)
            db.commit()
            raise _public_stage_error(exc) from exc

    existing_repertoire = _matching_repertoire(
        db,
        world_character_id=world_character_id,
        profile_id=profile.id,
        character_hash=character_hash,
        world_hash=world_hash,
    )
    if existing_repertoire is not None:
        return get_setup(db, world_character_id=world_character_id, user=user, reused=True)

    return await _generate_repertoire_stage(
        db,
        scope=scope,
        user=user,
        data=data,
        material=material,
        stage_provider=stage_provider,
        generation_context=generation_context,
        generation_input=generation_input,
        profile=profile,
        character_hash=character_hash,
        world_hash=world_hash,
        input_hash=input_hash,
    )


async def retry_setup(
    db: Session,
    *,
    world_character_id: str,
    user: models.User,
    data: schemas.WorldCharacterSetupRetryCreate,
    provider: world_character_provider.WorldCharacterSetupProvider | None = None,
) -> schemas.WorldCharacterSetupRead:
    if data.stage == "community_profile":
        generate = schemas.WorldCharacterSetupGenerateCreate(
            idempotency_key=data.idempotency_key,
            consent_policy_version=data.consent_policy_version,
            consented=True,
        )
        return await generate_setup(
            db,
            world_character_id=world_character_id,
            user=user,
            data=generate,
            provider=provider,
        )

    scope = _load_scope(db, world_character_id=world_character_id, user=user)
    material = _resolve_material(db, scope)
    character_hash = world_character_contracts.character_contract_hash(scope.character)
    world_hash = scope.world.contract_hash
    profile = _matching_profile(
        db,
        world_character_id=world_character_id,
        character_hash=character_hash,
        world_hash=world_hash,
    )
    if profile is None:
        raise WorldCharacterSetupValidationError("profile_schema_invalid")
    generation_context = build_world_generation_context(
        db, scope.world
    )
    generation_input = world_character_contracts.build_world_character_generation_input(
        character=scope.character,
        world_character=scope.world_character,
        world_context=generation_context,
        previous_candidate_signatures=_recent_candidate_signatures(
            db, world_character_id
        ),
        recent_execution_signatures=[],
    )
    stage_provider = (
        provider
        if provider is not None
        else world_character_provider.DirectLlmWorldCharacterSetupProvider()
    )
    generate_data = schemas.WorldCharacterSetupGenerateCreate(
        idempotency_key=data.idempotency_key,
        consent_policy_version=data.consent_policy_version,
        consented=True,
    )
    return await _generate_repertoire_stage(
        db,
        scope=scope,
        user=user,
        data=generate_data,
        material=material,
        stage_provider=stage_provider,
        generation_context=generation_context,
        generation_input=generation_input,
        profile=profile,
        character_hash=character_hash,
        world_hash=world_hash,
        input_hash=world_character_contracts.canonical_sha256(generation_input),
    )


async def _generate_repertoire_stage(
    db: Session,
    *,
    scope: SetupScope,
    user: models.User,
    data: schemas.WorldCharacterSetupGenerateCreate,
    material: CredentialMaterial,
    stage_provider: world_character_provider.WorldCharacterSetupProvider,
    generation_context: schemas.WorldGenerationContextRead,
    generation_input: dict[str, Any],
    profile: models.WorldCommunityProfile,
    character_hash: str,
    world_hash: str,
    input_hash: str,
) -> schemas.WorldCharacterSetupRead:
    attempt = _begin_attempt(
        db,
        scope=scope,
        stage="repertoire",
        idempotency_key=data.idempotency_key,
        material=material,
        consent_policy_version=data.consent_policy_version,
        input_hash=world_character_contracts.canonical_sha256(
            {
                "generation_input_hash": input_hash,
                "community_profile_id": profile.id,
            }
        ),
    )
    profile_payload = _profile_payload(profile)

    def validator(payload: dict[str, Any]):
        return world_character_contracts.validate_activity_repertoire(
            payload,
            world_context=generation_context,
            world_character=scope.world_character,
        )

    try:
        result = await stage_provider.generate_repertoire(
            material=material,
            character_id=scope.character.id,
            generation_input=generation_input,
            community_profile=profile_payload,
            validator=validator,
        )
        repertoire_payload = _require_repertoire_result(result.payload)
        scope = _reload_and_assert_hashes(
            db,
            scope=scope,
            user=user,
            character_hash=character_hash,
            world_hash=world_hash,
        )
        repertoire = _save_repertoire_draft(
            db,
            scope=scope,
            material=material,
            profile=profile,
            validated=repertoire_payload,
            character_hash=character_hash,
            world_hash=world_hash,
        )
        _finish_attempt_success(
            db,
            attempt,
            result=result,
            output={
                "repertoire_id": repertoire.id,
                "signatures": [
                    item.canonical_signature for item in repertoire_payload.candidates
                ],
            },
        )
        db.commit()
    except Exception as exc:
        _finish_attempt_failure(db, attempt, exc)
        db.commit()
        raise _public_stage_error(exc) from exc
    return get_setup(db, world_character_id=scope.world_character.id, user=user)


def approve_setup(
    db: Session,
    *,
    world_character_id: str,
    user: models.User,
    data: schemas.WorldCharacterSetupApproveCreate,
) -> schemas.WorldCharacterSetupRead:
    scope = _load_scope(
        db,
        world_character_id=world_character_id,
        user=user,
        lock_for_update=True,
    )
    existing_approval = db.scalar(
        select(models.WorldCharacterSetupAttempt).where(
            models.WorldCharacterSetupAttempt.owner_user_id == user.id,
            models.WorldCharacterSetupAttempt.world_character_id == world_character_id,
            models.WorldCharacterSetupAttempt.stage == "approval",
            models.WorldCharacterSetupAttempt.idempotency_key == data.idempotency_key,
        )
    )
    if existing_approval is not None:
        if existing_approval.status == "succeeded":
            _select_active_world_character(
                db,
                scope=scope,
                approval_id=existing_approval.id,
                selected_at=existing_approval.finished_at
                or existing_approval.created_at,
            )
            db.commit()
            return get_setup(db, world_character_id=world_character_id, user=user)
        raise WorldCharacterSetupConflictError("idempotency_replay")

    profile = db.get(models.WorldCommunityProfile, data.profile_id)
    repertoire = db.get(models.WorldActivityRepertoire, data.repertoire_id)
    if (
        profile is None
        or repertoire is None
        or profile.world_character_id != world_character_id
        or repertoire.world_character_id != world_character_id
        or repertoire.community_profile_id != profile.id
        or profile.status not in {"draft", "ready"}
        or repertoire.status not in {"draft", "ready"}
    ):
        raise WorldCharacterSetupValidationError("world_character_ineligible")

    character_hash = world_character_contracts.character_contract_hash(scope.character)
    world_hash = scope.world.contract_hash
    if (
        profile.character_contract_hash != character_hash
        or repertoire.character_contract_hash != character_hash
        or profile.world_contract_hash != world_hash
        or repertoire.world_contract_hash != world_hash
    ):
        profile.status = "stale"
        repertoire.status = "stale"
        db.commit()
        raise WorldCharacterSetupConflictError("contract_hash_stale")

    generation_context = build_world_generation_context(
        db, scope.world
    )
    candidate_rows = _candidate_rows(db, repertoire.id)
    validated = world_character_contracts.validate_activity_repertoire(
        {"candidates": [_candidate_payload(row).model_dump(mode="json") for row in candidate_rows]},
        world_context=generation_context,
        world_character=scope.world_character,
    )
    stored_signatures = [row.canonical_signature for row in candidate_rows]
    validated_signatures = [item.canonical_signature for item in validated.candidates]
    if stored_signatures != validated_signatures:
        raise WorldCharacterSetupConflictError("repertoire_signature_mismatch")
    world_character_contracts.validate_community_profile(
        _profile_payload(profile).model_dump(mode="json")
    )

    consent_attempt = db.scalar(
        select(models.WorldCharacterSetupAttempt)
        .where(
            models.WorldCharacterSetupAttempt.world_character_id == world_character_id,
            models.WorldCharacterSetupAttempt.status == "succeeded",
            models.WorldCharacterSetupAttempt.stage.in_(
                ["community_profile", "repertoire"]
            ),
        )
        .order_by(models.WorldCharacterSetupAttempt.created_at.desc())
    )
    if consent_attempt is None:
        raise WorldCharacterSetupValidationError("world_character_ineligible")

    now = datetime.now(UTC)
    approval = models.WorldCharacterSetupAttempt(
        id=uuid7_string(),
        owner_user_id=user.id,
        world_character_id=world_character_id,
        stage="approval",
        status="succeeded",
        idempotency_key=data.idempotency_key,
        provider=profile.provider,
        model=profile.model,
        credential_id=profile.credential_id,
        consent_policy_version=consent_attempt.consent_policy_version,
        consented_at=consent_attempt.consented_at,
        logical_call_count=0,
        physical_request_count=0,
        input_hash=world_character_contracts.canonical_sha256(
            {"profile_id": profile.id, "repertoire_id": repertoire.id}
        ),
        output_hash=world_character_contracts.canonical_sha256(
            {
                "profile_id": profile.id,
                "repertoire_id": repertoire.id,
                "candidate_count": len(validated.candidates),
            }
        ),
        started_at=now,
        finished_at=now,
    )

    previous_profiles = list(
        db.scalars(
            select(models.WorldCommunityProfile)
            .where(
                models.WorldCommunityProfile.world_character_id == world_character_id,
                models.WorldCommunityProfile.status == "ready",
                models.WorldCommunityProfile.id != profile.id,
            )
            .with_for_update()
        )
    )
    previous_repertoires = list(
        db.scalars(
            select(models.WorldActivityRepertoire)
            .where(
                models.WorldActivityRepertoire.world_character_id
                == world_character_id,
                models.WorldActivityRepertoire.status == "ready",
                models.WorldActivityRepertoire.id != repertoire.id,
            )
            .with_for_update()
        )
    )
    for row in previous_profiles:
        row.status = "superseded"
    for row in previous_repertoires:
        row.status = "superseded"
    profile.status = "ready"
    profile.approved_at = now
    repertoire.status = "ready"
    repertoire.approved_at = now
    scope.world_character.status = "active"
    scope.world_character.character_contract_hash = character_hash
    scope.world_character.world_contract_hash = world_hash
    scope.world_character.version += 1
    _select_active_world_character(
        db,
        scope=scope,
        approval_id=approval.id,
        selected_at=now,
    )
    db.add(approval)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise WorldCharacterSetupConflictError("idempotency_replay") from exc
    return get_setup(db, world_character_id=world_character_id, user=user)


def reject_setup(
    db: Session,
    *,
    world_character_id: str,
    user: models.User,
    data: schemas.WorldCharacterSetupRejectCreate,
) -> schemas.WorldCharacterSetupRead:
    scope = _load_scope(db, world_character_id=world_character_id, user=user)
    now = datetime.now(UTC)
    for profile in db.scalars(
        select(models.WorldCommunityProfile).where(
            models.WorldCommunityProfile.world_character_id == world_character_id,
            models.WorldCommunityProfile.status == "draft",
        )
    ):
        profile.status = "failed"
    for repertoire in db.scalars(
        select(models.WorldActivityRepertoire).where(
            models.WorldActivityRepertoire.world_character_id == world_character_id,
            models.WorldActivityRepertoire.status == "draft",
        )
    ):
        repertoire.status = "failed"
    consent_attempt = db.scalar(
        select(models.WorldCharacterSetupAttempt)
        .where(
            models.WorldCharacterSetupAttempt.world_character_id == world_character_id
        )
        .order_by(models.WorldCharacterSetupAttempt.created_at.desc())
    )
    if consent_attempt is None:
        raise WorldCharacterSetupValidationError("world_character_ineligible")
    db.add(
        models.WorldCharacterSetupAttempt(
            id=uuid7_string(),
            owner_user_id=user.id,
            world_character_id=world_character_id,
            stage="approval",
            status="cancelled",
            idempotency_key=data.idempotency_key,
            provider=consent_attempt.provider,
            model=consent_attempt.model,
            credential_id=consent_attempt.credential_id,
            consent_policy_version=consent_attempt.consent_policy_version,
            consented_at=consent_attempt.consented_at,
            logical_call_count=0,
            physical_request_count=0,
            input_hash=world_character_contracts.canonical_sha256(
                {"reason": data.reason, "world_character_id": scope.world_character.id}
            ),
            safe_error_code="owner_rejected",
            started_at=now,
            finished_at=now,
        )
    )
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise WorldCharacterSetupConflictError("idempotency_replay") from exc
    return get_setup(db, world_character_id=world_character_id, user=user)


def get_setup(
    db: Session,
    *,
    world_character_id: str,
    user: models.User,
    reused: bool = False,
) -> schemas.WorldCharacterSetupRead:
    scope = _load_scope(db, world_character_id=world_character_id, user=user)
    character_hash = world_character_contracts.character_contract_hash(scope.character)
    world_hash = scope.world.contract_hash
    profile = _latest_profile(db, world_character_id)
    repertoire = _latest_repertoire(db, world_character_id)
    running = db.scalar(
        select(models.WorldCharacterSetupAttempt.id).where(
            models.WorldCharacterSetupAttempt.world_character_id == world_character_id,
            models.WorldCharacterSetupAttempt.status == "running",
        )
    )
    latest_attempt = db.scalar(
        select(models.WorldCharacterSetupAttempt)
        .where(
            models.WorldCharacterSetupAttempt.world_character_id == world_character_id
        )
        .order_by(models.WorldCharacterSetupAttempt.created_at.desc())
    )
    stale = bool(
        (profile is not None and (
            profile.character_contract_hash != character_hash
            or profile.world_contract_hash != world_hash
        ))
        or (repertoire is not None and (
            repertoire.character_contract_hash != character_hash
            or repertoire.world_contract_hash != world_hash
        ))
    )
    candidate_rows = _candidate_rows(db, repertoire.id) if repertoire else []
    autonomy_ready = bool(
        profile is not None
        and repertoire is not None
        and profile.status == "ready"
        and repertoire.status == "ready"
        and not stale
        and _daypart_counts(candidate_rows)
        == {daypart: 10 for daypart in world_character_contracts.DAYPARTS}
    )
    can_approve = bool(
        profile is not None
        and repertoire is not None
        and profile.status in {"draft", "ready"}
        and repertoire.status in {"draft", "ready"}
        and not stale
        and len(candidate_rows) == 40
    )
    if running is not None:
        state: schemas.WorldSetupState = "running"
    elif stale:
        state = "stale"
    elif profile is None or profile.status == "failed":
        state = "failed" if latest_attempt and latest_attempt.status == "failed" else "needs_profile"
    elif repertoire is None or repertoire.status == "failed":
        state = "failed" if latest_attempt and latest_attempt.status == "failed" else "needs_repertoire"
    else:
        state = "ready"
    retry_stage = None
    if latest_attempt is not None and latest_attempt.status == "failed":
        retry_stage = latest_attempt.stage
    return schemas.WorldCharacterSetupRead(
        world_character_id=world_character_id,
        world_id=scope.world.id,
        character_id=scope.character.id,
        state=state,
        autonomy_ready=autonomy_ready,
        autonomous_enabled=scope.world_character.autonomous_enabled,
        reused=reused,
        can_retry_stage=retry_stage,
        can_approve=can_approve,
        can_regenerate=state in {"stale", "failed"},
        safe_reason_code=(
            latest_attempt.safe_error_code
            if latest_attempt is not None and latest_attempt.status == "failed"
            else None
        ),
        current_character_contract_hash=character_hash,
        current_world_contract_hash=world_hash,
        generated_character_contract_hash=(
            profile.character_contract_hash if profile is not None else None
        ),
        generated_world_contract_hash=(
            profile.world_contract_hash if profile is not None else None
        ),
        profile=_profile_read(profile) if profile is not None else None,
        repertoire=(
            _repertoire_read(repertoire, candidate_rows)
            if repertoire is not None
            else None
        ),
    )


def _assert_regeneration_quota(db: Session, scope: SetupScope) -> None:
    since = datetime.now(UTC) - timedelta(hours=24)
    character_count = db.scalar(
        select(func.count(models.WorldCharacterSetupAttempt.id)).where(
            models.WorldCharacterSetupAttempt.world_character_id
            == scope.world_character.id,
            models.WorldCharacterSetupAttempt.stage == "community_profile",
            models.WorldCharacterSetupAttempt.created_at >= since,
        )
    ) or 0
    owner_count = db.scalar(
        select(func.count(models.WorldCharacterSetupAttempt.id)).where(
            models.WorldCharacterSetupAttempt.owner_user_id == scope.character.owner_id,
            models.WorldCharacterSetupAttempt.stage == "community_profile",
            models.WorldCharacterSetupAttempt.created_at >= since,
        )
    ) or 0
    if (
        character_count >= PROFILE_REGENERATION_LIMIT_24H
        or owner_count >= OWNER_REGENERATION_LIMIT_24H
    ):
        raise WorldCharacterSetupValidationError("regeneration_limit_reached")


def _begin_attempt(
    db: Session,
    *,
    scope: SetupScope,
    stage: str,
    idempotency_key: str,
    material: CredentialMaterial,
    consent_policy_version: str,
    input_hash: str,
) -> models.WorldCharacterSetupAttempt:
    existing = db.scalar(
        select(models.WorldCharacterSetupAttempt).where(
            models.WorldCharacterSetupAttempt.owner_user_id == scope.character.owner_id,
            models.WorldCharacterSetupAttempt.world_character_id
            == scope.world_character.id,
            models.WorldCharacterSetupAttempt.stage == stage,
            models.WorldCharacterSetupAttempt.idempotency_key == idempotency_key,
        )
    )
    if existing is not None:
        raise WorldCharacterSetupConflictError(
            "setup_in_progress" if existing.status == "running" else "idempotency_replay"
        )
    running = db.scalar(
        select(models.WorldCharacterSetupAttempt.id).where(
            models.WorldCharacterSetupAttempt.world_character_id
            == scope.world_character.id,
            models.WorldCharacterSetupAttempt.stage == stage,
            models.WorldCharacterSetupAttempt.status == "running",
        )
    )
    if running is not None:
        raise WorldCharacterSetupConflictError("setup_in_progress")
    retry_of = db.scalar(
        select(models.WorldCharacterSetupAttempt.id)
        .where(
            models.WorldCharacterSetupAttempt.world_character_id
            == scope.world_character.id,
            models.WorldCharacterSetupAttempt.stage == stage,
            models.WorldCharacterSetupAttempt.status == "failed",
        )
        .order_by(models.WorldCharacterSetupAttempt.created_at.desc())
    )
    now = datetime.now(UTC)
    attempt = models.WorldCharacterSetupAttempt(
        id=uuid7_string(),
        owner_user_id=scope.character.owner_id,
        world_character_id=scope.world_character.id,
        stage=stage,
        status="running",
        idempotency_key=idempotency_key,
        retry_of_attempt_id=retry_of,
        provider=material.provider,
        model=material.model,
        credential_id=material.credential_id,
        consent_policy_version=consent_policy_version,
        consented_at=now,
        logical_call_count=1,
        physical_request_count=0,
        input_hash=input_hash,
        started_at=now,
    )
    db.add(attempt)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise WorldCharacterSetupConflictError("setup_in_progress") from exc
    return attempt


def _finish_attempt_success(
    db: Session,
    attempt: models.WorldCharacterSetupAttempt,
    *,
    result: world_character_provider.WorldCharacterProviderResult,
    output: Any,
) -> None:
    attempt.status = "succeeded"
    attempt.physical_request_count = result.physical_request_count
    attempt.output_hash = world_character_contracts.canonical_sha256(
        output.model_dump(mode="json") if hasattr(output, "model_dump") else output
    )
    attempt.prompt_token_count = result.prompt_token_count
    attempt.output_token_count = result.output_token_count
    attempt.total_token_count = result.total_token_count
    attempt.latency_ms = result.latency_ms
    attempt.finished_at = datetime.now(UTC)


def _finish_attempt_failure(
    db: Session,
    attempt: models.WorldCharacterSetupAttempt,
    exc: Exception,
) -> None:
    attempt.status = "failed"
    attempt.failure_class = type(exc).__name__[:80]
    attempt.safe_error_code = _safe_error_code(exc)
    attempt.physical_request_count = _physical_request_count(exc)
    attempt.finished_at = datetime.now(UTC)


def _safe_error_code(exc: Exception) -> str:
    if isinstance(exc, world_character_contracts.WorldCharacterContractError):
        return exc.reason_code
    if isinstance(exc, direct_llm.DirectLlmDeferred):
        return "provider_quota"
    if isinstance(exc, (TimeoutError, direct_llm.DirectLlmMaxCallsExceeded)):
        return "provider_timeout"
    if isinstance(exc, direct_llm.DirectLlmJsonError):
        return "provider_response_invalid"
    if isinstance(exc, WorldCharacterSetupError):
        return exc.reason_code
    return "provider_response_invalid"


def _physical_request_count(exc: Exception) -> int:
    value = getattr(exc, "attempt_count", None)
    return int(value) if isinstance(value, int) and value >= 0 else 1


def _public_stage_error(exc: Exception) -> WorldCharacterSetupError:
    if isinstance(exc, WorldCharacterSetupError):
        return exc
    return WorldCharacterSetupValidationError(_safe_error_code(exc))


def _require_profile_result(payload: Any) -> schemas.WorldCommunityProfilePayload:
    if isinstance(payload, schemas.WorldCommunityProfilePayload):
        return payload
    if isinstance(payload, dict):
        return world_character_contracts.validate_community_profile(payload)
    raise WorldCharacterSetupValidationError("profile_schema_invalid")


def _require_repertoire_result(
    payload: Any,
) -> world_character_contracts.ValidatedActivityRepertoire:
    if isinstance(payload, world_character_contracts.ValidatedActivityRepertoire):
        return payload
    raise WorldCharacterSetupValidationError("provider_response_invalid")


def _reload_and_assert_hashes(
    db: Session,
    *,
    scope: SetupScope,
    user: models.User,
    character_hash: str,
    world_hash: str,
) -> SetupScope:
    db.expire_all()
    current = _load_scope(
        db,
        world_character_id=scope.world_character.id,
        user=user,
        lock_for_update=True,
    )
    if (
        world_character_contracts.character_contract_hash(current.character)
        != character_hash
        or current.world.contract_hash != world_hash
    ):
        raise WorldCharacterSetupConflictError("contract_hash_stale")
    return current


def _save_profile_draft(
    db: Session,
    *,
    scope: SetupScope,
    material: CredentialMaterial,
    payload: schemas.WorldCommunityProfilePayload,
    character_hash: str,
    world_hash: str,
) -> models.WorldCommunityProfile:
    profile = models.WorldCommunityProfile(
        id=uuid7_string(),
        world_character_id=scope.world_character.id,
        status="draft",
        **payload.model_dump(mode="python"),
        schema_version=1,
        generator_version=world_character_contracts.WORLD_CHARACTER_GENERATOR_VERSION,
        character_contract_hash=character_hash,
        world_contract_hash=world_hash,
        provider=material.provider,
        model=material.model,
        credential_id=material.credential_id,
        generated_at=datetime.now(UTC),
    )
    db.add(profile)
    db.flush()
    return profile


def _save_repertoire_draft(
    db: Session,
    *,
    scope: SetupScope,
    material: CredentialMaterial,
    profile: models.WorldCommunityProfile,
    validated: world_character_contracts.ValidatedActivityRepertoire,
    character_hash: str,
    world_hash: str,
) -> models.WorldActivityRepertoire:
    repertoire = models.WorldActivityRepertoire(
        id=uuid7_string(),
        world_character_id=scope.world_character.id,
        status="draft",
        schema_version=world_character_contracts.REPERTOIRE_SCHEMA_VERSION,
        generator_version=world_character_contracts.WORLD_CHARACTER_GENERATOR_VERSION,
        character_contract_hash=character_hash,
        world_contract_hash=world_hash,
        community_profile_id=profile.id,
        provider=material.provider,
        model=material.model,
        credential_id=material.credential_id,
        validation_summary={
            "candidate_count": len(validated.candidates),
            "daypart_counts": validated.daypart_counts,
            "near_duplicate_pair_count": validated.near_duplicate_pair_count,
        },
        generated_at=datetime.now(UTC),
    )
    db.add(repertoire)
    db.flush()
    for candidate in validated.candidates:
        db.add(
            models.WorldActivityCandidate(
                id=uuid7_string(),
                repertoire_id=repertoire.id,
                ordinal=candidate.ordinal,
                canonical_signature=candidate.canonical_signature,
                enabled=True,
                **candidate.payload.model_dump(mode="python"),
            )
        )
    db.flush()
    return repertoire


def _ready_pair(
    db: Session,
    *,
    world_character_id: str,
    character_hash: str,
    world_hash: str,
) -> tuple[models.WorldCommunityProfile, models.WorldActivityRepertoire] | None:
    profile = db.scalar(
        select(models.WorldCommunityProfile).where(
            models.WorldCommunityProfile.world_character_id == world_character_id,
            models.WorldCommunityProfile.status == "ready",
            models.WorldCommunityProfile.character_contract_hash == character_hash,
            models.WorldCommunityProfile.world_contract_hash == world_hash,
        )
    )
    if profile is None:
        return None
    repertoire = db.scalar(
        select(models.WorldActivityRepertoire).where(
            models.WorldActivityRepertoire.world_character_id == world_character_id,
            models.WorldActivityRepertoire.community_profile_id == profile.id,
            models.WorldActivityRepertoire.status == "ready",
            models.WorldActivityRepertoire.character_contract_hash == character_hash,
            models.WorldActivityRepertoire.world_contract_hash == world_hash,
        )
    )
    if repertoire is None or len(_candidate_rows(db, repertoire.id)) != 40:
        return None
    return profile, repertoire


def _matching_profile(
    db: Session,
    *,
    world_character_id: str,
    character_hash: str,
    world_hash: str,
) -> models.WorldCommunityProfile | None:
    return db.scalar(
        select(models.WorldCommunityProfile)
        .where(
            models.WorldCommunityProfile.world_character_id == world_character_id,
            models.WorldCommunityProfile.status.in_(["draft", "ready"]),
            models.WorldCommunityProfile.character_contract_hash == character_hash,
            models.WorldCommunityProfile.world_contract_hash == world_hash,
        )
        .order_by(models.WorldCommunityProfile.created_at.desc())
    )


def _matching_repertoire(
    db: Session,
    *,
    world_character_id: str,
    profile_id: str,
    character_hash: str,
    world_hash: str,
) -> models.WorldActivityRepertoire | None:
    return db.scalar(
        select(models.WorldActivityRepertoire)
        .where(
            models.WorldActivityRepertoire.world_character_id == world_character_id,
            models.WorldActivityRepertoire.community_profile_id == profile_id,
            models.WorldActivityRepertoire.status.in_(["draft", "ready"]),
            models.WorldActivityRepertoire.character_contract_hash == character_hash,
            models.WorldActivityRepertoire.world_contract_hash == world_hash,
        )
        .order_by(models.WorldActivityRepertoire.created_at.desc())
    )


def _latest_profile(
    db: Session, world_character_id: str
) -> models.WorldCommunityProfile | None:
    return db.scalar(
        select(models.WorldCommunityProfile)
        .where(
            models.WorldCommunityProfile.world_character_id == world_character_id,
            models.WorldCommunityProfile.status.in_(
                ["draft", "ready", "stale", "failed"]
            ),
        )
        .order_by(models.WorldCommunityProfile.created_at.desc())
    )


def _latest_repertoire(
    db: Session, world_character_id: str
) -> models.WorldActivityRepertoire | None:
    return db.scalar(
        select(models.WorldActivityRepertoire)
        .where(
            models.WorldActivityRepertoire.world_character_id == world_character_id,
            models.WorldActivityRepertoire.status.in_(
                ["draft", "ready", "stale", "failed"]
            ),
        )
        .order_by(models.WorldActivityRepertoire.created_at.desc())
    )


def _candidate_rows(
    db: Session, repertoire_id: str
) -> list[models.WorldActivityCandidate]:
    rows = list(
        db.scalars(
            select(models.WorldActivityCandidate).where(
                models.WorldActivityCandidate.repertoire_id == repertoire_id,
                models.WorldActivityCandidate.enabled.is_(True),
            )
        )
    )
    order = {value: index for index, value in enumerate(world_character_contracts.DAYPARTS)}
    return sorted(rows, key=lambda row: (order[row.daypart], row.ordinal, row.id))


def _recent_candidate_signatures(db: Session, world_character_id: str) -> list[str]:
    repertoire_ids = list(
        db.scalars(
            select(models.WorldActivityRepertoire.id)
            .where(
                models.WorldActivityRepertoire.world_character_id == world_character_id
            )
            .order_by(models.WorldActivityRepertoire.created_at.desc())
            .limit(2)
        )
    )
    if not repertoire_ids:
        return []
    return list(
        db.scalars(
            select(models.WorldActivityCandidate.canonical_signature).where(
                models.WorldActivityCandidate.repertoire_id.in_(repertoire_ids)
            )
        )
    )[:80]


def _profile_payload(
    profile: models.WorldCommunityProfile,
) -> schemas.WorldCommunityProfilePayload:
    return schemas.WorldCommunityProfilePayload(
        visible_summary=profile.visible_summary,
        core_interests=profile.core_interests,
        adjacent_interests=profile.adjacent_interests,
        avoid_topics=profile.avoid_topics,
        discovery_openness=profile.discovery_openness,
        search_keywords=profile.search_keywords,
        action_profile=profile.action_profile,
    )


def _candidate_payload(
    row: models.WorldActivityCandidate,
) -> schemas.WorldActivityCandidatePayload:
    return schemas.WorldActivityCandidatePayload(
        daypart=row.daypart,
        activity_kind=row.activity_kind,
        title=row.title,
        activity_seed=row.activity_seed,
        place_key=row.place_key,
        social_mode=row.social_mode,
    )


def _profile_read(
    profile: models.WorldCommunityProfile,
) -> schemas.WorldCommunityProfileRead:
    return schemas.WorldCommunityProfileRead(
        id=profile.id,
        world_character_id=profile.world_character_id,
        status=profile.status,
        schema_version=profile.schema_version,
        generator_version=profile.generator_version,
        character_contract_hash=profile.character_contract_hash,
        world_contract_hash=profile.world_contract_hash,
        provider=profile.provider,
        model=profile.model,
        generated_at=profile.generated_at,
        approved_at=profile.approved_at,
        **_profile_payload(profile).model_dump(mode="python"),
    )


def _repertoire_read(
    repertoire: models.WorldActivityRepertoire,
    candidates: list[models.WorldActivityCandidate],
) -> schemas.WorldActivityRepertoireRead:
    return schemas.WorldActivityRepertoireRead(
        id=repertoire.id,
        world_character_id=repertoire.world_character_id,
        status=repertoire.status,
        schema_version=repertoire.schema_version,
        generator_version=repertoire.generator_version,
        character_contract_hash=repertoire.character_contract_hash,
        world_contract_hash=repertoire.world_contract_hash,
        community_profile_id=repertoire.community_profile_id,
        provider=repertoire.provider,
        model=repertoire.model,
        validation_summary=repertoire.validation_summary,
        generated_at=repertoire.generated_at,
        approved_at=repertoire.approved_at,
        candidates=[
            schemas.WorldActivityCandidateRead(
                id=row.id,
                repertoire_id=row.repertoire_id,
                ordinal=row.ordinal,
                canonical_signature=row.canonical_signature,
                enabled=row.enabled,
                **_candidate_payload(row).model_dump(mode="python"),
            )
            for row in candidates
        ],
    )


def _daypart_counts(
    rows: list[models.WorldActivityCandidate],
) -> dict[str, int]:
    return {
        daypart: sum(1 for row in rows if row.daypart == daypart)
        for daypart in world_character_contracts.DAYPARTS
    }
