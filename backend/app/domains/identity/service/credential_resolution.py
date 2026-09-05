from __future__ import annotations

from collections.abc import Collection
from typing import Any

from app.core import security
from app.domains.identity.contracts import (
    CredentialMaterial,
    CredentialPurpose,
)


from app.domains.identity.exceptions import CredentialResolutionError


_DEFAULT_STORED_PURPOSES: dict[CredentialPurpose, frozenset[str]] = {
    CredentialPurpose.RESIDENT_LLM: frozenset({"agent"}),
    CredentialPurpose.WORLD_CHARACTER_SETUP_LLM: frozenset({"agent"}),
    CredentialPurpose.MESSAGE_LLM: frozenset({"agent", "message"}),
    CredentialPurpose.LORE_EMBEDDING: frozenset({"agent"}),
    CredentialPurpose.PRIVATE_OPENCLAW: frozenset({"agent"}),
}


class CredentialResolver:
    @classmethod
    def resolve_llm_credential(
        cls,
        credential: Any,
        *,
        purpose: CredentialPurpose,
        owner_id: str | None = None,
        character_id: str | None = None,
        allowed_stored_purposes: Collection[str] | None = None,
        require_enabled: bool = True,
    ) -> CredentialMaterial:
        if credential is None:
            raise CredentialResolutionError("credential is missing")
        if require_enabled and not bool(getattr(credential, "enabled", False)):
            raise CredentialResolutionError("credential is disabled")
        if owner_id is not None and getattr(credential, "owner_id", None) != owner_id:
            raise CredentialResolutionError("credential owner does not match")
        assigned_character_id = getattr(credential, "character_id", None)
        if (
            character_id is not None
            and assigned_character_id is not None
            and assigned_character_id != character_id
        ):
            raise CredentialResolutionError("credential character does not match")
        stored_purpose = str(getattr(credential, "purpose", "") or "")
        accepted = (
            frozenset(allowed_stored_purposes)
            if allowed_stored_purposes is not None
            else _DEFAULT_STORED_PURPOSES.get(purpose)
        )
        if accepted is not None and stored_purpose not in accepted:
            raise CredentialResolutionError("credential purpose does not match")
        return cls.resolve_encrypted_material(
            encrypted_secret=getattr(credential, "encrypted_api_key", None),
            credential_id=str(getattr(credential, "id", "") or ""),
            provider=str(getattr(credential, "provider", "") or ""),
            model=str(getattr(credential, "model", "") or ""),
            fingerprint=getattr(credential, "key_fingerprint", None),
            purpose=purpose,
            owner_id=str(getattr(credential, "owner_id", "") or ""),
            character_id=str(getattr(credential, "character_id", "") or ""),
            stored_purpose=stored_purpose,
        )

    @classmethod
    def resolve_draft_credential(
        cls,
        draft: Any,
    ) -> CredentialMaterial:
        return cls.resolve_encrypted_material(
            encrypted_secret=getattr(draft, "encrypted_api_key", None),
            credential_id=str(getattr(draft, "id", "") or ""),
            provider=str(getattr(draft, "provider", "") or ""),
            model=str(getattr(draft, "model", "") or ""),
            fingerprint=getattr(draft, "key_fingerprint", None),
            purpose=CredentialPurpose.CREATION_DRAFT_LLM,
            owner_id=str(getattr(draft, "user_id", "") or ""),
            character_id="",
            stored_purpose="creation_draft",
        )

    @staticmethod
    def resolve_encrypted_material(
        *,
        encrypted_secret: str | None,
        credential_id: str,
        provider: str,
        model: str,
        fingerprint: str | None,
        purpose: CredentialPurpose,
        owner_id: str | None = None,
        character_id: str | None = None,
        stored_purpose: str | None = None,
    ) -> CredentialMaterial:
        if not encrypted_secret:
            raise CredentialResolutionError("credential key is missing")
        scope = (
            security.SecretScope(
                owner_id=owner_id or "",
                character_id=character_id or "",
                provider=provider,
                purpose=stored_purpose or purpose.value,
            )
            if owner_id is not None or stored_purpose is not None
            else None
        )
        try:
            secret = security.decrypt_secret(encrypted_secret, scope=scope).strip()
        except ValueError as exc:
            raise CredentialResolutionError(
                "credential key cannot be decrypted"
            ) from exc
        if not secret:
            raise CredentialResolutionError("credential key is empty")
        return CredentialMaterial(
            credential_id=credential_id,
            provider=provider,
            model=model,
            fingerprint=fingerprint,
            purpose=purpose,
            _secret=secret,
        )

    @staticmethod
    def migrate_local_envelope(
        encrypted_secret: str,
        *,
        scope: security.SecretScope,
    ) -> str:
        """Validate a local envelope and return its current local-v2 form."""

        try:
            plaintext = security.decrypt_secret(encrypted_secret, scope=scope).strip()
        except ValueError as exc:
            raise CredentialResolutionError(
                "credential key cannot be decrypted"
            ) from exc
        if not plaintext:
            raise CredentialResolutionError("credential key is empty")
        if encrypted_secret.startswith(f"{security.LOCAL_SECRET_PREFIX}:"):
            return encrypted_secret
        if not encrypted_secret.startswith(
            f"{security.LEGACY_LOCAL_SECRET_PREFIX}:"
        ):
            raise CredentialResolutionError("credential envelope is not local")
        migrated = security.encrypt_local_secret(plaintext, scope=scope)
        try:
            if security.decrypt_secret(migrated, scope=scope) != plaintext:
                raise CredentialResolutionError("credential migration canary failed")
        except ValueError as exc:
            raise CredentialResolutionError(
                "credential migration canary failed"
            ) from exc
        return migrated

    @classmethod
    def resolve_configured_secret(
        cls,
        value: str | None,
        *,
        credential_id: str,
        provider: str,
        model: str,
        purpose: CredentialPurpose,
    ) -> CredentialMaterial | None:
        raw_value = (value or "").strip()
        if not raw_value:
            return None
        if raw_value.startswith(
            (
                f"{security.OCI_KMS_SECRET_PREFIX}:",
                f"{security.LOCAL_SECRET_PREFIX}:",
                f"{security.LEGACY_LOCAL_SECRET_PREFIX}:",
            )
        ):
            return cls.resolve_encrypted_material(
                encrypted_secret=raw_value,
                credential_id=credential_id,
                provider=provider,
                model=model,
                fingerprint=None,
                purpose=purpose,
            )
        return CredentialMaterial(
            credential_id=credential_id,
            provider=provider,
            model=model,
            fingerprint=None,
            purpose=purpose,
            _secret=raw_value,
        )
