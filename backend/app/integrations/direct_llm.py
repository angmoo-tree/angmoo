from __future__ import annotations

import asyncio
from collections import defaultdict, deque
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
import hashlib
import json
import logging
import re
import time
from typing import Any

from app.core.config import settings
from app.core.redaction import (
    redact_exact_secret_text,
    redact_exact_secrets,
    redact_secret_text,
)
from app.providers.contracts import ProviderRequest
from app.providers.gemini import build_generate_content_config, genai, types
from app.providers.registry import get_provider_adapter, normalize_provider_name


logger = logging.getLogger(__name__)


_PROVIDER_ERROR_MAX_JSON_BYTES = 2048
_SENSITIVE_HEADER_NAMES = {"authorization", "x-goog-api-key", "api-key", "key"}
_BEARER_TOKEN_RE = re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]{12,}", re.IGNORECASE)


class DirectLlmError(Exception):
    pass


class DirectLlmJsonError(DirectLlmError):
    def __init__(
        self,
        message: str,
        *,
        failure_class: str,
        parse_error_type: str,
        attempt_count: int | None = None,
        validation_summary: list[dict[str, str]] | None = None,
        json_error_diagnostics: list[dict[str, Any]] | None = None,
        last_payload: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.failure_class = failure_class
        self.parse_error_type = parse_error_type
        self.attempt_count = attempt_count
        self.validation_summary = validation_summary
        self.json_error_diagnostics = json_error_diagnostics
        self.last_payload = last_payload


class DirectLlmDeferred(DirectLlmError):
    def __init__(self, message: str, *, retry_at: datetime, wait_seconds: float) -> None:
        super().__init__(message)
        self.retry_at = retry_at
        self.wait_seconds = wait_seconds


class DirectLlmMaxCallsExceeded(DirectLlmError):
    pass


@dataclass(frozen=True)
class DirectLlmCallContext:
    credential_id: str
    character_id: str | None
    agent_run_id: str | None
    node: str
    lane: str
    provider: str
    model: str
    key_fingerprint: str | None = None


@dataclass(frozen=True)
class DirectLlmImagePart:
    mime_type: str
    data: bytes | None = None
    url: str | None = None


@dataclass
class DirectLlmResponse:
    text: str
    parsed: Any | None
    usage: dict[str, int | None]
    finish_reason: str | None = None


@dataclass
class RunLlmTracker:
    max_calls: int = field(default_factory=lambda: settings.direct_llm_max_calls_per_run)
    call_order_in_run: int = 0
    provider_call_order_in_run: int = 0
    calls: list[dict[str, Any]] = field(default_factory=list)
    rate_limit_waits: list[dict[str, Any]] = field(default_factory=list)

    def next_call_order(self) -> int:
        if self.call_order_in_run >= self.max_calls:
            raise DirectLlmMaxCallsExceeded(
                f"direct LLM max calls exceeded: {self.max_calls}"
            )
        self.call_order_in_run += 1
        return self.call_order_in_run

    def next_provider_call_order(self) -> int:
        self.provider_call_order_in_run += 1
        return self.provider_call_order_in_run

    def record_wait(
        self,
        *,
        context: DirectLlmCallContext,
        wait_seconds: float,
        reason: str,
        call_type: str = "generate_content",
    ) -> None:
        self.rate_limit_waits.append(
            {
                "credential_id": context.credential_id,
                "key_fingerprint": context.key_fingerprint,
                "call_type": call_type,
                "provider": context.provider,
                "model": context.model,
                "node": context.node,
                "lane": context.lane,
                "wait_seconds": round(wait_seconds, 3),
                "reason": reason,
                "recorded_at": datetime.now(UTC).isoformat(),
            }
        )

    def record_call(
        self,
        *,
        context: DirectLlmCallContext,
        call_order: int,
        provider_call_order: int,
        status: str,
        duration_ms: int,
        usage: dict[str, int | None] | None = None,
        failure_class: str | None = None,
        parse_error_type: str | None = None,
        provider_error_hint: str | None = None,
        provider_error: dict[str, Any] | None = None,
        thinking_level: str | None = None,
        max_output_tokens: int | None = None,
        finish_reason: str | None = None,
    ) -> None:
        payload: dict[str, Any] = {
            "call_type": "generate_content",
            "provider_call_order_in_run": provider_call_order,
            "call_order_in_run": call_order,
            "credential_id": context.credential_id,
            "key_fingerprint": context.key_fingerprint,
            "character_id": context.character_id,
            "agent_run_id": context.agent_run_id,
            "node": context.node,
            "lane": context.lane,
            "provider": context.provider,
            "model": context.model,
            "status": status,
            "duration_ms": duration_ms,
        }
        if usage:
            payload["usage"] = usage
        if failure_class:
            payload["failure_class"] = failure_class
        if parse_error_type:
            payload["parse_error_type"] = parse_error_type
        if provider_error_hint:
            payload["provider_error_hint"] = provider_error_hint
        if provider_error:
            payload["provider_error"] = provider_error
        if thinking_level:
            payload["thinking_level"] = thinking_level
        if max_output_tokens is not None:
            payload["max_output_tokens"] = max_output_tokens
        if finish_reason:
            payload["finish_reason"] = str(finish_reason)[:64]
        self.calls.append(payload)

    def annotate_last_json_postprocess_error(
        self, *, context: DirectLlmCallContext, diagnostic: dict[str, Any]
    ) -> None:
        for call in reversed(self.calls):
            if call.get("call_type") != "generate_content":
                continue
            if call.get("node") != context.node or call.get("lane") != context.lane:
                continue
            if call.get("agent_run_id") != context.agent_run_id:
                continue
            call["json_postprocess_error"] = diagnostic
            return

    def record_embedding_call(
        self,
        *,
        context: DirectLlmCallContext,
        provider_call_order: int,
        status: str,
        duration_ms: int,
        failure_class: str | None = None,
        provider_error_hint: str | None = None,
    ) -> None:
        payload: dict[str, Any] = {
            "call_type": "embed_content",
            "provider_call_order_in_run": provider_call_order,
            "credential_id": context.credential_id,
            "key_fingerprint": context.key_fingerprint,
            "character_id": context.character_id,
            "agent_run_id": context.agent_run_id,
            "node": context.node,
            "lane": context.lane,
            "provider": context.provider,
            "model": context.model,
            "status": status,
            "duration_ms": duration_ms,
        }
        if failure_class:
            payload["failure_class"] = failure_class
        if provider_error_hint:
            payload["provider_error_hint"] = provider_error_hint
        self.calls.append(payload)

    def summary(self) -> dict[str, Any]:
        total_prompt_tokens = 0
        total_output_tokens = 0
        total_thought_tokens = 0
        total_tokens = 0
        generate_call_count = 0
        embedding_call_count = 0
        for call in self.calls:
            call_type = call.get("call_type") or "generate_content"
            if call_type == "embed_content":
                embedding_call_count += 1
            else:
                generate_call_count += 1
            usage = call.get("usage")
            if not isinstance(usage, dict):
                continue
            total_prompt_tokens += int(usage.get("prompt_token_count") or 0)
            total_output_tokens += int(usage.get("candidates_token_count") or 0)
            total_thought_tokens += int(usage.get("thoughts_token_count") or 0)
            total_tokens += int(usage.get("total_token_count") or 0)
        return {
            "summary_version": 3,
            "call_count": generate_call_count,
            "provider_call_count": len(self.calls),
            "generate_call_count": generate_call_count,
            "embedding_call_count": embedding_call_count,
            "max_calls": self.max_calls,
            "total_prompt_tokens": total_prompt_tokens,
            "total_output_tokens": total_output_tokens,
            "total_thought_tokens": total_thought_tokens,
            "total_tokens": total_tokens,
            "calls": self.calls,
            "rate_limit_waits": self.rate_limit_waits,
        }


class _DirectLlmRateLimiter:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._buckets: dict[tuple[str, str, str], deque[float]] = defaultdict(deque)

    async def wait_if_needed(
        self,
        *,
        context: DirectLlmCallContext,
        tracker: RunLlmTracker,
        call_type: str = "generate_content",
        on_rate_limit_wait: Callable[[float], Awaitable[None]] | None = None,
    ) -> None:
        rpm_limit = settings.direct_llm_default_rpm_limit
        credential_key = context.key_fingerprint or context.credential_id
        bucket_key = (credential_key, context.provider, context.model)
        now = time.monotonic()
        async with self._lock:
            bucket = self._buckets[bucket_key]
            while bucket and now - bucket[0] >= 60:
                bucket.popleft()
            if len(bucket) < rpm_limit:
                bucket.append(now)
                return
            wait_seconds = (
                60
                - (now - bucket[0])
                + settings.direct_llm_rate_limit_buffer_seconds
            )
        wait_seconds = max(0.0, wait_seconds)
        max_wait = settings.direct_llm_max_wait_seconds
        if wait_seconds > max_wait:
            retry_at = datetime.now(UTC) + timedelta(seconds=wait_seconds)
            tracker.record_wait(
                context=context,
                wait_seconds=wait_seconds,
                reason="deferred_window_exceeds_budget",
                call_type=call_type,
            )
            raise DirectLlmDeferred(
                "direct LLM rate-limit wait deferred",
                retry_at=retry_at,
                wait_seconds=wait_seconds,
            )
        tracker.record_wait(
            context=context,
            wait_seconds=wait_seconds,
            reason="rpm_window_full",
            call_type=call_type,
        )
        if on_rate_limit_wait is not None:
            await on_rate_limit_wait(wait_seconds)
        await asyncio.sleep(wait_seconds)
        await self.wait_if_needed(
            context=context,
            tracker=tracker,
            call_type=call_type,
            on_rate_limit_wait=on_rate_limit_wait,
        )


_RATE_LIMITER = _DirectLlmRateLimiter()
_GEMMA_MODEL_SEMAPHORE = asyncio.Semaphore(settings.langgraph_max_concurrent_gemma_calls)
_CREDENTIAL_SEMAPHORE_LOCK = asyncio.Lock()
_CREDENTIAL_SEMAPHORES: dict[tuple[str, str, str], asyncio.Semaphore] = {}


async def wait_for_provider_rate_limit(
    *,
    context: DirectLlmCallContext,
    tracker: RunLlmTracker,
    call_type: str,
    on_rate_limit_wait: Callable[[float], Awaitable[None]] | None = None,
) -> None:
    await _RATE_LIMITER.wait_if_needed(
        context=context,
        tracker=tracker,
        call_type=call_type,
        on_rate_limit_wait=on_rate_limit_wait,
    )


async def _credential_semaphore(
    context: DirectLlmCallContext,
) -> asyncio.Semaphore:
    credential_key = context.key_fingerprint or context.credential_id
    key = (credential_key, context.provider, context.model)
    async with _CREDENTIAL_SEMAPHORE_LOCK:
        semaphore = _CREDENTIAL_SEMAPHORES.get(key)
        if semaphore is None:
            semaphore = asyncio.Semaphore(1)
            _CREDENTIAL_SEMAPHORES[key] = semaphore
        return semaphore


def _is_google_provider(provider: str) -> bool:
    try:
        return normalize_provider_name(provider) == "google"
    except ValueError:
        return False


def _is_gemma_model(model: str) -> bool:
    return model.strip().lower().startswith("gemma")


def _is_provider_rate_limit_error(exc: BaseException) -> bool:
    if _provider_http_status(exc) == 429:
        return True
    if _provider_status(exc) == "RESOURCE_EXHAUSTED":
        return True
    raw = str(exc)
    lowered = raw.lower()
    uppered = raw.upper()
    return any(
        marker in lowered or marker in uppered
        for marker in ("429", "RESOURCE_EXHAUSTED", "rate_limit", "rate limit")
    )


def _provider_http_status(exc: BaseException) -> int | None:
    code = getattr(exc, "code", None)
    if isinstance(code, int) and not isinstance(code, bool):
        return code
    provider_error = getattr(exc, "provider_error", None)
    if isinstance(provider_error, dict):
        status = provider_error.get("provider_http_status")
        if isinstance(status, int) and not isinstance(status, bool):
            return status
    return None


def _provider_status(exc: BaseException) -> str | None:
    status = getattr(exc, "status", None)
    if isinstance(status, str) and status.strip():
        return status.strip().upper()
    provider_error = getattr(exc, "provider_error", None)
    if isinstance(provider_error, dict):
        provider_status = provider_error.get("provider_status")
        if isinstance(provider_status, str) and provider_status.strip():
            return provider_status.strip().upper()
    return None


def _is_provider_overload_error(exc: BaseException) -> bool:
    if isinstance(exc, TimeoutError):
        return False
    if _is_provider_rate_limit_error(exc):
        return False
    if _provider_http_status(exc) == 502 or _provider_status(exc) == "BAD_GATEWAY":
        return True
    raw = str(exc)
    lowered = raw.lower()
    uppered = raw.upper()
    return any(
        marker in lowered or marker in uppered
        for marker in (
            "502",
            "503",
            "BAD_GATEWAY",
            "bad gateway",
            "UNAVAILABLE",
            "high demand",
            "temporarily overloaded",
            "running out of capacity",
        )
    )


def _provider_error_hint(exc: BaseException) -> str | None:
    if isinstance(exc, TimeoutError):
        return "provider_timeout"
    if _is_provider_rate_limit_error(exc):
        return "provider_rate_limit"
    if _is_provider_overload_error(exc):
        return "provider_overloaded"
    return None


def _safe_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str):
        value = value.strip()
        if value.isdigit():
            return int(value)
    return None


def _safe_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        value = value.strip()
        if value.endswith("s"):
            value = value[:-1]
        try:
            return float(value)
        except ValueError:
            return None
    return None


def _clip_error_text(value: Any, limit: int = 500) -> str | None:
    if value is None:
        return None
    text = _BEARER_TOKEN_RE.sub("Bearer [REDACTED]", redact_secret_text(str(value))).strip()
    if not text:
        return None
    return text[:limit]


def _hash_provider_subject(value: Any) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    return hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()[:16]


def _response_json(response: Any) -> Any:
    if response is None:
        return None
    json_method = getattr(response, "json", None)
    if callable(json_method):
        try:
            return json_method()
        except Exception:
            return None
    return None


def _response_header(response: Any, name: str) -> str | None:
    headers = getattr(response, "headers", None)
    if not headers:
        return None
    try:
        for key, value in dict(headers).items():
            if str(key).lower() == name.lower() and str(key).lower() not in _SENSITIVE_HEADER_NAMES:
                return str(value)
    except Exception:
        return None
    return None


def _error_container(details: Any) -> dict[str, Any]:
    if isinstance(details, dict):
        error = details.get("error")
        if isinstance(error, dict):
            return error
        return details
    return {}


def _detail_items(details: Any) -> list[dict[str, Any]]:
    container = _error_container(details)
    raw_details = container.get("details")
    if isinstance(raw_details, list):
        return [item for item in raw_details if isinstance(item, dict)]
    return []


def _extract_quota_failure(payload: dict[str, Any], details: Any) -> None:
    for item in _detail_items(details):
        type_name = str(item.get("@type") or item.get("type") or "")
        if "QuotaFailure" not in type_name:
            continue
        violations = item.get("violations")
        if not isinstance(violations, list):
            continue
        for violation in violations:
            if not isinstance(violation, dict):
                continue
            metric = violation.get("quotaMetric") or violation.get("quota_metric")
            quota_id = violation.get("quotaId") or violation.get("quota_id")
            dimensions = (
                violation.get("quotaDimensions")
                or violation.get("quota_dimensions")
                or violation.get("dimensions")
            )
            subject_hash = _hash_provider_subject(violation.get("subject"))
            if metric and "quota_metric" not in payload:
                payload["quota_metric"] = _clip_error_text(metric, 240)
            if quota_id and "quota_id" not in payload:
                payload["quota_id"] = _clip_error_text(quota_id, 240)
            if isinstance(dimensions, dict) and "quota_dimensions" not in payload:
                payload["quota_dimensions"] = {
                    _clip_error_text(key, 80) or "unknown": _clip_error_text(value, 160)
                    for key, value in list(dimensions.items())[:8]
                }
            if subject_hash and "quota_subject_hash" not in payload:
                payload["quota_subject_hash"] = subject_hash
            break


def _extract_retry_delay(payload: dict[str, Any], details: Any, response: Any) -> None:
    for item in _detail_items(details):
        type_name = str(item.get("@type") or item.get("type") or "")
        if "RetryInfo" not in type_name:
            continue
        delay = (
            item.get("retryDelay")
            or item.get("retry_delay")
            or item.get("retryDelaySeconds")
        )
        seconds = _safe_float(delay)
        if seconds is not None:
            payload["retry_delay_seconds"] = round(seconds, 3)
            return
    retry_after = _response_header(response, "Retry-After")
    seconds = _safe_float(retry_after)
    if seconds is not None:
        payload["retry_delay_seconds"] = round(seconds, 3)


def _limit_provider_error_payload(payload: dict[str, Any]) -> dict[str, Any]:
    result = {key: value for key, value in payload.items() if value is not None}
    encoded = json.dumps(result, ensure_ascii=False, sort_keys=True, default=str)
    if len(encoded.encode("utf-8")) <= _PROVIDER_ERROR_MAX_JSON_BYTES:
        return result
    if isinstance(result.get("provider_message"), str):
        result["provider_message"] = result["provider_message"][:240]
    if isinstance(result.get("quota_dimensions"), dict):
        result["quota_dimensions"] = dict(list(result["quota_dimensions"].items())[:4])
    encoded = json.dumps(result, ensure_ascii=False, sort_keys=True, default=str)
    if len(encoded.encode("utf-8")) <= _PROVIDER_ERROR_MAX_JSON_BYTES:
        return result
    return {
        key: value
        for key, value in result.items()
        if key
        in {
            "provider_error_type",
            "provider_http_status",
            "provider_status",
            "provider_message",
            "quota_metric",
            "quota_id",
            "quota_subject_hash",
            "retry_delay_seconds",
            "details_present",
        }
    }


def provider_error_details(exc: BaseException) -> dict[str, Any] | None:
    details = getattr(exc, "details", None)
    response = getattr(exc, "response", None)
    response_json = _response_json(response)
    source = details if details is not None else response_json
    container = _error_container(source)
    code = _safe_int(getattr(exc, "code", None) or container.get("code"))
    status = getattr(exc, "status", None) or container.get("status")
    message = getattr(exc, "message", None) or container.get("message")
    if code is None:
        match = re.search(r"\b([45]\d\d)\b", str(exc))
        if match:
            code = int(match.group(1))
    if not status:
        match = re.search(r"\b([A-Z][A-Z0-9_]{3,})\b", str(exc))
        if match:
            status = match.group(1)
    payload: dict[str, Any] = {
        "provider_error_type": f"{type(exc).__module__}.{type(exc).__name__}",
        "provider_http_status": code,
        "provider_status": _clip_error_text(status, 120),
        "provider_message": _clip_error_text(message or str(exc), 500),
        "details_present": bool(_detail_items(source)),
    }
    if source is not None:
        _extract_quota_failure(payload, source)
        _extract_retry_delay(payload, source, response)
    elif response is not None:
        _extract_retry_delay(payload, {}, response)
    if not any(
        payload.get(key)
        for key in ("provider_http_status", "provider_status", "provider_message")
    ):
        return None
    return _limit_provider_error_payload(payload)


def _direct_llm_error_from_provider(
    exc: BaseException,
    *,
    safe_message: str | None = None,
    provider_error: dict[str, Any] | None,
    provider_error_hint: str | None,
    provider_diagnostic: dict[str, Any],
) -> DirectLlmError:
    error = DirectLlmError(
        (safe_message or redact_secret_text(str(exc)))[:1000]
    )
    if provider_error:
        setattr(error, "provider_error", provider_error)
    if provider_error_hint:
        setattr(error, "provider_error_hint", provider_error_hint)
    setattr(error, "provider_diagnostic", provider_diagnostic)
    return error


def _bounded_provider_diagnostic(
    *,
    context: DirectLlmCallContext,
    failure_class: str,
    provider_error: dict[str, Any] | None,
    provider_error_hint: str | None,
) -> dict[str, Any]:
    """Return the only durable provider-failure fields Chat may retain."""

    details = provider_error or {}
    code = details.get("provider_http_status")
    status = details.get("provider_status")
    retryable = (
        failure_class == "timeout"
        or code in {408, 429, 500, 502, 503, 504}
        or str(status or "").upper()
        in {"BAD_GATEWAY", "DEADLINE_EXCEEDED", "RESOURCE_EXHAUSTED", "UNAVAILABLE"}
    )
    return {
        "node": context.node[:96],
        "provider": context.provider[:64],
        "model": context.model[:120],
        "failure_class": failure_class[:64],
        "provider_status": (
            None if status is None else str(status)[:120]
        ),
        "provider_code": (
            code if isinstance(code, int) and not isinstance(code, bool) else None
        ),
        "provider_error_hint": (
            None if provider_error_hint is None else provider_error_hint[:120]
        ),
        "retryable": retryable,
    }


def _generate_content_config(
    *,
    model: str,
    system_prompt: str,
    max_output_tokens: int,
    response_mime_type: str | None,
    response_schema: dict[str, Any] | type | types.Schema | None,
    thinking_level: str | None,
) -> types.GenerateContentConfig:
    return build_generate_content_config(
        model=model,
        system_prompt=system_prompt,
        max_output_tokens=max_output_tokens,
        response_mime_type=response_mime_type,
        response_schema=response_schema,
        thinking_level=thinking_level,
    )


async def generate_text(
    *,
    api_key: str,
    context: DirectLlmCallContext,
    tracker: RunLlmTracker,
    system_prompt: str,
    user_prompt: str,
    max_output_tokens: int = 1024,
    timeout_seconds: float = 180.0,
    response_schema: dict[str, Any] | type | types.Schema | None = None,
    response_mime_type: str | None = None,
    thinking_level: str | None = None,
    user_image_parts: list[DirectLlmImagePart] | None = None,
    on_rate_limit_wait: Callable[[float], Awaitable[None]] | None = None,
) -> DirectLlmResponse:
    if not _is_google_provider(context.provider):
        raise DirectLlmError(f"direct LLM only supports Google provider: {context.provider}")
    semaphore = _GEMMA_MODEL_SEMAPHORE if _is_gemma_model(context.model) else None
    credential_semaphore = await _credential_semaphore(context)
    adapter = get_provider_adapter(context.provider, context.model)

    async def _invoke() -> Any:
        request = ProviderRequest(
            api_key=api_key,
            model=context.model,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            max_output_tokens=max_output_tokens,
            timeout_seconds=timeout_seconds,
            response_schema=response_schema,
            response_mime_type=response_mime_type,
            thinking_level=thinking_level,
            image_parts=tuple(user_image_parts or ()),
        )
        if response_mime_type == "application/json":
            return await adapter.generate_json(request)
        return await adapter.generate_text(request)

    async def _attempt_once() -> DirectLlmResponse:
        await _RATE_LIMITER.wait_if_needed(
            context=context,
            tracker=tracker,
            call_type="generate_content",
            on_rate_limit_wait=on_rate_limit_wait,
        )
        provider_call_order = tracker.next_provider_call_order()
        call_order = tracker.next_call_order()
        started = time.perf_counter()
        try:
            async with credential_semaphore:
                if semaphore is None:
                    async with asyncio.timeout(timeout_seconds):
                        response = await _invoke()
                else:
                    async with semaphore:
                        async with asyncio.timeout(timeout_seconds):
                            response = await _invoke()
            usage = response.usage.as_direct_llm_usage()
            result = DirectLlmResponse(
                text=response.text,
                parsed=response.parsed,
                usage=usage,
                finish_reason=response.finish_reason,
            )
            tracker.record_call(
                context=context,
                call_order=call_order,
                provider_call_order=provider_call_order,
                status="ok",
                duration_ms=int((time.perf_counter() - started) * 1000),
                usage=usage,
                thinking_level=thinking_level,
                max_output_tokens=max_output_tokens,
                finish_reason=response.finish_reason,
            )
            return result
        except Exception as exc:
            failure_class = (
                "timeout" if isinstance(exc, TimeoutError) else type(exc).__name__
            )
            provider_error_hint = _provider_error_hint(exc)
            provider_error = provider_error_details(exc)
            if provider_error:
                provider_error = redact_exact_secrets(provider_error, api_key)
            safe_exc = (
                exc
                if isinstance(exc, DirectLlmError)
                else adapter.normalize_error(exc, api_key=api_key)
            )
            safe_message = redact_exact_secret_text(str(safe_exc), api_key)
            provider_diagnostic = _bounded_provider_diagnostic(
                context=context,
                failure_class=failure_class,
                provider_error=provider_error,
                provider_error_hint=provider_error_hint,
            )
            if isinstance(safe_exc, DirectLlmError) and safe_message != str(safe_exc):
                safe_exc.args = (safe_message,)
            tracker.record_call(
                context=context,
                call_order=call_order,
                provider_call_order=provider_call_order,
                status="error",
                duration_ms=int((time.perf_counter() - started) * 1000),
                failure_class=failure_class,
                provider_error_hint=provider_error_hint,
                provider_error=provider_error,
                thinking_level=thinking_level,
                max_output_tokens=max_output_tokens,
            )
            logger.warning(
                "direct_llm_call_failed character_id=%s agent_run_id=%s node=%s lane=%s "
                "provider=%s model=%s failure_class=%s error=%s",
                context.character_id,
                context.agent_run_id,
                context.node,
                context.lane,
                context.provider,
                context.model,
                failure_class,
                safe_message[:500],
            )
            if isinstance(exc, DirectLlmError):
                if provider_error and not hasattr(exc, "provider_error"):
                    setattr(exc, "provider_error", provider_error)
                if provider_error_hint and not hasattr(exc, "provider_error_hint"):
                    setattr(exc, "provider_error_hint", provider_error_hint)
                setattr(exc, "provider_diagnostic", provider_diagnostic)
                raise
            raise _direct_llm_error_from_provider(
                safe_exc,
                safe_message=safe_message,
                provider_error=provider_error,
                provider_error_hint=provider_error_hint,
                provider_diagnostic=provider_diagnostic,
            ) from exc

    last_error: DirectLlmError | None = None
    for attempt in range(2):
        try:
            return await _attempt_once()
        except DirectLlmError as exc:
            last_error = exc
            if attempt == 0 and _is_provider_overload_error(exc):
                wait_seconds = 60.0
                tracker.record_wait(
                    context=context,
                    wait_seconds=wait_seconds,
                    reason="provider_overloaded_retry",
                )
                await asyncio.sleep(wait_seconds)
                continue
            raise
    raise last_error or DirectLlmError("direct LLM call failed")


def _coerce_json_payload(response: DirectLlmResponse) -> dict[str, Any]:
    if isinstance(response.parsed, dict):
        return response.parsed
    text = response.text.strip()
    if not text:
        raise ValueError("empty_json_response")
    payload = json.loads(text)
    if not isinstance(payload, dict):
        raise TypeError("json_response_not_object")
    return payload


def _json_response_preview_parts(
    text: str, *, exact_secret: str | None = None
) -> tuple[str, str]:
    redacted = redact_exact_secret_text(text, exact_secret)
    if len(redacted) <= 700:
        return redacted, ""
    return redacted[:350], redacted[-350:]


def _json_shape_hint(
    *,
    text: str,
    exc: BaseException,
    parsed_present: bool,
) -> str:
    if _validation_summary(exc):
        return "schema_validation"
    stripped = text.strip()
    if not stripped:
        return "empty"
    lowered = stripped.lower()
    if stripped.startswith("```") or "```json" in lowered or "```" in stripped:
        return "markdown_fence"
    if not stripped.startswith(("{", "[")):
        return "natural_text_only"
    if isinstance(exc, json.JSONDecodeError):
        message = exc.msg.lower()
        if "extra data" in message:
            return "extra_text"
        if (
            "unterminated string" in message
            or "invalid control character" in message
            or "invalid \\escape" in message
        ):
            return "bad_escape"
        if stripped.startswith("{") and not stripped.endswith("}"):
            return "truncated_or_unclosed"
        if stripped.startswith("[") and not stripped.endswith("]"):
            return "truncated_or_unclosed"
    if parsed_present:
        return "schema_validation"
    return "unknown"


def _json_error_diagnostic(
    *,
    response: DirectLlmResponse | None,
    exc: BaseException,
    attempt: int,
    schema_validation: bool = False,
    exact_secret: str | None = None,
) -> dict[str, Any]:
    text = response.text if response is not None else ""
    preview_head, preview_tail = _json_response_preview_parts(
        text, exact_secret=exact_secret
    )
    parsed_present = bool(response is not None and response.parsed is not None)
    diagnostic: dict[str, Any] = {
        "attempt": attempt,
        "parse_error_type": type(exc).__name__,
        "error_message": redact_exact_secret_text(str(exc), exact_secret)[:240],
        "response_length": len(text),
        "finish_reason": response.finish_reason if response is not None else None,
        "parsed_present": parsed_present,
        "preview_head": preview_head,
        "shape_hint": "schema_validation" if schema_validation else _json_shape_hint(
            text=text,
            exc=exc,
            parsed_present=parsed_present,
        ),
    }
    if preview_tail:
        diagnostic["preview_tail"] = preview_tail
    return diagnostic


def _validation_summary(
    exc: BaseException, *, exact_secret: str | None = None
) -> list[dict[str, str]] | None:
    errors = getattr(exc, "errors", None)
    if not callable(errors):
        return None
    try:
        raw_errors = errors()
    except Exception:
        return None
    if not isinstance(raw_errors, list):
        return None
    summary: list[dict[str, str]] = []
    for raw_error in raw_errors[:4]:
        if not isinstance(raw_error, dict):
            continue
        loc = raw_error.get("loc")
        if isinstance(loc, (list, tuple)):
            loc_text = ".".join(str(item) for item in loc)
        else:
            loc_text = str(loc or "")
        item = {
            "path": loc_text[:160],
            "type": str(raw_error.get("type") or type(exc).__name__)[:120],
        }
        msg = raw_error.get("msg")
        if msg:
            item["message"] = redact_exact_secret_text(
                str(msg), exact_secret
            )[:240]
        summary.append(item)
    return summary or None


async def generate_json(
    *,
    api_key: str,
    context: DirectLlmCallContext,
    tracker: RunLlmTracker,
    system_prompt: str,
    user_prompt: str,
    response_schema: dict[str, Any] | type | types.Schema,
    validator: Callable[[dict[str, Any]], Any] | None = None,
    max_output_tokens: int = 1024,
    timeout_seconds: float = 180.0,
    thinking_level: str | None = None,
    user_image_parts: list[DirectLlmImagePart] | None = None,
    on_rate_limit_wait: Callable[[float], Awaitable[None]] | None = None,
    should_retry_json_error: Callable[
        [BaseException, dict[str, Any] | None, dict[str, Any], int], bool
    ]
    | None = None,
) -> Any:
    last_error_type = "unknown"
    last_validation_summary: list[dict[str, str]] | None = None
    json_error_diagnostics: list[dict[str, Any]] = []
    last_payload: dict[str, Any] | None = None
    for attempt in range(2):
        response: DirectLlmResponse | None = None
        payload_coerced = False
        last_payload = None
        try:
            response = await generate_text(
                api_key=api_key,
                context=context,
                tracker=tracker,
                system_prompt=system_prompt,
                user_prompt=user_prompt
                if attempt == 0
                else (
                    f"{user_prompt}\n\nThe previous attempt failed validation. "
                    f"Return one valid JSON object only. error_type={last_error_type}"
                ),
                max_output_tokens=max_output_tokens,
                timeout_seconds=timeout_seconds,
                response_schema=response_schema,
                response_mime_type="application/json",
                thinking_level=thinking_level,
                user_image_parts=user_image_parts,
                on_rate_limit_wait=on_rate_limit_wait,
            )
            payload = _coerce_json_payload(response)
            payload_coerced = True
            last_payload = payload
            return validator(payload) if validator is not None else payload
        except (json.JSONDecodeError, TypeError, ValueError) as exc:
            last_error_type = type(exc).__name__
            last_validation_summary = _validation_summary(
                exc, exact_secret=api_key
            )
            diagnostic = _json_error_diagnostic(
                response=response,
                exc=exc,
                attempt=attempt + 1,
                schema_validation=payload_coerced,
                exact_secret=api_key,
            )
            json_error_diagnostics.append(diagnostic)
            tracker.annotate_last_json_postprocess_error(
                context=context,
                diagnostic=diagnostic,
            )
            should_retry = (
                should_retry_json_error(exc, last_payload, diagnostic, attempt + 1)
                if should_retry_json_error is not None
                else True
            )
            if attempt == 0 and should_retry:
                continue
            raise DirectLlmJsonError(
                "direct LLM JSON parse failed",
                failure_class="json_parse_failed",
                parse_error_type=last_error_type,
                attempt_count=attempt + 1,
                validation_summary=last_validation_summary,
                json_error_diagnostics=json_error_diagnostics,
                last_payload=last_payload,
            ) from exc
        except Exception as exc:
            if isinstance(exc, DirectLlmJsonError):
                raise
            last_error_type = type(exc).__name__
            last_validation_summary = _validation_summary(
                exc, exact_secret=api_key
            )
            if not isinstance(exc, DirectLlmError):
                diagnostic = _json_error_diagnostic(
                    response=response,
                    exc=exc,
                    attempt=attempt + 1,
                    schema_validation=payload_coerced,
                    exact_secret=api_key,
                )
                json_error_diagnostics.append(diagnostic)
                tracker.annotate_last_json_postprocess_error(
                    context=context,
                    diagnostic=diagnostic,
                )
                should_retry = (
                    should_retry_json_error(
                        exc, last_payload, diagnostic, attempt + 1
                    )
                    if should_retry_json_error is not None
                    else True
                )
                if attempt == 0 and should_retry:
                    continue
                raise DirectLlmJsonError(
                    "direct LLM JSON parse failed",
                    failure_class="json_parse_failed",
                    parse_error_type=last_error_type,
                    attempt_count=attempt + 1,
                    validation_summary=last_validation_summary,
                    json_error_diagnostics=json_error_diagnostics,
                    last_payload=last_payload,
                ) from exc
            raise
    raise DirectLlmJsonError(
        "direct LLM JSON parse failed",
        failure_class="json_parse_failed",
        parse_error_type=last_error_type,
        attempt_count=2,
        validation_summary=last_validation_summary,
        json_error_diagnostics=json_error_diagnostics,
        last_payload=last_payload,
    )
