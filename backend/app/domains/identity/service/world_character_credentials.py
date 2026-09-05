"""The existing agent-purpose BYOK lookup in the caller Session."""
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.domains.identity import models


def find_world_character_credential(db: Session, *, character_id: str):
    """Return the attached record for subsequent Identity credential resolution."""
    return db.scalar(
        select(models.LlmCredential)
        .where(models.LlmCredential.character_id == character_id)
        .where(models.LlmCredential.purpose == "agent")
    )
