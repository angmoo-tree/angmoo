from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app import models, schemas
from app.api.v1.deps import get_current_user, get_db
from app.core.config import settings
from app.domains.relationships import public as relationships
from app.domains.routines import public as routines
from app.services import social_memory_read
from app.services.relationship_graph_read import (
    SqlAlchemyRelationshipGraphReadGateway,
)


router = APIRouter(prefix="/characters", tags=["world-activity-runtime"])


def _raise_plan_error(exc: routines.DailyActivityPlanError) -> None:
    if isinstance(exc, routines.DailyActivityPlanNotFoundError):
        status_code = status.HTTP_404_NOT_FOUND
    elif isinstance(exc, routines.DailyActivityPlanForbiddenError):
        status_code = status.HTTP_403_FORBIDDEN
    elif isinstance(exc, routines.DailyActivityPlanConflictError):
        status_code = status.HTTP_409_CONFLICT
    else:
        status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    raise HTTPException(status_code=status_code, detail=exc.reason_code) from exc

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
    "/{character_id}/worlds/{world_id}/activity-plan",
    response_model=schemas.DailyActivityPlanRead,
)
def get_daily_activity_plan(
    character_id: str,
    world_id: str,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
) -> schemas.DailyActivityPlanRead:
    try:
        return routines.get_activity_plan(
            db,
            character_id=character_id,
            world_id=world_id,
            user=user,
        )
    except routines.DailyActivityPlanError as exc:
        _raise_plan_error(exc)


@router.post(
    "/{character_id}/worlds/{world_id}/activity-plan/prepare",
    response_model=schemas.DailyActivityPlanRead,
)
def prepare_daily_activity_plan(
    character_id: str,
    world_id: str,
    data: schemas.DailyActivityPlanPrepareCreate,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
) -> schemas.DailyActivityPlanRead:
    try:
        return routines.prepare_activity_plan(
            db,
            character_id=character_id,
            world_id=world_id,
            user=user,
            data=data,
        )
    except routines.DailyActivityPlanError as exc:
        _raise_plan_error(exc)


@router.patch(
    "/{character_id}/worlds/{world_id}/activity-runtime-mode",
    response_model=schemas.WorldCharacterRuntimeModeRead,
)
def update_world_character_activity_runtime_mode(
    character_id: str,
    world_id: str,
    data: schemas.WorldCharacterRuntimeModeUpdate,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
) -> schemas.WorldCharacterRuntimeModeRead:
    try:
        return routines.update_activity_runtime_mode(
            db,
            character_id=character_id,
            world_id=world_id,
            user=user,
            data=data,
        )
    except routines.DailyActivityPlanError as exc:
        _raise_plan_error(exc)


@router.get(
    "/{character_id}/worlds/{world_id}/social-memory",
    response_model=schemas.SocialMemoryDiagnosticsRead,
)
def get_world_character_social_memory(
    character_id: str,
    world_id: str,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
) -> schemas.SocialMemoryDiagnosticsRead:
    """Return owner-only P6 evidence, directional relationships, and joint state."""

    try:
        return social_memory_read.get_owner_diagnostics(
            db,
            character_id=character_id,
            world_id=world_id,
            user=user,
        )
    except social_memory_read.SocialMemoryReadError as exc:
        _raise_social_memory_error(exc)


@router.get(
    "/{character_id}/worlds/{world_id}/relationship-graph",
    response_model=relationships.RelationshipGraphRead,
)
def get_world_character_relationship_graph(
    character_id: str,
    world_id: str,
    view: Literal["neighborhood", "direct", "evidence"] = Query(default="neighborhood"),
    target_world_character_id: str | None = Query(default=None, max_length=64),
    depth: int = Query(default=1, ge=1, le=2),
    limit: int = Query(default=20, ge=1, le=20),
    provider: Literal["neo4j", "ladybug"] = Query(default="neo4j"),
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
) -> relationships.RelationshipGraphRead:
    try:
        gateway = SqlAlchemyRelationshipGraphReadGateway(
            db,
            config=settings,
            graph_provider=provider,
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
            graph_projection_enabled=settings.graph_projection_enabled,
            graph_provider=provider,
        )
    except relationships.RelationshipGraphReadError as exc:
        _raise_relationship_graph_error(exc)
