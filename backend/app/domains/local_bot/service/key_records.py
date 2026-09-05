from datetime import UTC, datetime
from uuid import uuid4
from sqlalchemy.orm import Session
from app.core import security
from app.domains.local_bot import models
from app.domains.local_bot.contracts.key_management import LocalKeyOwner, LocalKeyCharacter
from app.domains.local_bot.repository import keys as key_repository


def create_local_key(
    db: Session,
    *,
    user: LocalKeyOwner,
    character: LocalKeyCharacter,
    token: str,
    token_prefix: str,
) -> models.AgentLocalKey:
    revoke_active_local_key(db, character.id, commit=False)
    key = models.AgentLocalKey(
        id=f"local-key-{uuid4().hex[:12]}",
        owner_id=user.id,
        character_id=character.id,
        token_hash=security.hash_token(token),
        token_prefix=token_prefix,
        enabled=True,
    )
    key_repository.add_key(db, key)
    key_repository.save_key(db, key)
    return key


def mark_local_key_used(
    db: Session, key: models.AgentLocalKey, *, used_at: datetime | None = None
) -> models.AgentLocalKey:
    key.last_used_at = used_at or datetime.now(UTC)
    key_repository.save_key(db, key)
    return key


def revoke_active_local_key(
    db: Session, character_id: str, *, commit: bool = True
) -> models.AgentLocalKey | None:
    key = key_repository.get_active_local_key(db, character_id)
    if key is None:
        return None
    key.enabled = False
    key.revoked_at = datetime.now(UTC)
    key_repository.save_key(db, key, commit=commit)
    return key
