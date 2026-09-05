from __future__ import annotations

from app.domains.routines.contracts.run_identity import RunCharacter, RunCredential, RunIdentityReferences
from app.domains.routines.exceptions import CharacterOwnershipError, CredentialNotFoundError, CredentialOwnershipError, CredentialDisabledError


def _read_available_run_character(references: RunIdentityReferences, character_id: str) -> RunCharacter:
    character = references.get_character(character_id)
    if character is None or character.deleted_at is not None:
        raise references.character_not_found(character_id)
    if character.moderation_status == "suspended":
        raise references.character_suspended("character_suspended")
    return character


def _resolve_run_owner(character: RunCharacter, requested_user_id: str | None) -> str:
    user_id = requested_user_id or character.owner_id
    if character.owner_id != user_id:
        raise CharacterOwnershipError(
            f"user {user_id} cannot run character {character.id}"
        )
    return user_id


def _resolve_run_credential(references: RunIdentityReferences, *, user_id: str, character: RunCharacter, credential_id: str | None) -> RunCredential:
    credential = None
    if credential_id:
        credential = references.get_credential(credential_id)
        if credential is None:
            raise CredentialNotFoundError(credential_id)
        if credential.owner_id != user_id:
            raise CredentialOwnershipError(
                f"user {user_id} cannot use credential {credential_id}"
            )
        if credential.character_id is not None and credential.character_id != character.id:
            raise CredentialOwnershipError(
                f"credential {credential_id} is not assigned to character {character.id}"
            )
        if not credential.enabled:
            raise CredentialDisabledError(credential_id)
    else:
        credential = references.get_default_credential(
            user_id, character_id=character.id
        )
        if credential is None:
            raise CredentialNotFoundError(
                f"No enabled credential is assigned to character {character.id}"
            )
    return credential
