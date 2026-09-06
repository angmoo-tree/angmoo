from __future__ import annotations

from typing import Any, Protocol

from app.core.redaction import redact_secret_text
from app.credentials import CredentialPurpose, CredentialResolutionError, CredentialResolver
from app.domains.characters.models import Character
from app.domains.identity.models import LlmCredential
from app.domains.routines.exceptions import CredentialRequiredError, CredentialSyncError
from app.domains.runtime.contracts import ResidentRuntimeError as OpenClawGatewayError


class SecretReloadClient(Protocol):
    async def reload_secrets(self) -> Any: ...


class SlotAuthProfiles(Protocol):
    OpenClawAuthProfileSyncError: type[Exception]

    def inspect_credential_slot(self, *, agent_id: str, user_id: str, character_id: str, credential: LlmCredential) -> dict[str, Any]: ...
    def bind_credential_to_slot(self, *, agent_id: str, user_id: str, character_id: str, credential: LlmCredential, api_key: str) -> Any: ...
    def release_credential_from_slot(self, *, agent_id: str, user_id: str, character_id: str, credential: LlmCredential) -> Any: ...


async def _ensure_slot_auth_profile(
    *,
    client: SecretReloadClient,
    openclaw_auth_profiles: SlotAuthProfiles,
    agent_id: str,
    user_id: str,
    character: Character,
    credential: LlmCredential,
) -> bool:
    try:
        profile = openclaw_auth_profiles.inspect_credential_slot(
            agent_id=agent_id,
            user_id=user_id,
            character_id=character.id,
            credential=credential,
        )
    except openclaw_auth_profiles.OpenClawAuthProfileSyncError as exc:
        raise CredentialSyncError(redact_secret_text(str(exc))) from exc
    if profile.get("matches") is True:
        return True
    try:
        material = CredentialResolver.resolve_llm_credential(
            credential,
            purpose=CredentialPurpose.PRIVATE_OPENCLAW,
            owner_id=user_id,
            character_id=character.id,
        )
        api_key = material.reveal()
    except CredentialResolutionError as exc:
        raise CredentialRequiredError("Agent credential key cannot be decrypted") from exc
    try:
        openclaw_auth_profiles.bind_credential_to_slot(
            agent_id=agent_id,
            user_id=user_id,
            character_id=character.id,
            credential=credential,
            api_key=api_key,
        )
        await client.reload_secrets()
        profile = openclaw_auth_profiles.inspect_credential_slot(
            agent_id=agent_id,
            user_id=user_id,
            character_id=character.id,
            credential=credential,
        )
    except openclaw_auth_profiles.OpenClawAuthProfileSyncError as exc:
        raise CredentialSyncError(redact_secret_text(str(exc))) from exc
    except OpenClawGatewayError as exc:
        raise CredentialSyncError(redact_secret_text(str(exc))) from exc
    if profile.get("matches") is not True:
        raise CredentialSyncError("OpenClaw auth profile preflight failed")
    return True


async def _release_slot_auth_profile(
    *,
    client: SecretReloadClient,
    openclaw_auth_profiles: SlotAuthProfiles,
    agent_id: str,
    user_id: str,
    character_id: str,
    credential: LlmCredential,
) -> None:
    try:
        openclaw_auth_profiles.release_credential_from_slot(
            agent_id=agent_id,
            user_id=user_id,
            character_id=character_id,
            credential=credential,
        )
        await client.reload_secrets()
    except openclaw_auth_profiles.OpenClawAuthProfileSyncError as exc:
        raise CredentialSyncError(redact_secret_text(str(exc))) from exc
    except OpenClawGatewayError as exc:
        raise CredentialSyncError(redact_secret_text(str(exc))) from exc
