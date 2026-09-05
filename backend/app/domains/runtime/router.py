"""Owner-only Runtime status HTTP endpoint and stable response metadata."""
from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session
from app.api.identity_dependencies import browser_session
from app.config import settings
from app.domains.identity.service.runtime_access import is_runtime_owner
from app.domains.runtime.contracts.http import RuntimeOwner as User
from app.domains.runtime.dependencies import get_current_user, get_db, get_runtime_status_reader_factory
from app.domains.runtime.schemas import LocalRuntimeStatusRead, runtime_status_read
from app.domains.runtime.service.status import ReadApplicationRuntimeStatus
from app.domains.runtime.service.components import overlay_in_process_component_status

router = APIRouter(prefix="/runtime", tags=["runtime"])


@router.get("/status", response_model=LocalRuntimeStatusRead)
def get_runtime_status(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> LocalRuntimeStatusRead:
    browser_session.require_local_frontend_request(request, mutation=False)
    if not is_runtime_owner(db, current_user.id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="local_owner_required",
        )
    runtime_settings = getattr(request.app.state, "runtime_settings", settings)
    runtime_config = getattr(request.app.state, "runtime_config", None)
    SqlAlchemyApplicationRuntimeProbe = get_runtime_status_reader_factory(request)
    probe = (
        SqlAlchemyApplicationRuntimeProbe(db, config=runtime_settings)
        if runtime_config is not None
        else SqlAlchemyApplicationRuntimeProbe(db)
    )
    runtime_status = ReadApplicationRuntimeStatus(probe).execute()
    runtime_status = overlay_in_process_component_status(
        runtime_status,
        config=runtime_settings,
    )
    return runtime_status_read(
        runtime_status,
        runtime_profile=(
            runtime_config.profile.value if runtime_config is not None else None
        ),
        canonical_generation=(
            runtime_config.generation if runtime_config is not None else None
        ),
        persistence_provider="sqlite",
        graph_provider=runtime_settings.graph_provider,
    )
