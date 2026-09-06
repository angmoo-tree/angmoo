from __future__ import annotations

from app.domains.routines.contracts.run_identity import RunCharacter, RunCredential, RunIdentityReferences
from app.domains.routines.exceptions import CharacterOwnershipError, CredentialNotFoundError, CredentialOwnershipError, CredentialDisabledError


def _validate_character_and_credential(
    references: RunIdentityReferences,
    *,
    user_id: str,
    character_id: str,
    credential_id: str,
) -> tuple[RunCharacter, RunCredential]:
    character = references.get_character(character_id)
    if character is None or character.deleted_at is not None:
        raise references.character_not_found(character_id)
    if character.owner_id != user_id:
        raise CharacterOwnershipError(
            f"user {user_id} cannot run character {character.id}"
        )

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

    return character, credential
