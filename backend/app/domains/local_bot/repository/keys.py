from sqlalchemy import select
from sqlalchemy.orm import Session
from app.domains.local_bot import models


def get_active_local_key(
    db: Session, character_id: str
) -> models.AgentLocalKey | None:
    return db.scalar(
        select(models.AgentLocalKey)
        .where(models.AgentLocalKey.character_id == character_id)
        .where(models.AgentLocalKey.enabled.is_(True))
        .where(models.AgentLocalKey.revoked_at.is_(None))
        .order_by(
            models.AgentLocalKey.created_at.desc(),
            models.AgentLocalKey.id.desc(),
        )
        .limit(1)
    )


def get_active_local_key_by_hash(
    db: Session, token_hash: str
) -> models.AgentLocalKey | None:
    return db.scalar(
        select(models.AgentLocalKey)
        .where(models.AgentLocalKey.token_hash == token_hash)
        .where(models.AgentLocalKey.enabled.is_(True))
        .where(models.AgentLocalKey.revoked_at.is_(None))
        .limit(1)
    )


def get_latest_local_key(
    db: Session, character_id: str
) -> models.AgentLocalKey | None:
    return db.scalar(
        select(models.AgentLocalKey)
        .where(models.AgentLocalKey.character_id == character_id)
        .order_by(
            models.AgentLocalKey.created_at.desc(),
            models.AgentLocalKey.id.desc(),
        )
        .limit(1)
    )


def add_key(db: Session, key: models.AgentLocalKey) -> None:
    db.add(key)


def save_key(db: Session, key: models.AgentLocalKey, *, commit: bool = True) -> None:
    if commit:
        db.commit()
        db.refresh(key)
    else:
        db.flush()
