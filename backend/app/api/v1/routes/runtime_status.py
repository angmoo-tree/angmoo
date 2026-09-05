from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.api.v1.deps import get_current_user
from app.core import browser_session
from app.config import settings
from app.core.db import get_db
from app.domains.identity.public import (
    InstallationIdentity,
    LOCAL_INSTALLATION_KEY,
    User,
)
from app.domains.runtime.public import (
    LocalRuntimeStatusRead,
    ReadApplicationRuntimeStatus,
    SqlAlchemyApplicationRuntimeProbe,
    overlay_in_process_component_status,
    runtime_status_read,
)


router = APIRouter(prefix="/runtime", tags=["runtime"])


@router.get("/status", response_model=LocalRuntimeStatusRead)
def get_runtime_status(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> LocalRuntimeStatusRead:
    browser_session.require_local_frontend_request(request, mutation=False)
    installation = db.get(InstallationIdentity, LOCAL_INSTALLATION_KEY)
    if (
        installation is None
        or installation.bootstrap_state != "claimed"
        or installation.owner_user_id != current_user.id
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="local_owner_required",
        )
    runtime_settings = getattr(request.app.state, "runtime_settings", settings)
    runtime_config = getattr(request.app.state, "runtime_config", None)
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
