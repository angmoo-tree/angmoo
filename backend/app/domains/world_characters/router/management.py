"""Local frontend scoped management routes; composition supplies concrete ports."""
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from app.api.identity_dependencies import get_current_user, browser_session
from app.database import get_db
from app.domains.world_characters.schemas import management as schemas
from app.domains.world_characters.service.management import WorldManagementError
from app.domains.worlds import service as worlds
from app.api.world_character_management_dependencies import get_management_service, profile_media_workflow, manual_activity_workflow
from app.api.world_character_management_contracts import WorldCharacterRunNowRead
from app.domains.characters import exceptions as character_errors
from app.domains.media.contracts import InvalidProfileMediaError

router = APIRouter(prefix="/worlds", tags=["world-character-management"])


def _call(service, method, request, *, mutation=False, **kwargs):
    browser_session.require_local_frontend_request(request, mutation=mutation)
    try:
        return getattr(service, method)(**kwargs)
    except WorldManagementError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.reason_code) from exc
    except worlds.WorldServiceError as exc:
        from app.api.world_errors import _raise_world_error
        _raise_world_error(exc)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="world_configuration_invalid") from exc


@router.get("/{world_id}/character-dashboard", response_model=schemas.WorldCharacterDashboardRead)
def dashboard(world_id: str, request: Request, user=Depends(get_current_user), service=Depends(get_management_service)):
    return _call(service, "dashboard", request, world_id=world_id, user=user)


@router.get("/{world_id}/world-characters/{world_character_id}/management", response_model=schemas.WorldCharacterManagementRead)
def management(world_id: str, world_character_id: str, request: Request, user=Depends(get_current_user), service=Depends(get_management_service)):
    return _call(service, "management", request, world_id=world_id, world_character_id=world_character_id, user=user)


@router.get("/{world_id}/world-characters/{world_character_id}/settings", response_model=schemas.WorldCharacterSettingsRead)
def settings(world_id: str, world_character_id: str, request: Request, user=Depends(get_current_user), service=Depends(get_management_service)):
    return _call(service, "settings", request, world_id=world_id, world_character_id=world_character_id, user=user)


@router.patch("/{world_id}/world-characters/{world_character_id}/profile", response_model=schemas.WorldCharacterManagementRead)
def patch_profile(world_id: str, world_character_id: str, data: schemas.WorldCharacterProfilePatch, request: Request, user=Depends(get_current_user), service=Depends(get_management_service)):
    return _call(service, "patch_profile", request, mutation=True, world_id=world_id, world_character_id=world_character_id, user=user, data=data)


@router.patch("/{world_id}/world-characters/{world_character_id}/settings", response_model=schemas.WorldCharacterSettingsRead)
def patch_settings(world_id: str, world_character_id: str, data: schemas.WorldCharacterSettingsPatch, request: Request, user=Depends(get_current_user), service=Depends(get_management_service)):
    return _call(service, "patch_settings", request, mutation=True, world_id=world_id, world_character_id=world_character_id, user=user, data=data)


@router.post("/{world_id}/world-characters/{world_character_id}/activate", response_model=schemas.WorldCharacterDashboardRead)
def activate(world_id: str, world_character_id: str, data: schemas.ExpectedWorldRevision, request: Request, user=Depends(get_current_user), service=Depends(get_management_service)):
    return _call(service, "set_autonomy", request, mutation=True, world_id=world_id, world_character_id=world_character_id, user=user, data=data, enabled=True)


@router.post("/{world_id}/world-characters/{world_character_id}/deactivate", response_model=schemas.WorldCharacterDashboardRead)
def deactivate(world_id: str, world_character_id: str, data: schemas.ExpectedWorldRevision, request: Request, user=Depends(get_current_user), service=Depends(get_management_service)):
    return _call(service, "set_autonomy", request, mutation=True, world_id=world_id, world_character_id=world_character_id, user=user, data=data, enabled=False)


@router.post("/{world_id}/world-characters/{world_character_id}/profile/media", response_model=schemas.WorldCharacterManagementRead)
def profile_media(world_id: str, world_character_id: str, data: schemas.WorldCharacterProfileMedia, request: Request, user=Depends(get_current_user), service=Depends(get_management_service), workflow=Depends(profile_media_workflow)):
    browser_session.require_local_frontend_request(request, mutation=True)
    try:
        return workflow(service, world_id=world_id, world_character_id=world_character_id, user=user, data=data)
    except WorldManagementError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.reason_code) from exc
    except worlds.WorldServiceError as exc:
        from app.api.world_errors import _raise_world_error
        _raise_world_error(exc)
    except (ValueError, InvalidProfileMediaError) as exc:
        raise HTTPException(status_code=422, detail="world_profile_media_invalid") from exc


@router.post("/{world_id}/world-characters/{world_character_id}/run-now", response_model=WorldCharacterRunNowRead)
async def run_now(world_id: str, world_character_id: str, data: schemas.ExpectedWorldRevision, request: Request, user=Depends(get_current_user), service=Depends(get_management_service), workflow=Depends(manual_activity_workflow)):
    browser_session.require_local_frontend_request(request, mutation=True)
    try:
        return await workflow(service, world_id=world_id, world_character_id=world_character_id, user=user, data=data)
    except WorldManagementError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.reason_code) from exc
    except worlds.WorldServiceError as exc:
        from app.api.world_errors import _raise_world_error
        _raise_world_error(exc)
