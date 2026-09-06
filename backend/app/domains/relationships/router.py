"""Owner diagnostics and relationship graph HTTP contracts."""
from __future__ import annotations
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session
from app.config import settings
from app.domains.relationships import schemas, exceptions as errors
from app.domains.relationships.contracts.diagnostics import DiagnosticsOwner, DiagnosticsReferences
from app.domains.relationships.contracts.graph_read import GraphProvider
from app.domains.relationships.service import diagnostics, graph_read
from app.domains.relationships.dependencies import get_current_user, get_db, get_read_references

router = APIRouter()


def _raise_social_memory_error(exc: errors.SocialMemoryReadError) -> None:
    if isinstance(exc, errors.SocialMemoryNotFoundError):
        status_code = status.HTTP_404_NOT_FOUND
    elif isinstance(exc, errors.SocialMemoryForbiddenError):
        status_code = status.HTTP_403_FORBIDDEN
    else:
        status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    raise HTTPException(status_code=status_code, detail=exc.reason_code) from exc


def _raise_relationship_graph_error(
    exc: errors.RelationshipGraphReadError,
) -> None:
    if isinstance(exc, errors.RelationshipGraphNotFoundError):
        status_code = status.HTTP_404_NOT_FOUND
    elif isinstance(exc, errors.RelationshipGraphForbiddenError):
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
    user: DiagnosticsOwner = Depends(get_current_user),
    references: DiagnosticsReferences = Depends(get_read_references),
) -> schemas.SocialMemoryDiagnosticsRead:
    """Return owner-only P6 evidence, directional relationships, and joint state."""

    runtime_settings = getattr(request.app.state, "runtime_settings", settings)
    try:
        return diagnostics.get_owner_diagnostics(
            db,
            character_id=character_id,
            world_id=world_id,
            user=user,
            references=references,
            config=runtime_settings,
        )
    except errors.SocialMemoryReadError as exc:
        _raise_social_memory_error(exc)


@router.get(
    "/{character_id}/worlds/{world_id}/relationship-graph",
    response_model=schemas.RelationshipGraphRead,
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
    user: DiagnosticsOwner = Depends(get_current_user),
    references: DiagnosticsReferences = Depends(get_read_references),
) -> schemas.RelationshipGraphRead:
    runtime_settings = getattr(request.app.state, "runtime_settings", settings)
    selected_provider: GraphProvider = (
        provider or runtime_settings.graph_provider
    )
    try:
        gateway = references.graph_gateway(
            graph_provider=selected_provider,
        )
        return graph_read.get_owner_relationship_graph(
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
    except errors.RelationshipGraphReadError as exc:
        _raise_relationship_graph_error(exc)
