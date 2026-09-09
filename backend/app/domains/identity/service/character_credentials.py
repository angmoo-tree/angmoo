"""Character credential defaults, secret scope and update policy."""
from uuid import uuid4
from sqlalchemy.orm import Session
from app.core import security
from app.domains.identity import models
from app.domains.identity.contracts import CredentialCharacter
from app.domains.identity.repository import credentials as credential_repository


def default_auth_profile_id(provider: str, character_id: str) -> str:
    safe_character_id = "".join(
        char if char.isalnum() or char in {"-", "_"} else "-" for char in character_id
    )
    return f"{provider}:{safe_character_id}"


def default_credential_model() -> str:
    return "gemini-3.1-flash-lite"


def upsert_credential(
    db: Session,
    *,
    user: models.User,
    character: CredentialCharacter,
    provider: str,
    model: str | None,
    api_key: str,
    auth_profile_id: str | None,
    label: str | None,
    commit: bool = True,
    thinking_level: str = "high",
) -> models.LlmCredential:
    credential = credential_repository.get_character_credential(db, character.id)
    profile_id = auth_profile_id or default_auth_profile_id(provider, character.id)
    credential_model = model or default_credential_model()
    encrypted_api_key = security.encrypt_secret(
        api_key,
        scope=security.SecretScope(
            owner_id=user.id,
            character_id=character.id,
            provider=provider,
            purpose="agent",
        ),
    )
    key_fingerprint = security.fingerprint_secret(api_key)
    if credential is None:
        credential = models.LlmCredential(
            id=f"cred-{uuid4().hex[:12]}",
            owner_id=user.id,
            character_id=character.id,
            provider=provider,
            purpose="agent",
            model=credential_model,
            auth_profile_id=profile_id,
            label=label or f"{character.name} {provider}",
            encrypted_api_key=encrypted_api_key,
            key_fingerprint=key_fingerprint,
            enabled=True,
        )
        credential_repository.add_credential(db, credential)
    else:
        credential.provider = provider
        credential.model = credential_model
        credential.auth_profile_id = profile_id
        credential.label = label or credential.label
        credential.encrypted_api_key = encrypted_api_key
        credential.key_fingerprint = key_fingerprint
        credential.enabled = True
    credential.thinking_level = thinking_level
    credential_repository.save_credential(db, credential, commit=commit)
    return credential
