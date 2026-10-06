"""Routine admission wiring, independent of character management and workers."""
from app.config import settings
from app.credentials import CredentialPurpose, CredentialResolutionError, CredentialResolver
from app.domains.characters.exceptions import CredentialRequiredError, CredentialSyncError
from app.domains.characters.service.access import _ensure_llm_mode, _ensure_not_suspended
from app.domains.identity.repository import credentials
from app.domains.operations.service import maintenance
from app.domains.routines.contracts.autonomy_admission import AutonomyAdmissionReferences
from app.domains.world_characters.service import readiness
from app.runtime.extensions.resident_adapter import OpenClawGatewayClient, OpenClawGatewayError, openclaw_auth_profiles
from app.runtime.resident.autonomy_reads import count_effective_active_server_llm_autonomy_agents
from app.runtime.resident.slots import prepare_resident_slot_assignment


def resident_profile_sync_enabled():
    return settings.agent_activity_engine == "openclaw"


def bind_resident_profile(slot, *, user_id, character, credential):
    try:
        material = CredentialResolver.resolve_llm_credential(credential, purpose=CredentialPurpose.PRIVATE_OPENCLAW,
            owner_id=user_id, character_id=character.id)
        openclaw_auth_profiles.bind_credential_to_slot(agent_id=slot.agent_id, user_id=user_id,
            character_id=character.id, credential=credential, api_key=material.reveal())
    except CredentialResolutionError as exc:
        raise CredentialRequiredError("Agent credential key cannot be decrypted") from exc
    except openclaw_auth_profiles.OpenClawAuthProfileSyncError as exc:
        raise CredentialSyncError(str(exc)) from exc


def release_resident_profile(slot, *, user_id, character_id, credential):
    try:
        openclaw_auth_profiles.release_credential_from_slot(agent_id=slot.agent_id, user_id=user_id,
            character_id=character_id, credential=credential)
    except openclaw_auth_profiles.OpenClawAuthProfileSyncError as exc:
        raise CredentialSyncError(str(exc)) from exc


def reload_resident_secrets():
    token = settings.openclaw_gateway_token
    if token is None:
        return
    try:
        OpenClawGatewayClient(url=settings.openclaw_gateway_url, token=token,
            timeout_seconds=settings.openclaw_timeout_seconds).reload_secrets_sync()
    except OpenClawGatewayError as exc:
        raise CredentialSyncError(str(exc)) from exc


def build_autonomy_admission_references(*, evaluate_readiness=None, assign_slot=None,
    sync_enabled=None, bind_profile=None, release_profile=None, reload_secrets=None):
    return AutonomyAdmissionReferences(ensure_not_suspended=_ensure_not_suspended, ensure_llm_mode=_ensure_llm_mode,
        ensure_auto_ticks_available=maintenance.ensure_auto_ticks_available,
        evaluate_readiness=evaluate_readiness or readiness.evaluate,
        get_credential=credentials.get_character_credential,
        count_effective_agents=count_effective_active_server_llm_autonomy_agents,
        assign_slot=assign_slot or prepare_resident_slot_assignment,
        sync_enabled=sync_enabled or resident_profile_sync_enabled,
        bind_profile=bind_profile or bind_resident_profile,
        release_profile=release_profile or release_resident_profile,
        reload_secrets=reload_secrets or reload_resident_secrets)
