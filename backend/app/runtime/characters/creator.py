from __future__ import annotations

from app.domains.characters.service import image_generation as image_generation_service
from app.domains.characters.service.image_generation import (
    POLLINATIONS_MAX_SEED,
    STYLE_PROMPTS,
    _build_pollinations_prompt,
    _draft_media_seed,
    _pollinations_image_size,
)

from app.domains.characters.service import media as media_service
from app.domains.characters.service.media import _cleanup_expired_profile_image_candidates, _get_owned_profile_image_candidate

from app.domains.characters.contracts import CreatorWorkflows
from app.domains.characters.service import drafts as draft_lifecycle

from app.domains.characters.service.creator import (
    DRAFT_TTL,
    DRAFT_COOLDOWN,
    PROFILE_IMAGE_CANDIDATE_TTL,
    _draft_read,
    _build_persona_enhance_prompt,
    _parse_json_object,
    _safe_payload_text,
    _clean_text,
    _ensure_not_in_cooldown,
    _ensure_draft_persona_prompt_safety,
    _ensure_draft_prompt_safety,
)

from app.domains.characters.service.image_quota import (
    PROFILE_IMAGE_DAILY_LIMIT,
    PROFILE_IMAGE_USED_STATUSES,
    _profile_image_usage_read,
    _profile_image_usage_status,
    _reserve_profile_image_quota,
    _finalize_profile_image_quota,
    _profile_image_bucket,
    _profile_image_quota_date,
    _profile_image_reset_at,
    _lock_profile_image_quota,
)

from app.domains.characters.exceptions import (
    AgentCreationDraftError,
    AgentCreationDraftNotFoundError,
    AgentCreationDraftExpiredError,
    AgentCreationDraftCooldownError,
    AgentCreationDraftValidationError,
    AgentCreationDraftHandleConflictError,
    AgentCreationDraftMediaError,
    AgentProfileImageQuotaExceededError,
    AgentProfileImageCandidateNotFoundError,
    AgentProfileImageCandidateExpiredError,
    AgentPrivateMediaNotFoundError,
    AgentCreationDraftParseError,
)

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
import json
import logging
import re
from threading import Lock
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urlparse
from urllib.request import Request
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import models, schemas
from app.domains.characters import models as character_models
from app.domains.characters.service import profile as character_profile
from app.core import security
from app.config import settings
from app.core.redaction import redact_exact_secret_text
from app.credentials import CredentialResolutionError, CredentialResolver
from app.cruds import agent_runs as agent_run_crud
from app.cruds import agents as agent_crud
from app.policies import name_policy
from app.runtime.characters import management as agent_service
from app.services import agent_activity_policy
from app.services import agent_runs as agent_run_service
from app.domains.identity.service import demo_access as demo_lock
from app.services.direct_llm import DirectLlmCallContext, RunLlmTracker, generate_text
from app.services import operation_settings
from app.integrations import image_provider
from app.integrations import pollinations_image
from app.core import prompt_safety
from app.domains.characters.service import media_storage as profile_media
from app.integrations.media import files as media_files
from app.integrations.media import images as media_images
from app.integrations import bounded_http
from app.integrations import provider_http
from app.integrations import replicate_image
from app.services import service_image_key
from app.services.runtime_boundary import (
    OpenClawGatewayClient,
    OpenClawGatewayError,
    openclaw_auth_profiles,
)


logger = logging.getLogger(__name__)
POLLINATIONS_MODELS_URL = "https://gen.pollinations.ai/image/models"
POLLINATIONS_IMAGE_URL = "https://gen.pollinations.ai/image"
POLLINATIONS_LEGACY_IMAGE_URL = "https://image.pollinations.ai/prompt"
PROVIDER_SENSITIVE_HEADERS = frozenset(
    {
        "Authorization",
        "Ocp-Apim-Subscription-Key",
        "Ocp-Apim-Subscription-Region",
    }
)
# OpenClaw validates the global tool allowlist before honoring tool_choice="none".
DRAFT_LLM_TOOLS_ALLOW = ["angmoo_list_feed"]
HANGUL_RE = re.compile(r"[\uac00-\ud7a3]")
TRANSLATION_CACHE_MAX = 256
_POLLINATIONS_MODEL_CHECKED_AT: dict[str, datetime] = {}
_TRANSLATION_CACHE: dict[str, str] = {}
_TRANSLATION_USAGE_LOCK = Lock()


@dataclass
class _DraftCredential:
    id: str
    provider: str
    model: str
    auth_profile_id: str
    label: str


async def create_draft(
    db: Session, user: models.User, data: schemas.AgentCreationDraftCreate
) -> schemas.AgentCreationDraftRead:
    return await draft_lifecycle.create_draft(db, user, data, workflows=build_creator_workflows())


def get_draft(
    db: Session, user: models.User, draft_id: str
) -> schemas.AgentCreationDraftRead:
    return draft_lifecycle.get_draft(db, user, draft_id, workflows=build_creator_workflows())


def get_draft_media_content(
    db: Session,
    user: models.User,
    draft_id: str,
    media_type: str,
):
    return media_service.get_draft_media_content(db, user, draft_id, media_type, workflows=build_creator_workflows())


def get_draft_candidate_content(
    db: Session,
    user: models.User,
    draft_id: str,
    candidate_id: str,
):
    return media_service.get_draft_candidate_content(db, user, draft_id, candidate_id, workflows=build_creator_workflows())


def get_profile_candidate_content(
    db: Session,
    user: models.User,
    character_id: str,
    candidate_id: str,
):
    return media_service.get_profile_candidate_content(db, user, character_id, candidate_id)


def update_draft(
    db: Session,
    user: models.User,
    draft_id: str,
    data: schemas.AgentCreationDraftUpdate,
) -> schemas.AgentCreationDraftRead:
    return draft_lifecycle.update_draft(db, user, draft_id, data, workflows=build_creator_workflows())


async def enhance_persona(
    db: Session, user: models.User, draft_id: str
) -> schemas.AgentCreationDraftRead:
    return await draft_lifecycle.enhance_persona(db, user, draft_id, workflows=build_creator_workflows())


def upload_draft_media(
    db: Session,
    user: models.User,
    draft_id: str,
    data: schemas.AgentCreationDraftMediaUpload,
) -> schemas.AgentCreationDraftRead:
    return media_service.upload_draft_media(db, user, draft_id, data, workflows=build_creator_workflows())


async def generate_media(
    db: Session,
    user: models.User,
    draft_id: str,
    data: schemas.AgentCreationDraftGenerateMediaCreate,
) -> schemas.AgentCreationDraftMediaGenerationRead:
    return await image_generation_service.generate_media(db, user, draft_id, data, workflows=build_image_generation_workflows(), creator_workflows=build_creator_workflows())


async def generate_profile_media(
    db: Session,
    user: models.User,
    character_id: str,
    data: schemas.AgentProfileMediaGenerateCreate,
) -> schemas.AgentProfileMediaGenerationRead:
    return await image_generation_service.generate_profile_media(db, user, character_id, data, workflows=build_image_generation_workflows())


def get_draft_profile_image_usage(
    db: Session, user: models.User, draft_id: str
) -> schemas.AgentProfileImageUsageRead:
    return media_service.get_draft_profile_image_usage(db, user, draft_id, workflows=build_creator_workflows())


def get_agent_profile_image_usage(
    db: Session, user: models.User, character_id: str
) -> schemas.AgentProfileImageUsageRead:
    return media_service.get_agent_profile_image_usage(db, user, character_id)


def apply_draft_media_candidate(
    db: Session,
    user: models.User,
    draft_id: str,
    candidate_id: str,
) -> schemas.AgentCreationDraftRead:
    return media_service.apply_draft_media_candidate(db, user, draft_id, candidate_id, workflows=build_creator_workflows())


def apply_profile_media_candidate(
    db: Session,
    user: models.User,
    character_id: str,
    candidate_id: str,
) -> schemas.AgentDetailRead:
    return media_service.apply_profile_media_candidate(db, user, character_id, candidate_id, workflows=agent_service.build_character_media_workflows())


def discard_draft_media_candidate(
    db: Session,
    user: models.User,
    draft_id: str,
    candidate_id: str,
) -> None:
    return media_service.discard_draft_media_candidate(db, user, draft_id, candidate_id, workflows=build_creator_workflows())


def discard_profile_media_candidate(
    db: Session,
    user: models.User,
    character_id: str,
    candidate_id: str,
) -> None:
    return media_service.discard_profile_media_candidate(db, user, character_id, candidate_id)


def complete_draft(
    db: Session,
    user: models.User,
    draft_id: str,
    data: schemas.AgentCreationDraftComplete | None = None,
) -> schemas.AgentDetailRead:
    return draft_lifecycle.complete_draft(db, user, draft_id, data, workflows=build_creator_workflows())


def _get_owned_draft(
    db: Session, user: models.User, draft_id: str
) -> character_models.AgentCreationDraft:
    return draft_lifecycle._get_owned_draft(db, user, draft_id, workflows=build_creator_workflows())


def _cleanup_expired_drafts(db: Session) -> None:
    return draft_lifecycle._cleanup_expired_drafts(db, workflows=build_creator_workflows())


def _delete_profile_image_candidates_for_draft(
    db: Session, draft: character_models.AgentCreationDraft
) -> None:
    return draft_lifecycle._delete_profile_image_candidates_for_draft(db, draft, workflows=build_creator_workflows())


async def _run_draft_llm(
    *,
    db: Session,
    user: models.User,
    draft_id: str,
    provider: str,
    model: str,
    api_key: str,
    message: str,
    extra_system_prompt: str,
) -> str:
    if settings.server_llm_engine == "direct":
        run_id = str(uuid4())
        tracker = RunLlmTracker()
        response = await generate_text(
            api_key=api_key,
            context=DirectLlmCallContext(
                credential_id=f"draft:{draft_id}",
                character_id=None,
                agent_run_id=run_id,
                node="AgentCreationDraft",
                lane="server_llm",
                provider=provider,
                model=model,
            ),
            tracker=tracker,
            system_prompt=extra_system_prompt,
            user_prompt=message,
            max_output_tokens=2400,
            timeout_seconds=settings.openclaw_timeout_seconds,
        )
        if not response.text.strip():
            raise AgentCreationDraftParseError("LLM 응답을 읽지 못했습니다.")
        return response.text.strip()

    token = settings.openclaw_gateway_token
    if token is None:
        raise agent_service.CredentialSyncError("OPENCLAW_GATEWAY_TOKEN is missing")
    run_id = str(uuid4())
    timeout_seconds = settings.openclaw_timeout_seconds
    slot = agent_run_crud.claim_agent_slot(
        db,
        run_id=run_id,
        agent_ids=settings.openclaw_agent_ids,
        lease_seconds=timeout_seconds + 90,
    )
    if slot is None:
        raise agent_run_service.AgentSlotUnavailableError(
            f"No OpenClaw slot is available for {', '.join(settings.openclaw_agent_ids)}"
        )

    credential = _DraftCredential(
        id=f"cred-{draft_id}",
        provider=provider,
        model=model,
        auth_profile_id=f"{provider}:{draft_id}",
        label=f"Angmoo draft {draft_id}",
    )
    client = OpenClawGatewayClient(
        url=settings.openclaw_gateway_url,
        token=token,
        timeout_seconds=timeout_seconds,
    )
    bound_profile = False
    last_error: str | None = None
    try:
        openclaw_auth_profiles.bind_credential_to_slot(
            agent_id=slot.agent_id,
            user_id=user.id,
            character_id=draft_id,
            credential=credential,  # type: ignore[arg-type]
            api_key=api_key,
        )
        bound_profile = True
        await client.reload_secrets()
        gateway_result = await client.run_agent(
            message=message,
            agent_id=slot.agent_id,
            session_key=f"agent:{slot.agent_id}:angmoo:draft:{user.id}:{draft_id}:{run_id}",
            provider=provider,
            model=model,
            auth_profile_id=credential.auth_profile_id,
            tool_choice="none",
            tools_allow=DRAFT_LLM_TOOLS_ALLOW,
            prompt_mode="minimal",
            bootstrap_context_mode="lightweight",
            bootstrap_context_run_kind="default",
            idempotency_key=run_id,
            extra_system_prompt=extra_system_prompt,
        )
        return _extract_gateway_result_text(gateway_result)
    except OpenClawGatewayError as exc:
        last_error = redact_exact_secret_text(str(exc), api_key)
        exc.args = (last_error,)
        raise
    except openclaw_auth_profiles.OpenClawAuthProfileSyncError as exc:
        last_error = redact_exact_secret_text(str(exc), api_key)[:1000]
        raise agent_service.CredentialSyncError(last_error) from exc
    finally:
        if bound_profile:
            try:
                openclaw_auth_profiles.release_credential_from_slot(
                    agent_id=slot.agent_id,
                    user_id=user.id,
                    character_id=draft_id,
                    credential=credential,  # type: ignore[arg-type]
                )
                await client.reload_secrets()
            except Exception as exc:
                last_error = redact_exact_secret_text(str(exc), api_key)[:1000]
        agent_run_crud.release_agent_slot(
            db, agent_id=slot.agent_id, run_id=run_id, last_error=last_error
        )


def _extract_gateway_result_text(gateway_result: dict[str, Any]) -> str:
    result = gateway_result.get("result")
    if isinstance(result, dict):
        meta = result.get("meta")
        if isinstance(meta, dict):
            for key in ("finalAssistantVisibleText", "finalAssistantRawText"):
                text = meta.get(key)
                if isinstance(text, str) and text.strip():
                    return text.strip()
        payloads = result.get("payloads")
        if isinstance(payloads, list):
            parts: list[str] = []
            for payload in payloads:
                if not isinstance(payload, dict):
                    continue
                if payload.get("isError") or payload.get("isReasoning"):
                    continue
                text = payload.get("text")
                if isinstance(text, str) and text.strip():
                    parts.append(text.strip())
            if parts:
                return "\n\n".join(parts)
    raise AgentCreationDraftParseError("LLM 응답을 읽지 못했습니다.")


def _decrypt_draft_api_key(draft: character_models.AgentCreationDraft) -> str:
    try:
        return CredentialResolver.resolve_draft_credential(draft).reveal()
    except CredentialResolutionError as exc:
        raise agent_service.CredentialRequiredError(
            "Agent draft credential key cannot be decrypted"
        ) from exc


async def _generate_profile_image_candidate(
    db: Session,
    *,
    user: models.User,
    scope: str,
    media_type: str,
    prompt: str,
    seed: int,
    model: str,
    route_mode: str,
    draft_id: str | None,
    character_id: str | None,
) -> tuple[character_models.ProfileImageCandidate, schemas.AgentProfileImageUsageStatusRead]:
    return await image_generation_service._generate_profile_image_candidate(db, user=user, scope=scope, media_type=media_type, prompt=prompt, seed=seed, model=model, route_mode=route_mode, draft_id=draft_id, character_id=character_id, workflows=build_image_generation_workflows())






def _open_pollinations_request(request: Request, timeout_seconds: float):
    try:
        return provider_http.open_validated_request(
            request,
            timeout_seconds=timeout_seconds,
            initial_validator=lambda url: provider_http.validate_public_https_url(
                url,
                allowed_hosts={"gen.pollinations.ai", "image.pollinations.ai"},
                allowed_path_prefixes={"/image", "/prompt"},
            ),
            redirect_validator=provider_http.validate_public_https_url,
            sensitive_headers=PROVIDER_SENSITIVE_HEADERS,
            allow_cross_origin_redirects=True,
        )
    except provider_http.ProviderUrlError as exc:
        raise URLError("Pollinations URL was not allowed") from exc


def _open_translation_request(request: Request, timeout_seconds: float):
    endpoint = urlparse(settings.azure_translator_endpoint)
    if not endpoint.hostname:
        raise URLError("Azure Translator endpoint was not allowed")
    translate_path = f"{endpoint.path.rstrip('/')}/translate"
    try:
        return provider_http.open_validated_request(
            request,
            timeout_seconds=timeout_seconds,
            initial_validator=lambda url: provider_http.validate_public_https_url(
                url,
                allowed_hosts={endpoint.hostname},
                allowed_path_prefixes={translate_path},
            ),
            redirect_validator=provider_http.validate_public_https_url,
            sensitive_headers=PROVIDER_SENSITIVE_HEADERS,
            allow_cross_origin_redirects=False,
        )
    except provider_http.ProviderUrlError as exc:
        raise URLError("Azure Translator URL was not allowed") from exc


def _ensure_pollinations_model_available(model_name: str) -> None:
    now = datetime.now(UTC)
    checked_at = _POLLINATIONS_MODEL_CHECKED_AT.get(model_name)
    if checked_at is not None and now - checked_at < timedelta(minutes=15):
        return
    try:
        request = Request(POLLINATIONS_MODELS_URL, headers={"User-Agent": "Angmoo/1.0"})
        with _open_pollinations_request(request, 20) as response:
            payload = json.loads(
                bounded_http.read_bounded_response(
                    response,
                    max_bytes=bounded_http.MAX_PROVIDER_JSON_BYTES,
                ).decode("utf-8")
            )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise AgentCreationDraftMediaError(
            "이미지 모델 상태를 확인하지 못했습니다."
        ) from exc
    models_payload = payload if isinstance(payload, list) else payload.get("models", [])
    if not isinstance(models_payload, list):
        raise AgentCreationDraftMediaError("이미지 모델 목록 형식이 올바르지 않습니다.")
    for model in models_payload:
        if not isinstance(model, dict) or model.get("name") != model_name:
            continue
        if model.get("paid_only") is True:
            raise AgentCreationDraftMediaError("현재 선택한 이미지 모델을 사용할 수 없습니다.")
        input_modalities = model.get("input_modalities") or []
        output_modalities = model.get("output_modalities") or []
        if "text" not in input_modalities or "image" not in output_modalities:
            raise AgentCreationDraftMediaError("현재 이미지 URL 생성 방식을 사용할 수 없습니다.")
        _POLLINATIONS_MODEL_CHECKED_AT[model_name] = now
        return
    raise AgentCreationDraftMediaError("현재 선택한 이미지 모델을 찾지 못했습니다.")




def _translate_image_prompt_to_english(text: str) -> str:
    prompt = text.strip()
    if not prompt or not HANGUL_RE.search(prompt):
        return prompt
    cached = _TRANSLATION_CACHE.get(prompt)
    if cached:
        return cached
    translated = _translate_ko_to_en_with_azure(prompt)
    if not translated:
        return prompt
    if len(_TRANSLATION_CACHE) >= TRANSLATION_CACHE_MAX:
        _TRANSLATION_CACHE.pop(next(iter(_TRANSLATION_CACHE)))
    _TRANSLATION_CACHE[prompt] = translated
    return translated


def _translate_ko_to_en_with_azure(text: str) -> str | None:
    if settings.translation_provider != "azure":
        return None
    api_key = settings.azure_translator_key
    if not api_key:
        return None
    char_count = len(text)
    if not _reserve_translation_chars(char_count):
        return None

    try:
        query = urlencode({"api-version": "3.0", "from": "ko", "to": "en"})
        url = f"{settings.azure_translator_endpoint}/translate?{query}"
        headers = {
            "Content-Type": "application/json; charset=utf-8",
            "Ocp-Apim-Subscription-Key": api_key,
            "User-Agent": "Angmoo/1.0",
        }
        region = settings.azure_translator_region
        if region:
            headers["Ocp-Apim-Subscription-Region"] = region
        body = json.dumps([{"Text": text}], ensure_ascii=False).encode("utf-8")
        request = Request(url, data=body, headers=headers, method="POST")
        with _open_translation_request(
            request,
            settings.translation_timeout_seconds,
        ) as response:
            payload = json.loads(
                bounded_http.read_bounded_response(
                    response,
                    max_bytes=bounded_http.MAX_PROVIDER_JSON_BYTES,
                ).decode("utf-8")
            )
        translated = payload[0]["translations"][0]["text"]
        return translated.strip() if isinstance(translated, str) else None
    except Exception:
        _release_translation_chars(char_count)
        return None


def _reserve_translation_chars(char_count: int) -> bool:
    limit = settings.translation_monthly_char_limit
    if limit <= 0:
        return True
    usage_path = settings.media_root_path / "translation-usage.json"
    month = datetime.now(UTC).strftime("%Y-%m")
    with _TRANSLATION_USAGE_LOCK:
        usage = _read_translation_usage(usage_path, month)
        if usage["chars"] + char_count > limit:
            return False
        usage["chars"] += char_count
        _write_translation_usage(usage_path, usage)
    return True


def _release_translation_chars(char_count: int) -> None:
    limit = settings.translation_monthly_char_limit
    if limit <= 0:
        return
    usage_path = settings.media_root_path / "translation-usage.json"
    month = datetime.now(UTC).strftime("%Y-%m")
    with _TRANSLATION_USAGE_LOCK:
        usage = _read_translation_usage(usage_path, month)
        usage["chars"] = max(0, usage["chars"] - char_count)
        _write_translation_usage(usage_path, usage)


def _read_translation_usage(path: Any, month: str) -> dict[str, Any]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        raw = {}
    if raw.get("month") != month or not isinstance(raw.get("chars"), int):
        return {"month": month, "chars": 0}
    return {"month": month, "chars": max(0, raw["chars"])}


def _write_translation_usage(path: Any, usage: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(usage, ensure_ascii=False), encoding="utf-8")




def _pollinations_image_query(
    *,
    model: str,
    media_type: str,
    seed: int,
    size: tuple[int, int] | None,
) -> dict[str, str | int]:
    width, height = _pollinations_image_size(media_type, size)
    query: dict[str, str | int] = {
        "model": model,
        "width": width,
        "height": height,
        "nologo": "true",
        "enhance": "true",
        "seed": seed,
    }
    return query


def _build_pollinations_image_url(
    *,
    base_url: str,
    model: str,
    prompt: str,
    media_type: str,
    seed: int,
    size: tuple[int, int] | None = None,
) -> str:
    query = _pollinations_image_query(
        model=model,
        media_type=media_type,
        seed=seed,
        size=size,
    )
    return f"{base_url}/{quote(prompt)}?{urlencode(query)}"


def _download_pollinations_image(
    *,
    model: str,
    prompt: str,
    media_type: str,
    seed: int,
    size: tuple[int, int] | None = None,
) -> tuple[str, bytes]:
    api_key = settings.pollinations_api_key
    primary_url = _build_pollinations_image_url(
        base_url=POLLINATIONS_IMAGE_URL,
        model=model,
        prompt=prompt,
        media_type=media_type,
        seed=seed,
        size=size,
    )
    urls = [primary_url]
    if not api_key:
        legacy_url = _build_pollinations_image_url(
            base_url=POLLINATIONS_LEGACY_IMAGE_URL,
            model=model,
            prompt=prompt,
            media_type=media_type,
            seed=seed,
            size=size,
        )
        urls = [legacy_url, primary_url]

    last_status: int | None = None
    for index, url in enumerate(urls):
        try:
            headers = {"User-Agent": "Angmoo/1.0"}
            headers["Accept-Encoding"] = "identity"
            if api_key:
                headers["Authorization"] = f"Bearer {api_key}"
            request = Request(url, headers=headers)
            with _open_pollinations_request(
                request,
                settings.pollinations_timeout_seconds,
            ) as response:
                content_type = (
                    response.headers.get("Content-Type") or ""
                ).split(";")[0].lower()
                content = bounded_http.read_bounded_response(
                    response,
                    max_bytes=bounded_http.MAX_PROVIDER_IMAGE_BYTES,
                )
            media_images.validate_profile_media_content(content_type, content)
            return content_type, content
        except HTTPError as exc:
            last_status = exc.code
            if index == 0 and not api_key and exc.code in {400, 401, 402, 403}:
                continue
            raise AgentCreationDraftMediaError(
                f"이미지 생성 서비스가 응답하지 않았습니다. ({exc.code})"
            ) from exc
        except bounded_http.ResponseTooLargeError as exc:
            raise AgentCreationDraftMediaError(
                "Image provider response is too large"
            ) from exc
        except (TimeoutError, URLError, OSError) as exc:
            raise AgentCreationDraftMediaError("이미지 생성 요청이 실패했습니다.") from exc
        except profile_media.InvalidProfileMediaError as exc:
            raise AgentCreationDraftMediaError("이미지 생성 결과를 저장할 수 없습니다.") from exc
    raise AgentCreationDraftMediaError(
        f"이미지 생성 서비스가 응답하지 않았습니다. ({last_status})"
    )


def _download_pollinations_image_with_retry(
    *, model: str, prompt: str, media_type: str, seed: int
) -> tuple[str, bytes]:
    last_error: AgentCreationDraftMediaError | None = None
    attempts = (((768, 768), prompt),) if media_type == "avatar" else ((None, prompt),)
    for offset, (size, attempt_prompt) in enumerate(attempts):
        try:
            return _download_pollinations_image(
                model=model,
                prompt=attempt_prompt,
                media_type=media_type,
                seed=seed + offset,
                size=size,
            )
        except AgentCreationDraftMediaError as exc:
            last_error = exc
    if last_error is not None:
        raise last_error
    raise AgentCreationDraftMediaError("이미지 생성 요청이 실패했습니다.")


def _generate_draft_media_file(
    draft_id: str, media_type: str, prompt: str, seed: int, model: str
) -> str:
    content_type, content = _download_pollinations_image_with_retry(
        model=model,
        prompt=prompt,
        media_type=media_type,
        seed=seed,
    )
    return profile_media.save_draft_profile_media_bytes(
        draft_id=draft_id,
        media_type=media_type,
        content_type=content_type,
        content=content,
    )




def build_creator_workflows() -> CreatorWorkflows:
    """Bind external work; lifecycle decisions and draft ORM stay in Characters."""
    return CreatorWorkflows(
        run_llm=_run_draft_llm,
        decrypt_api_key=_decrypt_draft_api_key,
        delete_candidate_media=profile_media.delete_profile_image_candidate,
        delete_draft_media=profile_media.delete_draft_media,
        promote_media=profile_media.promote_draft_profile_media,
        create_character=agent_service.create_agent,
        read_character=agent_service.get_agent,
    )


def _resolve_profile_image_api_key(model: str) -> str | None:
    return (
        service_image_key.get_replicate_image_api_key()
        if image_provider.is_replicate_model(model)
        else service_image_key.get_profile_image_api_key()
    )


def build_image_generation_workflows():
    from app.domains.characters.contracts import CharacterImageGenerationWorkflows

    return CharacterImageGenerationWorkflows(
        get_model=operation_settings.get_pollinations_profile_image_model,
        get_route_mode=operation_settings.get_pollinations_profile_image_route_mode,
        image_key_available=service_image_key.is_profile_image_available_for_model,
        resolve_api_key=_resolve_profile_image_api_key,
        translate_prompt=_translate_image_prompt_to_english,
    )
