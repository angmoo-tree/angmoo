from sqlalchemy import case, select
from sqlalchemy.orm import Session
from app.domains.identity import models


def get_character_credential(
    db: Session, character_id: str
) -> models.LlmCredential | None:
    return db.scalar(
        select(models.LlmCredential)
        .where(models.LlmCredential.character_id == character_id)
        .where(models.LlmCredential.purpose == "agent")
    )


def get_credential(db: Session, credential_id: str) -> models.LlmCredential | None:
    return db.get(models.LlmCredential, credential_id)


def embedding_credential_options(db: Session, owner_id: str, selected_id: str | None = None) -> list[dict[str, str]]:
    """Owner-only selection metadata, never key material or fingerprints."""
    rows = db.execute(select(models.LlmCredential.id, models.LlmCredential.label).where(
        models.LlmCredential.owner_id == owner_id,
        models.LlmCredential.enabled.is_(True),
        models.LlmCredential.provider == "google",
        models.LlmCredential.purpose.in_(("agent", "message")),
    ).order_by(case((models.LlmCredential.id == selected_id, 0), else_=1),
               models.LlmCredential.created_at, models.LlmCredential.id).limit(200)).all()
    return [{"id": row.id, "label": row.label} for row in rows]


def get_default_credential(
    db: Session, owner_id: str, character_id: str | None = None
) -> models.LlmCredential | None:
    query = select(models.LlmCredential).where(
        models.LlmCredential.owner_id == owner_id,
        models.LlmCredential.enabled.is_(True),
    )
    if character_id is not None:
        query = query.where(models.LlmCredential.character_id == character_id)
    return db.scalar(
        query.order_by(models.LlmCredential.created_at.asc(), models.LlmCredential.id.asc())
    )


def add_credential(db: Session, credential: models.LlmCredential) -> None:
    db.add(credential)


def save_credential(db: Session, credential: models.LlmCredential, *, commit: bool = True) -> None:
    if commit:
        db.commit()
        db.refresh(credential)
    else:
        db.flush()
