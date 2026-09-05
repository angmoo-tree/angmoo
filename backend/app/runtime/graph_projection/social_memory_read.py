"""Compose owner diagnostics with actual source readers in the caller Session."""
from sqlalchemy.orm import Session
from app.config import Settings, settings
from app.domains.relationships import schemas
from app.domains.relationships.contracts.diagnostics import DiagnosticsOwner
from app.domains.relationships.exceptions import (
    SocialMemoryReadError, SocialMemoryNotFoundError, SocialMemoryForbiddenError,
)
from app.domains.relationships.service import diagnostics
from app.runtime.graph_projection.diagnostic_references import SqlAlchemyDiagnosticReferences


def get_owner_diagnostics(
    db: Session,
    *,
    character_id: str,
    world_id: str,
    user: DiagnosticsOwner,
    config: Settings = settings,
) -> schemas.SocialMemoryDiagnosticsRead:
    return diagnostics.get_owner_diagnostics(
        db, character_id=character_id, world_id=world_id, user=user, config=config,
        references=SqlAlchemyDiagnosticReferences(db, config),
    )
