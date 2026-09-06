from app.domains.local_bot.router.keys import get_local_connection

from app.domains.local_bot.router.keys import issue_local_key

from app.domains.local_bot.router.keys import revoke_local_key

from app.domains.local_bot.router.keys import router as local_key_router

from app.domains.characters.router import delete_image_seed

from app.domains.characters.router import delete_image_settings_key

from app.domains.characters.router import get_image_settings

from app.domains.characters.router import update_image_settings

from app.domains.characters.router import upload_image_seed

from app.domains.characters.router import generate_agent_draft_media

from app.domains.characters.router import generate_profile_media

from app.domains.characters.router import get_agent_draft_media

from app.domains.characters.router import upload_agent_draft_media

from app.domains.characters.router import get_agent_draft_media_usage

from app.domains.characters.router import get_agent_draft_media_candidate_content

from app.domains.characters.router import apply_agent_draft_media_candidate

from app.domains.characters.router import discard_agent_draft_media_candidate

from app.domains.characters.router import upload_profile_media

from app.domains.characters.router import get_profile_media_usage

from app.domains.characters.router import get_agent_profile_media_candidate_content

from app.domains.characters.router import apply_profile_media_candidate

from app.domains.characters.router import discard_profile_media_candidate

from app.domains.characters.router import create_agent_draft

from app.domains.characters.router import enhance_agent_draft_persona

from app.domains.characters.router import complete_agent_draft

from app.domains.characters.router import get_agent_draft

from app.domains.characters.router import update_agent_draft

from app.domains.characters.router import list_agents

from app.domains.characters.router import create_agent

from app.domains.characters.router import get_agent

from app.domains.characters.router import update_profile

from app.domains.characters.router import update_persona

from app.domains.characters.router import update_promotion_usage

from app.domains.characters.router import router as character_router

from fastapi import APIRouter

from fastapi import Body

from fastapi import Depends

from fastapi import HTTPException

from fastapi import Response

from fastapi import status

from fastapi.responses import FileResponse

from sqlalchemy.orm import Session

from app import schemas

from app.domains.identity.models import User as _model_User

from app.runtime.persistence.model_registration import register_models

from app.domains.identity.dependencies import get_current_user

from app.database import get_db

from app.runtime.characters import creator as draft_service

from app.runtime.characters import management as agent_service

from app.domains.routines import exceptions as agent_run_service

from app.services import community as community_service

from app.domains.operations.service import maintenance as maintenance_service

from app.integrations.direct_llm import DirectLlmDeferred

from app.integrations.direct_llm import DirectLlmError

from app.integrations.direct_llm import DirectLlmJsonError

from app.services.runtime_boundary import OpenClawGatewayAuthError

from app.services.runtime_boundary import OpenClawGatewayError

register_models()

router = APIRouter(prefix="/agents", tags=["agents"])

_character_routes = {route.name: route for route in character_router.routes}

_local_key_routes = {route.name: route for route in local_key_router.routes}

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
    user: _model_User = Depends(get_current_user),
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

router.routes.append(_local_key_routes["get_local_connection"])

router.routes.append(_local_key_routes["issue_local_key"])

router.routes.append(_local_key_routes["revoke_local_key"])

router.routes.append(_character_routes["update_profile"])

router.routes.append(_character_routes["update_persona"])

router.routes.append(_character_routes["update_promotion_usage"])

router.routes.append(_character_routes["upload_profile_media"])

router.routes.append(_character_routes["get_image_settings"])

router.routes.append(_character_routes["update_image_settings"])

router.routes.append(_character_routes["delete_image_settings_key"])

router.routes.append(_character_routes["upload_image_seed"])

router.routes.append(_character_routes["delete_image_seed"])

router.routes.append(_character_routes["generate_profile_media"])

router.routes.append(_character_routes["get_profile_media_usage"])

router.routes.append(_character_routes["get_agent_profile_media_candidate_content"])

router.routes.append(_character_routes["apply_profile_media_candidate"])

router.routes.append(_character_routes["discard_profile_media_candidate"])

router.routes.append(_character_routes["get_feed_cue"])

router.routes.append(_character_routes["give_feed_cue"])

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
