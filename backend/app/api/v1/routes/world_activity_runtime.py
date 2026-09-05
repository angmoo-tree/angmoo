from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from app import models, schemas
from app.domains.identity.dependencies import get_current_user
from app.core.db import get_db
from app.config import settings
from app.domains.relationships import public as relationships
from app.domains.routines import router as routine_routes
from app.runtime.graph_projection import social_memory_read
from app.runtime.graph_projection.relationship_graph_read import (
    SqlAlchemyRelationshipGraphReadGateway,
)


router = APIRouter(prefix="/characters", tags=["world-activity-runtime"])
router.include_router(routine_routes.router)


def _raise_social_memory_error(exc: social_memory_read.SocialMemoryReadError) -> None:
    if isinstance(exc, social_memory_read.SocialMemoryNotFoundError):
        status_code = status.HTTP_404_NOT_FOUND
    elif isinstance(exc, social_memory_read.SocialMemoryForbiddenError):
        status_code = status.HTTP_403_FORBIDDEN
    else:
        status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    raise HTTPException(status_code=status_code, detail=exc.reason_code) from exc


def _raise_relationship_graph_error(
    exc: relationships.RelationshipGraphReadError,
) -> None:
    if isinstance(exc, relationships.RelationshipGraphNotFoundError):
        status_code = status.HTTP_404_NOT_FOUND
    elif isinstance(exc, relationships.RelationshipGraphForbiddenError):
        status_code = status.HTTP_403_FORBIDDEN
    else:
        status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    raise HTTPException(status_code=status_code, detail=exc.reason_code) from exc


@router.get(
    "/{character_id}/worlds/{world_id}/social-memory",
    response_model=schemas.SocialMemoryDiagnosticsRead,
)
def get_world_character_social_memory(
    request: Request,
    character_id: str,
    world_id: str,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
) -> schemas.SocialMemoryDiagnosticsRead:
    """Return owner-only P6 evidence, directional relationships, and joint state."""

    runtime_settings = getattr(request.app.state, "runtime_settings", settings)
    try:
        return social_memory_read.get_owner_diagnostics(
            db,
            character_id=character_id,
            world_id=world_id,
            user=user,
            config=runtime_settings,
        )
    except social_memory_read.SocialMemoryReadError as exc:
        _raise_social_memory_error(exc)


@router.get(
    "/{character_id}/worlds/{world_id}/relationship-graph",
    response_model=relationships.RelationshipGraphRead,
)
def get_world_character_relationship_graph(
    request: Request,
    character_id: str,
    world_id: str,
    view: Literal["neighborhood", "direct", "evidence"] = Query(default="neighborhood"),
    target_world_character_id: str | None = Query(default=None, max_length=64),
    depth: int = Query(default=1, ge=1, le=2),
    limit: int = Query(default=20, ge=1, le=20),
    provider: Literal["ladybug"] | None = Query(default=None),
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
) -> relationships.RelationshipGraphRead:
    runtime_settings = getattr(request.app.state, "runtime_settings", settings)
    selected_provider: relationships.GraphProvider = (
        provider or runtime_settings.graph_provider
    )
    try:
        gateway = SqlAlchemyRelationshipGraphReadGateway(
            db,
            config=runtime_settings,
            graph_provider=selected_provider,
        )
        return relationships.get_owner_relationship_graph(
            gateway,
            character_id=character_id,
            world_id=world_id,
            owner_id=user.id,
            view=view,
            target_world_character_id=target_world_character_id,
            depth=depth,
            limit=limit,
            graph_projection_enabled=runtime_settings.graph_projection_enabled,
            graph_provider=selected_provider,
        )
    except relationships.RelationshipGraphReadError as exc:
        _raise_relationship_graph_error(exc)
