from sqlalchemy import select
from sqlalchemy.orm import Session
from app import models
from app.domains.relationships.constants import (RELATIONSHIP_POINT_KINDS, RELATIONSHIP_POINT_PENDING, RELATIONSHIP_POINT_SELECTED, RELATIONSHIP_POINT_CONSUMED, RELATIONSHIP_POINT_EXPIRED, RELATIONSHIP_POINT_FAILED, RELATIONSHIP_POINT_ACTIVE_STATUSES)
from app.domains.relationships.utils.points import (relationship_point_pair_key, relationship_point_source_signature, relationship_point_chain_id, _relationship_point_payload)
from app.domains.relationships.repository.points import count_relationship_points_for_pair_since
from app.domains.relationships.service.points import (create_relationship_point, expire_relationship_points, list_pending_relationship_points, mark_relationship_point_selected, release_relationship_point_selection, mark_relationship_point_consumed, mark_relationship_point_replied, mark_relationship_point_failed)


def get_credential(db: Session, credential_id: str) -> models.LlmCredential | None:
    return db.get(models.LlmCredential, credential_id)


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
