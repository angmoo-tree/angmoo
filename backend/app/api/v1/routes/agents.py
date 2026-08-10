from fastapi import APIRouter, Body, Depends, HTTPException, Response, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app import models, schemas
from app.api.v1.deps import get_current_user, get_db
from app.services import agent_creation_drafts as draft_service
from app.services import agents as agent_service
from app.services import agent_runs as agent_run_service
from app.services import community as community_service
from app.services import maintenance as maintenance_service
from app.services import profile_media
from app.services.direct_llm import DirectLlmDeferred, DirectLlmError, DirectLlmJsonError
from app.services.runtime_boundary import OpenClawGatewayAuthError, OpenClawGatewayError


router = APIRouter(prefix="/agents", tags=["agents"])
TENDENCY_ANALYSIS_RETRY_DETAIL = (
    "성향 분석 결과를 정리하지 못했습니다. 잠시 후 다시 시도해주세요."
)


def _raise_demo_account_locked(exc: Exception) -> None:
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc


@router.get("", response_model=list[schemas.AgentDetailRead])
def list_agents(
    db: Session = Depends(get_db), user: models.User = Depends(get_current_user)
) -> list[schemas.AgentDetailRead]:
    return agent_service.list_agents(db, user)


@router.post("", response_model=schemas.AgentDetailRead, status_code=status.HTTP_201_CREATED)
def create_agent(
    data: schemas.AgentCreate,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
) -> schemas.AgentDetailRead:
    try:
        return agent_service.create_agent(db, user, data)
    except agent_service.AgentLimitError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except agent_service.AgentHandleConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except agent_service.AgentHandleInvalidError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except agent_service.AgentActiveHoursInvalidError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except agent_service.PromptInjectionDetectedError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc


@router.post(
    "/drafts",
    response_model=schemas.AgentCreationDraftRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_agent_draft(
    data: schemas.AgentCreationDraftCreate,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
) -> schemas.AgentCreationDraftRead:
    try:
        return await draft_service.create_draft(db, user, data)
    except agent_service.AgentLimitError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except agent_service.CredentialSyncError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    except agent_run_service.AgentSlotUnavailableError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except OpenClawGatewayAuthError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="OpenClaw Gateway authentication failed",
        ) from exc
    except OpenClawGatewayError as exc:
        credential_error = agent_service.llm_credential_error_message(exc)
        if credential_error is not None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=credential_error) from exc
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc


@router.get("/drafts/{draft_id}", response_model=schemas.AgentCreationDraftRead)
def get_agent_draft(
    draft_id: str,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
) -> schemas.AgentCreationDraftRead:
    try:
        return draft_service.get_draft(db, user, draft_id)
    except draft_service.AgentCreationDraftNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Draft not found") from exc


@router.get("/drafts/{draft_id}/media/{media_type}", response_class=FileResponse)
def get_agent_draft_media(
    draft_id: str,
    media_type: str,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
) -> FileResponse:
    try:
        path, content_type = draft_service.get_draft_media_content(
            db,
            user,
            draft_id,
            media_type,
        )
    except (
        draft_service.AgentCreationDraftNotFoundError,
        draft_service.AgentPrivateMediaNotFoundError,
    ) as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Draft media not found",
        ) from exc
    return FileResponse(
        path,
        media_type=content_type,
        headers={
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.patch("/drafts/{draft_id}", response_model=schemas.AgentCreationDraftRead)
def update_agent_draft(
    draft_id: str,
    data: schemas.AgentCreationDraftUpdate,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
) -> schemas.AgentCreationDraftRead:
    try:
        return draft_service.update_draft(db, user, draft_id, data)
    except draft_service.AgentCreationDraftNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Draft not found") from exc
    except draft_service.AgentCreationDraftHandleConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except draft_service.AgentCreationDraftValidationError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc


@router.post(
    "/drafts/{draft_id}/enhance-persona",
    response_model=schemas.AgentCreationDraftRead,
)
async def enhance_agent_draft_persona(
    draft_id: str,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
) -> schemas.AgentCreationDraftRead:
    try:
        return await draft_service.enhance_persona(db, user, draft_id)
    except draft_service.AgentCreationDraftNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Draft not found") from exc
    except draft_service.AgentCreationDraftCooldownError as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"페르소나 보강은 {exc.available_at.isoformat()} 이후 다시 시도할 수 있습니다.",
        ) from exc
    except agent_service.CredentialRequiredError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except agent_service.CredentialSyncError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    except agent_run_service.AgentSlotUnavailableError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except draft_service.AgentCreationDraftParseError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    except draft_service.AgentCreationDraftValidationError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except OpenClawGatewayAuthError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="OpenClaw Gateway authentication failed",
        ) from exc
    except OpenClawGatewayError as exc:
        credential_error = agent_service.llm_credential_error_message(exc)
        if credential_error is not None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=credential_error) from exc
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc


@router.post("/drafts/{draft_id}/media", response_model=schemas.AgentCreationDraftRead)
def upload_agent_draft_media(
    draft_id: str,
    data: schemas.AgentCreationDraftMediaUpload,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
) -> schemas.AgentCreationDraftRead:
    try:
        return draft_service.upload_draft_media(db, user, draft_id, data)
    except draft_service.AgentCreationDraftNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Draft not found") from exc
    except profile_media.InvalidProfileMediaError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc


@router.post(
    "/drafts/{draft_id}/generate-media",
    response_model=schemas.AgentCreationDraftMediaGenerationRead,
)
async def generate_agent_draft_media(
    draft_id: str,
    data: schemas.AgentCreationDraftGenerateMediaCreate,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
) -> schemas.AgentCreationDraftMediaGenerationRead:
    try:
        return await draft_service.generate_media(db, user, draft_id, data)
    except draft_service.AgentCreationDraftNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Draft not found") from exc
    except draft_service.AgentCreationDraftCooldownError as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"이미지 생성은 {exc.available_at.isoformat()} 이후 다시 시도할 수 있습니다.",
        ) from exc


@router.get(
    "/drafts/{draft_id}/media-usage",
    response_model=schemas.AgentProfileImageUsageRead,
)
def get_agent_draft_media_usage(
    draft_id: str,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
) -> schemas.AgentProfileImageUsageRead:
    try:
        return draft_service.get_draft_profile_image_usage(db, user, draft_id)
    except draft_service.AgentCreationDraftNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Draft not found") from exc


@router.get(
    "/drafts/{draft_id}/media-candidates/{candidate_id}/content",
    response_class=FileResponse,
)
def get_agent_draft_media_candidate_content(
    draft_id: str,
    candidate_id: str,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
) -> FileResponse:
    try:
        path, content_type = draft_service.get_draft_candidate_content(
            db,
            user,
            draft_id,
            candidate_id,
        )
    except (
        draft_service.AgentCreationDraftNotFoundError,
        draft_service.AgentProfileImageCandidateNotFoundError,
    ) as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Candidate not found",
        ) from exc
    return FileResponse(
        path,
        media_type=content_type,
        headers={
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.post(
    "/drafts/{draft_id}/media-candidates/{candidate_id}/apply",
    response_model=schemas.AgentCreationDraftRead,
)
def apply_agent_draft_media_candidate(
    draft_id: str,
    candidate_id: str,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
) -> schemas.AgentCreationDraftRead:
    try:
        return draft_service.apply_draft_media_candidate(db, user, draft_id, candidate_id)
    except draft_service.AgentCreationDraftNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Draft not found") from exc
    except draft_service.AgentProfileImageCandidateNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Candidate not found") from exc
    except profile_media.InvalidProfileMediaError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc


@router.delete(
    "/drafts/{draft_id}/media-candidates/{candidate_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def discard_agent_draft_media_candidate(
    draft_id: str,
    candidate_id: str,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
) -> Response:
    try:
        draft_service.discard_draft_media_candidate(db, user, draft_id, candidate_id)
    except draft_service.AgentCreationDraftNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Draft not found") from exc
    except draft_service.AgentProfileImageCandidateNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Candidate not found") from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/drafts/{draft_id}/complete", response_model=schemas.AgentDetailRead)
def complete_agent_draft(
    draft_id: str,
    data: schemas.AgentCreationDraftComplete | None = Body(default=None),
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
) -> schemas.AgentDetailRead:
    try:
        return draft_service.complete_draft(
            db, user, draft_id, data or schemas.AgentCreationDraftComplete()
        )
    except draft_service.AgentCreationDraftNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Draft not found") from exc
    except draft_service.AgentCreationDraftValidationError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except agent_service.AgentLimitError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except agent_service.AgentHandleConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except agent_service.AgentHandleInvalidError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except agent_service.AgentActiveHoursInvalidError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except agent_service.PromptInjectionDetectedError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except agent_service.CredentialRequiredError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except profile_media.InvalidProfileMediaError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc


@router.get("/{character_id}", response_model=schemas.AgentDetailRead)
def get_agent(
    character_id: str,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
) -> schemas.AgentDetailRead:
    try:
        return agent_service.get_agent(db, user, character_id)
    except agent_service.AgentNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found") from exc


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


@router.get("/{character_id}/feed-cue", response_model=schemas.AgentFeedCueRead | None)
def get_feed_cue(
    character_id: str,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
) -> schemas.AgentFeedCueRead | None:
    try:
        return agent_service.get_feed_cue(db, user, character_id)
    except agent_service.AgentNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found") from exc
    except agent_service.AgentExecutionModeError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.post(
    "/{character_id}/feed-cue",
    response_model=schemas.AgentFeedCueRead,
    status_code=status.HTTP_201_CREATED,
)
def give_feed_cue(
    character_id: str,
    data: schemas.AgentFeedCueCreate,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
) -> schemas.AgentFeedCueRead:
    try:
        return agent_service.give_feed_cue(db, user, character_id, data)
    except maintenance_service.AgentActivityMaintenanceError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc
    except agent_service.AgentNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found") from exc
    except agent_service.AgentSuspendedError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except (
        agent_service.AgentFeedCueConflictError,
        agent_service.AgentFeedCueUnavailableError,
        agent_service.AgentExecutionModeError,
    ) as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except agent_service.PromptInjectionDetectedError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc


@router.put("/{character_id}/profile", response_model=schemas.AgentDetailRead)
def update_profile(
    character_id: str,
    data: schemas.AgentProfileUpdate,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
) -> schemas.AgentDetailRead:
    try:
        return agent_service.update_profile(db, user, character_id, data)
    except agent_service.AgentNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found") from exc
    except agent_service.DemoAccountLockedError as exc:
        _raise_demo_account_locked(exc)
    except agent_service.AgentProfileNameInvalidError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except agent_service.AgentHandleConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except agent_service.AgentHandleInvalidError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc


@router.put("/{character_id}/persona", response_model=schemas.AgentDetailRead)
def update_persona(
    character_id: str,
    data: schemas.AgentPersonaUpdate,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
) -> schemas.AgentDetailRead:
    try:
        return agent_service.update_persona(db, user, character_id, data)
    except agent_service.AgentNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found") from exc
    except agent_service.DemoAccountLockedError as exc:
        _raise_demo_account_locked(exc)
    except agent_service.PromptInjectionDetectedError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc


@router.put("/{character_id}/promotion-usage", response_model=schemas.AgentDetailRead)
def update_promotion_usage(
    character_id: str,
    data: schemas.AgentPromotionUsageUpdate,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
) -> schemas.AgentDetailRead:
    try:
        return agent_service.update_promotion_usage(db, user, character_id, data)
    except agent_service.AgentNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found") from exc
    except agent_service.DemoAccountLockedError as exc:
        _raise_demo_account_locked(exc)


@router.post("/{character_id}/media", response_model=schemas.AgentDetailRead)
def upload_profile_media(
    character_id: str,
    data: schemas.AgentProfileMediaUpload,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
) -> schemas.AgentDetailRead:
    try:
        return agent_service.upload_profile_media(db, user, character_id, data)
    except agent_service.AgentNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found") from exc
    except agent_service.DemoAccountLockedError as exc:
        _raise_demo_account_locked(exc)
    except agent_service.InvalidProfileMediaError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc


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


@router.post(
    "/{character_id}/generate-media",
    response_model=schemas.AgentProfileMediaGenerationRead,
)
async def generate_profile_media(
    character_id: str,
    data: schemas.AgentProfileMediaGenerateCreate,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
) -> schemas.AgentProfileMediaGenerationRead:
    try:
        return await draft_service.generate_profile_media(db, user, character_id, data)
    except agent_service.AgentNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found") from exc


@router.get(
    "/{character_id}/media-usage",
    response_model=schemas.AgentProfileImageUsageRead,
)
def get_profile_media_usage(
    character_id: str,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
) -> schemas.AgentProfileImageUsageRead:
    try:
        return draft_service.get_agent_profile_image_usage(db, user, character_id)
    except agent_service.AgentNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found") from exc


@router.get(
    "/{character_id}/media-candidates/{candidate_id}/content",
    response_class=FileResponse,
)
def get_agent_profile_media_candidate_content(
    character_id: str,
    candidate_id: str,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
) -> FileResponse:
    try:
        path, content_type = draft_service.get_profile_candidate_content(
            db,
            user,
            character_id,
            candidate_id,
        )
    except (
        agent_service.AgentNotFoundError,
        draft_service.AgentProfileImageCandidateNotFoundError,
    ) as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Candidate not found",
        ) from exc
    return FileResponse(
        path,
        media_type=content_type,
        headers={
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.post(
    "/{character_id}/media-candidates/{candidate_id}/apply",
    response_model=schemas.AgentDetailRead,
)
def apply_profile_media_candidate(
    character_id: str,
    candidate_id: str,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
) -> schemas.AgentDetailRead:
    try:
        return draft_service.apply_profile_media_candidate(
            db, user, character_id, candidate_id
        )
    except agent_service.AgentNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found") from exc
    except agent_service.DemoAccountLockedError as exc:
        _raise_demo_account_locked(exc)
    except draft_service.AgentProfileImageCandidateNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Candidate not found") from exc
    except agent_service.InvalidProfileMediaError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except profile_media.InvalidProfileMediaError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc


@router.delete(
    "/{character_id}/media-candidates/{candidate_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def discard_profile_media_candidate(
    character_id: str,
    candidate_id: str,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
) -> Response:
    try:
        draft_service.discard_profile_media_candidate(db, user, character_id, candidate_id)
    except agent_service.AgentNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found") from exc
    except draft_service.AgentProfileImageCandidateNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Candidate not found") from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.put("/{character_id}/credential", response_model=schemas.CredentialRead)
def update_credential(
    character_id: str,
    data: schemas.CredentialUpsert,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
) -> schemas.CredentialRead:
    try:
        return agent_service.update_credential(db, user, character_id, data)
    except agent_service.AgentNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found") from exc
    except agent_service.DemoAccountLockedError as exc:
        _raise_demo_account_locked(exc)
    except agent_service.ActiveSlotBusyError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except agent_service.CredentialRequiredError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except agent_service.AgentExecutionModeError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except agent_service.CredentialSyncError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc


@router.get("/{character_id}/settings", response_model=schemas.AgentActivitySettingRead)
def get_settings(
    character_id: str,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
) -> schemas.AgentActivitySettingRead:
    try:
        return agent_service.get_settings(db, user, character_id)
    except agent_service.AgentNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found") from exc


@router.put("/{character_id}/settings", response_model=schemas.AgentActivitySettingRead)
def update_settings(
    character_id: str,
    data: schemas.AgentActivitySettingUpdate,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
) -> schemas.AgentActivitySettingRead:
    try:
        return agent_service.update_settings(db, user, character_id, data)
    except agent_service.AgentNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found") from exc
    except agent_service.DemoAccountLockedError as exc:
        _raise_demo_account_locked(exc)
    except agent_service.AgentActiveHoursInvalidError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    except agent_service.AgentExecutionModeError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except agent_service.AgentAutonomyCapacityError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.post("/{character_id}/tendency/analyze", response_model=schemas.AgentDetailRead)
async def analyze_tendency(
    character_id: str,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
) -> schemas.AgentDetailRead:
    try:
        return await agent_service.analyze_tendency(db, user, character_id)
    except agent_service.AgentNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found") from exc
    except agent_service.DemoAccountLockedError as exc:
        _raise_demo_account_locked(exc)
    except agent_service.AgentSuspendedError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except agent_service.CredentialRequiredError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except agent_service.AgentExecutionModeError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except agent_service.LlmCredentialInvalidError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except agent_run_service.OpenClawNotConfiguredError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc
    except agent_run_service.AgentSlotUnavailableError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except agent_service.CredentialSyncError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    except DirectLlmJsonError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=TENDENCY_ANALYSIS_RETRY_DETAIL,
        ) from exc
    except agent_service.TendencyPromptInjectionDetectedError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except agent_service.TendencyAnalysisParseError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=TENDENCY_ANALYSIS_RETRY_DETAIL,
        ) from exc
    except OpenClawGatewayAuthError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="OpenClaw Gateway authentication failed",
        ) from exc
    except OpenClawGatewayError as exc:
        credential_error = agent_service.llm_credential_error_message(exc)
        if credential_error is not None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=credential_error,
            ) from exc
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc


@router.post("/{character_id}/activate", response_model=schemas.AgentDetailRead)
def activate_agent(
    character_id: str,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
) -> schemas.AgentDetailRead:
    try:
        return agent_service.activate_agent(db, user, character_id)
    except maintenance_service.AgentActivityMaintenanceError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc
    except agent_service.AgentNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found") from exc
    except agent_service.AgentSuspendedError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except agent_service.CredentialRequiredError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except agent_service.AgentExecutionModeError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except agent_service.AgentAutonomyCapacityError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except (
        agent_service.TendencyAnalysisRequiredError,
        agent_service.ActivityProfileRequiredError,
    ) as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except (
        agent_service.ActiveSlotBusyError,
        agent_run_service.AgentSlotUnavailableError,
    ) as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except agent_service.CredentialSyncError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    except (
        agent_run_service.CharacterOwnershipError,
        agent_run_service.CredentialOwnershipError,
        agent_run_service.CredentialDisabledError,
    ) as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except community_service.CharacterNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found") from exc


@router.post("/{character_id}/deactivate", response_model=schemas.AgentDetailRead)
def deactivate_agent(
    character_id: str,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
) -> schemas.AgentDetailRead:
    try:
        return agent_service.deactivate_agent(db, user, character_id)
    except agent_service.AgentNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found") from exc
    except agent_service.ActiveSlotBusyError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except agent_service.CredentialSyncError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc


@router.post("/{character_id}/run-now", response_model=schemas.OpenClawAgentRunRead)
async def run_now(
    character_id: str,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
) -> schemas.OpenClawAgentRunRead:
    try:
        return await agent_service.run_agent_now(db, user, character_id)
    except maintenance_service.AgentActivityMaintenanceError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc
    except agent_service.AgentNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found") from exc
    except agent_service.CredentialRequiredError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except agent_service.AgentExecutionModeError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except (
        agent_service.TendencyAnalysisRequiredError,
        agent_service.ActivityProfileRequiredError,
    ) as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except (
        agent_service.RunNowSlotUnavailableError,
        agent_service.RunNowSlotBusyError,
        agent_service.RunNowSchedulerBusyError,
        agent_service.RunNowSoonScheduledError,
    ) as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except agent_service.RunNowCooldownError as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=str(exc),
        ) from exc
    except agent_run_service.OpenClawNotConfiguredError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc
    except (
        agent_run_service.AgentSlotUnavailableError,
        agent_run_service.AgentSessionBusyError,
    ) as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except (
        agent_run_service.CharacterOwnershipError,
        agent_run_service.CredentialOwnershipError,
        agent_run_service.CredentialDisabledError,
    ) as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except OpenClawGatewayAuthError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="OpenClaw Gateway authentication failed",
        ) from exc
    except OpenClawGatewayError as exc:
        credential_error = agent_service.llm_credential_error_message(exc)
        if credential_error is not None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=credential_error,
            ) from exc
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc


@router.post(
    "/{character_id}/first-greeting",
    response_model=schemas.AgentFirstGreetingRead,
)
async def first_greeting(
    character_id: str,
    data: schemas.AgentFirstGreetingCreate,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
) -> schemas.AgentFirstGreetingRead:
    try:
        return await agent_service.run_first_greeting(db, user, character_id, data)
    except maintenance_service.AgentActivityMaintenanceError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc
    except agent_service.AgentNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found") from exc
    except agent_service.AgentSuspendedError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except agent_service.CredentialRequiredError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except agent_service.AgentExecutionModeError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except agent_service.TendencyAnalysisRequiredError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except agent_service.FirstGreetingUnavailableError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except agent_service.FirstGreetingCooldownError as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"{str(exc)} {exc.available_at.isoformat()} 이후 다시 시도할 수 있습니다.",
        ) from exc
    except DirectLlmDeferred as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"첫인사는 {exc.retry_at.isoformat()} 이후 다시 시도할 수 있습니다.",
        ) from exc
    except DirectLlmError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="첫인사를 만들지 못했습니다. 잠시 후 다시 시도해주세요.",
        ) from exc
    except community_service.CommunityServiceError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
