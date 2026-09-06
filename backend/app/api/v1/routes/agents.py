import app.domains.social.exceptions as social_errors
from app.domains.characters.router import generate_agent_draft_media, generate_profile_media
from app.domains.characters.router import (
    get_agent_draft_media,
    upload_agent_draft_media,
    get_agent_draft_media_usage,
    get_agent_draft_media_candidate_content,
    apply_agent_draft_media_candidate,
    discard_agent_draft_media_candidate,
    upload_profile_media,
    get_profile_media_usage,
    get_agent_profile_media_candidate_content,
    apply_profile_media_candidate,
    discard_profile_media_candidate,
)
from app.domains.characters.router import (
    create_agent_draft,
    enhance_agent_draft_persona,
    complete_agent_draft,

    get_agent_draft,
    update_agent_draft,
    list_agents,
    create_agent,
    get_agent,
    update_profile,
    update_persona,
    update_promotion_usage,
    router as character_router,
)
from fastapi import APIRouter, Body, Depends, HTTPException, Response, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app import models, schemas
from app.domains.identity.dependencies import get_current_user
from app.core.db import get_db
from app.runtime.characters import creator as draft_service
from app.runtime.characters import management as agent_service
from app.domains.routines import exceptions as agent_run_service
from app.services import maintenance as maintenance_service
from app.services.direct_llm import DirectLlmDeferred, DirectLlmError, DirectLlmJsonError
from app.services.runtime_boundary import OpenClawGatewayAuthError, OpenClawGatewayError


router = APIRouter(prefix="/agents", tags=["agents"])
_character_routes = {route.name: route for route in character_router.routes}



def _raise_demo_account_locked(exc: Exception) -> None:
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc


router.routes.append(_character_routes["list_agents"])


router.routes.append(_character_routes["create_agent"])


router.routes.append(_character_routes["create_agent_draft"])


router.routes.append(_character_routes["get_agent_draft"])


router.routes.append(_character_routes["get_agent_draft_media"])


router.routes.append(_character_routes["update_agent_draft"])


router.routes.append(_character_routes["enhance_agent_draft_persona"])


router.routes.append(_character_routes["upload_agent_draft_media"])


router.routes.append(_character_routes["generate_agent_draft_media"])


router.routes.append(_character_routes["get_agent_draft_media_usage"])


router.routes.append(_character_routes["get_agent_draft_media_candidate_content"])


router.routes.append(_character_routes["apply_agent_draft_media_candidate"])


router.routes.append(_character_routes["discard_agent_draft_media_candidate"])


router.routes.append(_character_routes["complete_agent_draft"])


router.routes.append(_character_routes["get_agent"])


@router.delete("/{character_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_agent(
    character_id: str,
    data: schemas.AgentDeleteCreate,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
) -> Response:
    try:
        agent_service.delete_agent(db, user, character_id, data)
    except agent_service.AgentNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found") from exc
    except agent_service.DemoAccountLockedError as exc:
        _raise_demo_account_locked(exc)
    except agent_service.AgentDeleteConfirmationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="앵무 이름이 일치하지 않습니다.",
        ) from exc
    except agent_service.ActiveSlotBusyError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="앵무가 지금 활동 중이라 삭제할 수 없습니다. 잠시 뒤 다시 시도해주세요.",
        ) from exc
    except agent_service.AgentDeletionCredentialSyncError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="앵무 삭제 전 보안 자격 정리에 실패했습니다. 잠시 뒤 다시 시도해주세요.",
        ) from exc
    except agent_service.AgentDeletionMediaCleanupError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="앵무의 비공개 미디어 정리에 실패했습니다. 잠시 뒤 다시 시도해주세요.",
        ) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/{character_id}/local-connection",
    response_model=schemas.AgentLocalConnectionRead,
)
def get_local_connection(
    character_id: str,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
) -> schemas.AgentLocalConnectionRead:
    try:
        return agent_service.get_local_connection(db, user, character_id)
    except agent_service.AgentNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found") from exc
    except agent_service.AgentExecutionModeError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.post(
    "/{character_id}/local-key",
    response_model=schemas.AgentLocalKeyCreateRead,
    status_code=status.HTTP_201_CREATED,
)
def issue_local_key(
    character_id: str,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
) -> schemas.AgentLocalKeyCreateRead:
    try:
        return agent_service.issue_local_key(db, user, character_id)
    except agent_service.AgentNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found") from exc
    except agent_service.AgentExecutionModeError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.delete("/{character_id}/local-key", status_code=status.HTTP_204_NO_CONTENT)
def revoke_local_key(
    character_id: str,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
) -> Response:
    try:
        agent_service.revoke_local_key(db, user, character_id)
    except agent_service.AgentNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found") from exc
    except agent_service.AgentExecutionModeError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


router.routes.append(_character_routes["get_feed_cue"])


router.routes.append(_character_routes["give_feed_cue"])


router.routes.append(_character_routes["update_profile"])


router.routes.append(_character_routes["update_persona"])


router.routes.append(_character_routes["update_promotion_usage"])


router.routes.append(_character_routes["upload_profile_media"])


@router.get(
    "/{character_id}/image-settings",
    response_model=schemas.AgentImageGenerationSettingRead,
)
def get_image_settings(
    character_id: str,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
) -> schemas.AgentImageGenerationSettingRead:
    try:
        return agent_service.get_image_settings(db, user, character_id)
    except agent_service.AgentNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found") from exc


@router.put(
    "/{character_id}/image-settings",
    response_model=schemas.AgentImageGenerationSettingRead,
)
def update_image_settings(
    character_id: str,
    data: schemas.AgentImageGenerationSettingUpdate,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
) -> schemas.AgentImageGenerationSettingRead:
    try:
        return agent_service.update_image_settings(db, user, character_id, data)
    except agent_service.AgentNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found") from exc
    except agent_service.DemoAccountLockedError as exc:
        _raise_demo_account_locked(exc)
    except agent_service.AgentExecutionModeError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except (
        agent_service.ImageSettingsInvalidError,
        agent_service.UnsafeImagePromptError,
    ) as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc


@router.delete(
    "/{character_id}/image-settings/key",
    response_model=schemas.AgentImageGenerationSettingRead,
)
def delete_image_settings_key(
    character_id: str,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
) -> schemas.AgentImageGenerationSettingRead:
    try:
        return agent_service.update_image_settings(
            db,
            user,
            character_id,
            schemas.AgentImageGenerationSettingUpdate(clear_pollinations_api_key=True),
        )
    except agent_service.AgentNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found") from exc
    except agent_service.DemoAccountLockedError as exc:
        _raise_demo_account_locked(exc)
    except agent_service.AgentExecutionModeError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except (
        agent_service.ImageSettingsInvalidError,
        agent_service.UnsafeImagePromptError,
    ) as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc


@router.post(
    "/{character_id}/image-settings/seed",
    response_model=schemas.AgentImageGenerationSettingRead,
)
def upload_image_seed(
    character_id: str,
    data: schemas.AgentImageSeedUpload,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
) -> schemas.AgentImageGenerationSettingRead:
    try:
        return agent_service.upload_image_seed(db, user, character_id, data)
    except agent_service.AgentNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found") from exc
    except agent_service.DemoAccountLockedError as exc:
        _raise_demo_account_locked(exc)
    except agent_service.AgentExecutionModeError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except agent_service.InvalidProfileMediaError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc


@router.delete(
    "/{character_id}/image-settings/seed",
    response_model=schemas.AgentImageGenerationSettingRead,
)
def delete_image_seed(
    character_id: str,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
) -> schemas.AgentImageGenerationSettingRead:
    try:
        return agent_service.delete_image_seed(db, user, character_id)
    except agent_service.AgentNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found") from exc
    except agent_service.DemoAccountLockedError as exc:
        _raise_demo_account_locked(exc)
    except agent_service.AgentExecutionModeError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


router.routes.append(_character_routes["generate_profile_media"])


router.routes.append(_character_routes["get_profile_media_usage"])


router.routes.append(_character_routes["get_agent_profile_media_candidate_content"])


router.routes.append(_character_routes["apply_profile_media_candidate"])


router.routes.append(_character_routes["discard_profile_media_candidate"])


router.routes.append(_character_routes["update_credential"])


router.routes.append(_character_routes["get_credential_metadata"])


router.routes.append(_character_routes["delete_credential"])


router.routes.append(_character_routes["get_settings"])


router.routes.append(_character_routes["update_settings"])


router.routes.append(_character_routes["analyze_tendency"])


router.routes.append(_character_routes["activate_agent"])


router.routes.append(_character_routes["deactivate_agent"])


router.routes.append(_character_routes["run_now"])


router.routes.append(_character_routes["first_greeting"])
