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
from app.domains.identity.exceptions import CredentialResolutionError
from app.domains.identity.schemas import WorldCredentialRead, WorldCredentialWrite, WorldCredentialDelete, WorldCredentialPurpose
from app.api.world_character_management_dependencies import credential_workflows
from app.domains.memory.exceptions import MemoryDomainError

router = APIRouter(prefix="/worlds", tags=["world-character-management"])


from app.api.world_character_management_dependencies import status_workflow
from app.api.world_character_management_dependencies import image_policy_workflows
from app.domains.media.schemas import WorldImagePolicyPatch
from app.domains.media.schemas import WorldImagePolicyRead
from pydantic import ValidationError
from app.domains.media.contracts import ImagePreparationError
from app.domains.world_characters.schemas.status import WorldCharacterStatusRead
from app.api.world_character_management_dependencies import instance_deletion_workflow
from app.domains.world_characters.schemas.deletion import WorldInstanceDelete
from app.domains.world_characters.schemas.deletion import WorldInstanceDeleteRead
from app.domains.media.service.http_workflows import require_comfy_raw_json


@router.get("/{world_id}/world-characters/{world_character_id}/status", response_model=WorldCharacterStatusRead)
def character_status(world_id: str, world_character_id: str, request: Request, user=Depends(get_current_user),
    service=Depends(get_management_service), workflow=Depends(status_workflow)):
    return _credential_call(workflow, service, request, world_id=world_id, world_character_id=world_character_id, user=user)


@router.delete("/{world_id}/world-characters/{world_character_id}/instance", response_model=WorldInstanceDeleteRead)
def delete_instance(world_id: str, world_character_id: str, data: WorldInstanceDelete, request: Request,
    user=Depends(get_current_user), service=Depends(get_management_service), workflow=Depends(instance_deletion_workflow)):
    return _credential_call(workflow, service, request, mutation=True, world_id=world_id,
        world_character_id=world_character_id, user=user, data=data)


@router.get("/{world_id}/world-characters/{world_character_id}/image-policy", response_model=WorldImagePolicyRead)
def read_image_policy(world_id: str, world_character_id: str, request: Request, user=Depends(get_current_user),
    service=Depends(get_management_service), workflows=Depends(image_policy_workflows)):
    return _credential_call(workflows.read, service, request, world_id=world_id, world_character_id=world_character_id, user=user)


@router.patch("/{world_id}/world-characters/{world_character_id}/image-policy", response_model=WorldImagePolicyRead, dependencies=[Depends(require_comfy_raw_json)])
def write_image_policy(world_id: str, world_character_id: str, data: WorldImagePolicyPatch, request: Request, user=Depends(get_current_user),
    service=Depends(get_management_service), workflows=Depends(image_policy_workflows)):
    return _credential_call(workflows.write, service, request, mutation=True, world_id=world_id, world_character_id=world_character_id, user=user, data=data)


@router.post("/{world_id}/world-characters/{world_character_id}/image-policy/check", response_model=WorldImagePolicyRead, dependencies=[Depends(require_comfy_raw_json)])
async def check_image_policy(world_id: str, world_character_id: str, data: WorldImagePolicyPatch, request: Request,
    user=Depends(get_current_user), service=Depends(get_management_service), workflows=Depends(image_policy_workflows)):
    browser_session.require_local_frontend_request(request, mutation=True)
    try:
        return await workflows.check(service, world_id=world_id, world_character_id=world_character_id, user=user, data=data)
    except (ImagePreparationError, CredentialResolutionError) as exc:
        service.db.rollback()
        raise HTTPException(409 if "conflict" in str(exc) else 422, detail=str(exc)) from exc
    except WorldManagementError as exc:
        service.db.rollback()
        raise HTTPException(exc.status_code, detail=exc.reason_code) from exc
    except ValidationError as exc:
        service.db.rollback()
        raise HTTPException(422, detail="world_image_policy_invalid") from exc


def _credential_call(workflow, service, request, *, mutation=False, **kwargs):
    browser_session.require_local_frontend_request(request, mutation=mutation)
    try:
        return workflow(service, **kwargs)
    except WorldManagementError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.reason_code) from None
    except worlds.WorldServiceError as exc:
        from app.api.world_errors import _raise_world_error
        _raise_world_error(exc)
    except CredentialResolutionError as exc:
        code = str(exc)
        raise HTTPException(status_code=409 if code.endswith("revision_conflict") else 422, detail=code) from None
    except MemoryDomainError as exc:
        code = str(exc)
        raise HTTPException(status_code=409 if code.endswith("revision_conflict") else 422, detail=code) from None
    except ImagePreparationError as exc:
        code = str(exc)
        raise HTTPException(status_code=409 if code.endswith("revision_conflict") else 422, detail=code) from None
    except (ValidationError, InvalidProfileMediaError) as exc:
        service.db.rollback()
        raise HTTPException(status_code=422, detail="world_image_policy_invalid") from exc


@router.get("/{world_id}/world-characters/{world_character_id}/credentials/{purpose}", response_model=WorldCredentialRead)
def credential_read(world_id: str, world_character_id: str, purpose: WorldCredentialPurpose, request: Request,
                    user=Depends(get_current_user), service=Depends(get_management_service), workflows=Depends(credential_workflows)):
    return _credential_call(workflows.read, service, request, world_id=world_id, world_character_id=world_character_id, user=user, purpose=purpose)


@router.put("/{world_id}/world-characters/{world_character_id}/credentials/{purpose}", response_model=WorldCredentialRead)
def credential_write(world_id: str, world_character_id: str, purpose: WorldCredentialPurpose, data: WorldCredentialWrite, request: Request,
                     user=Depends(get_current_user), service=Depends(get_management_service), workflows=Depends(credential_workflows)):
    return _credential_call(workflows.write, service, request, mutation=True, world_id=world_id, world_character_id=world_character_id, user=user, purpose=purpose, data=data)


@router.delete("/{world_id}/world-characters/{world_character_id}/credentials/{purpose}", response_model=WorldCredentialRead)
def credential_delete(world_id: str, world_character_id: str, purpose: WorldCredentialPurpose, data: WorldCredentialDelete, request: Request,
                      user=Depends(get_current_user), service=Depends(get_management_service), workflows=Depends(credential_workflows)):
    return _credential_call(workflows.write, service, request, mutation=True, world_id=world_id, world_character_id=world_character_id, user=user, purpose=purpose, data=data, remove=True)


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
