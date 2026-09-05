"""Caller-owned message credentials: attached reads, flush-only writes.

No commit or rollback is performed here. Message preference choices, missing-key
errors and the enclosing transaction remain the responsibility of Chat.
"""

from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import security
from app.domains.identity.models import LlmCredential


def get_message_credential(db: Session, user_id: str) -> LlmCredential | None:
    return db.scalar(
        select(LlmCredential)
        .where(LlmCredential.owner_id == user_id)
        .where(LlmCredential.purpose == "message")
    )


def upsert_message_credential(
    db: Session, owner_id: str, api_key: str, model: str
) -> LlmCredential:
    credential = get_message_credential(db, owner_id)
    encrypted_api_key = security.encrypt_secret(
        api_key,
        scope=security.SecretScope(
            owner_id=owner_id, character_id="", provider="google", purpose="message"
        ),
    )
    fingerprint = security.fingerprint_secret(api_key)
    if credential is None:
        credential = LlmCredential(
            id=f"cred-msg-{uuid4().hex[:12]}",
            owner_id=owner_id,
            character_id=None,
            provider="google",
            purpose="message",
            model=model,
            auth_profile_id=f"google:message:{owner_id}",
            label="쪽지용 Google API key",
            encrypted_api_key=encrypted_api_key,
            key_fingerprint=fingerprint,
            enabled=True,
        )
        db.add(credential)
    else:
        credential.provider = "google"
        credential.model = model
        credential.encrypted_api_key = encrypted_api_key
        credential.key_fingerprint = fingerprint
        credential.enabled = True
    db.flush()
    return credential


def get_agent_credential(
    db: Session, owner_id: str, character_id: str
) -> LlmCredential | None:
    return db.scalar(
        select(LlmCredential)
        .where(LlmCredential.owner_id == owner_id)
        .where(LlmCredential.character_id == character_id)
        .where(LlmCredential.purpose == "agent")
    )


def clear_message_credential(credential: LlmCredential) -> None:
    credential.enabled = False
    credential.encrypted_api_key = None
    credential.key_fingerprint = None
