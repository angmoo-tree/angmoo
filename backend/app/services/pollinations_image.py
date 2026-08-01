from __future__ import annotations

import asyncio
import base64
from dataclasses import dataclass
import hashlib
import json
import logging
import re
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request

from app.core.config import settings
from app.services import bounded_http, provider_http


logger = logging.getLogger(__name__)

POLLINATIONS_IMAGE_URL = "https://gen.pollinations.ai/image"
POLLINATIONS_REFERER = "https://angmoo.com"
POLLINATIONS_USER_AGENT = "Angmoo/1.0"
POLLINATIONS_SAFE_FILTER = "privacy,secrets,sexual,violence,shield"
POLLINATIONS_PROMPT_PREVIEW_MAX = 160
POLLINATIONS_SAFE_HINT_TERMS = (
    "safe",
    "moderation",
    "blocked",
    "policy",
    "nsfw",
    "sexual",
    "violence",
    "privacy",
    "secrets",
    "shield",
)
POLLINATIONS_INPUT_HINT_TERMS = (
    "input",
    "schema",
    "model",
    "unsupported",
    "invalid",
    "bad_request",
    "bad request",
)
POLLINATIONS_SENSITIVE_HEADERS = frozenset(
    {"Authorization", "X-Pollinations-Api-Key"}
)
POLLINATIONS_REFERENCE_FALLBACK_FAILURES = {
    "http_400",
    "http_404",
    "http_422",
    "invalid_image",
    "invalid_response",
}


class PollinationsImageError(Exception):
    def __init__(
        self,
        message: str,
        *,
        failure_class: str,
        status_code: int | None = None,
        response_body_preview: str | None = None,
        response_content_type: str | None = None,
        request_url_length: int | None = None,
        prompt_length: int | None = None,
        reference_sent: bool | None = None,
        safe_filter: str | None = None,
        diagnostic_hint: str | None = None,
        relay_elapsed_ms: int | None = None,
        provider_request_id: str | None = None,
    ) -> None:
        super().__init__(message)
        self.failure_class = failure_class
        self.status_code = status_code
        self.response_body_preview = None
        self.response_content_type = response_content_type
        self.request_url_length = request_url_length
        self.prompt_length = prompt_length
        self.reference_sent = reference_sent
        self.safe_filter = safe_filter
        self.diagnostic_hint = diagnostic_hint
        self.relay_elapsed_ms = relay_elapsed_ms
        self.provider_request_id = provider_request_id


@dataclass(frozen=True)
class PollinationsGeneratedImage:
    content_type: str
    content: bytes
    fallback_used: bool
    safe_filter: str | None = POLLINATIONS_SAFE_FILTER
    relay_elapsed_ms: int | None = None


@dataclass(frozen=True)
class _PollinationsTransportResponse:
    content_type: str
    content: bytes
    relay_elapsed_ms: int | None = None


async def generate_image(
    *,
    api_key: str,
    model: str,
    prompt: str,
    reference_image_url: str | None = None,
    allow_reference_fallback: bool = True,
    timeout_seconds: float = 90.0,
    prompt_hash: str | None = None,
    log_context: dict[str, Any] | None = None,
    route_mode: str = "direct",
    safe_filter: str | None = POLLINATIONS_SAFE_FILTER,
    width: int = 1024,
    height: int = 768,
    seed: int = -1,
) -> PollinationsGeneratedImage:
    prompt_hash = prompt_hash or _prompt_hash(prompt)
    if reference_image_url:
        try:
            response = _normalize_transport_response(
                await _request_image(
                    api_key=api_key,
                    model=model,
                    prompt=prompt,
                    reference_image_url=reference_image_url,
                    timeout_seconds=timeout_seconds,
                    prompt_hash=prompt_hash,
                    log_context=log_context,
                    route_mode=route_mode,
                    safe_filter=safe_filter,
                    width=width,
                    height=height,
                    seed=seed,
                )
            )
            return PollinationsGeneratedImage(
                content_type=response.content_type,
                content=response.content,
                fallback_used=False,
                safe_filter=safe_filter,
                relay_elapsed_ms=response.relay_elapsed_ms,
            )
        except PollinationsImageError as exc:
            if (
                not allow_reference_fallback
                or exc.failure_class not in POLLINATIONS_REFERENCE_FALLBACK_FAILURES
            ):
                raise

    response = _normalize_transport_response(
        await _request_image(
            api_key=api_key,
            model=model,
            prompt=prompt,
            reference_image_url=None,
            timeout_seconds=timeout_seconds,
            prompt_hash=prompt_hash,
            log_context=log_context,
            route_mode=route_mode,
            safe_filter=safe_filter,
            width=width,
            height=height,
            seed=seed,
        )
    )
    return PollinationsGeneratedImage(
        content_type=response.content_type,
        content=response.content,
        fallback_used=bool(reference_image_url),
        safe_filter=safe_filter,
        relay_elapsed_ms=response.relay_elapsed_ms,
    )


async def _request_image(
    *,
    api_key: str,
    model: str,
    prompt: str,
    reference_image_url: str | None,
    timeout_seconds: float,
    prompt_hash: str,
    log_context: dict[str, Any] | None,
    route_mode: str = "direct",
    safe_filter: str | None = POLLINATIONS_SAFE_FILTER,
    width: int = 1024,
    height: int = 768,
    seed: int = -1,
) -> _PollinationsTransportResponse:
    if route_mode == "lambda":
        return await _request_image_via_lambda(
            api_key=api_key,
            model=model,
            prompt=prompt,
            reference_image_url=reference_image_url,
            timeout_seconds=timeout_seconds,
            prompt_hash=prompt_hash,
            log_context=log_context,
            safe_filter=safe_filter,
            width=width,
            height=height,
            seed=seed,
        )
    return await _request_image_direct(
        api_key=api_key,
        model=model,
        prompt=prompt,
        reference_image_url=reference_image_url,
        timeout_seconds=timeout_seconds,
        prompt_hash=prompt_hash,
        log_context=log_context,
        safe_filter=safe_filter,
        width=width,
        height=height,
        seed=seed,
    )


async def _request_image_direct(
    *,
    api_key: str,
    model: str,
    prompt: str,
    reference_image_url: str | None,
    timeout_seconds: float,
    prompt_hash: str,
    log_context: dict[str, Any] | None,
    safe_filter: str | None,
    width: int,
    height: int,
    seed: int,
) -> _PollinationsTransportResponse:
    def _run_sync() -> _PollinationsTransportResponse:
        query: dict[str, str] = {
            "model": model,
            "width": str(width),
            "height": str(height),
            "seed": str(seed),
            "nologo": "true",
        }
        if safe_filter is not None:
            query["safe"] = safe_filter
        if reference_image_url:
            query["image"] = reference_image_url
        url = f"{POLLINATIONS_IMAGE_URL}/{quote(prompt, safe='')}?{urlencode(query)}"
        request_url_length = len(url)
        prompt_length = len(prompt)
        reference_sent = reference_image_url is not None
        request = Request(
            url,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Accept": "image/jpeg,image/png,image/webp",
                "Accept-Encoding": "identity",
                "User-Agent": POLLINATIONS_USER_AGENT,
                "Referer": POLLINATIONS_REFERER,
            },
            method="GET",
        )
        try:
            with _open_pollinations_request(request, timeout_seconds) as response:
                content_type = (
                    response.headers.get("Content-Type", "")
                    .split(";", 1)[0]
                    .strip()
                    .lower()
                )
                content = bounded_http.read_bounded_response(
                    response,
                    max_bytes=bounded_http.MAX_PROVIDER_IMAGE_BYTES,
                )
        except bounded_http.ResponseTooLargeError as exc:
            raise PollinationsImageError(
                "Pollinations image response was too large",
                failure_class="invalid_image",
            ) from exc
        except HTTPError as exc:
            failure_class = f"http_{exc.code}"
            diagnostic = provider_http.read_safe_http_error_diagnostic(
                exc,
                classify_body=lambda body, content_type: classify_failure_diagnostic_hint(
                    failure_class=failure_class,
                    status_code=exc.code,
                    response_body_preview=body,
                    response_content_type=content_type,
                ),
            )
            _log_failure(
                model=model,
                failure_class=failure_class,
                status_code=exc.code,
                response_body_preview=None,
                response_content_type=diagnostic.content_type,
                prompt_hash=prompt_hash,
                prompt_length=prompt_length,
                request_url_length=request_url_length,
                reference_sent=reference_sent,
                prompt=prompt,
                log_context=log_context,
            )
            raise PollinationsImageError(
                f"Pollinations image request failed with HTTP {exc.code}",
                failure_class=failure_class,
                status_code=exc.code,
                response_body_preview=None,
                response_content_type=diagnostic.content_type,
                request_url_length=request_url_length,
                prompt_length=prompt_length,
                reference_sent=reference_sent,
                safe_filter=safe_filter,
                diagnostic_hint=diagnostic.diagnostic_hint,
                provider_request_id=diagnostic.request_id,
            ) from exc
        except TimeoutError as exc:
            _log_failure(
                model=model,
                failure_class="timeout",
                status_code=None,
                response_body_preview=None,
                response_content_type=None,
                prompt_hash=prompt_hash,
                prompt_length=prompt_length,
                request_url_length=request_url_length,
                reference_sent=reference_sent,
                prompt=prompt,
                log_context=log_context,
            )
            raise PollinationsImageError(
                "Pollinations image request timed out",
                failure_class="timeout",
                request_url_length=request_url_length,
                prompt_length=prompt_length,
                reference_sent=reference_sent,
                safe_filter=safe_filter,
                diagnostic_hint=classify_failure_diagnostic_hint(
                    failure_class="timeout",
                    status_code=None,
                    response_body_preview=None,
                    response_content_type=None,
                ),
            ) from exc
        except URLError as exc:
            reason = getattr(exc, "reason", None)
            failure_class = "timeout" if isinstance(reason, TimeoutError) else "network_error"
            _log_failure(
                model=model,
                failure_class=failure_class,
                status_code=None,
                response_body_preview=None,
                response_content_type=None,
                prompt_hash=prompt_hash,
                prompt_length=prompt_length,
                request_url_length=request_url_length,
                reference_sent=reference_sent,
                prompt=prompt,
                log_context=log_context,
            )
            raise PollinationsImageError(
                "Pollinations image request failed",
                failure_class=failure_class,
                request_url_length=request_url_length,
                prompt_length=prompt_length,
                reference_sent=reference_sent,
                safe_filter=safe_filter,
                diagnostic_hint=classify_failure_diagnostic_hint(
                    failure_class=failure_class,
                    status_code=None,
                    response_body_preview=None,
                    response_content_type=None,
                ),
            ) from exc

        if content_type not in {"image/jpeg", "image/png", "image/webp"}:
            _log_failure(
                model=model,
                failure_class="invalid_response",
                status_code=None,
                response_body_preview=None,
                response_content_type=content_type,
                prompt_hash=prompt_hash,
                prompt_length=prompt_length,
                request_url_length=request_url_length,
                reference_sent=reference_sent,
                prompt=prompt,
                log_context=log_context,
            )
            raise PollinationsImageError(
                "Pollinations image response was not an image",
                failure_class="invalid_response",
                response_content_type=content_type,
                request_url_length=request_url_length,
                prompt_length=prompt_length,
                reference_sent=reference_sent,
                safe_filter=safe_filter,
                diagnostic_hint=classify_failure_diagnostic_hint(
                    failure_class="invalid_response",
                    status_code=None,
                    response_body_preview=None,
                    response_content_type=content_type,
                ),
            )
        if not content:
            _log_failure(
                model=model,
                failure_class="invalid_image",
                status_code=None,
                response_body_preview=None,
                response_content_type=content_type,
                prompt_hash=prompt_hash,
                prompt_length=prompt_length,
                request_url_length=request_url_length,
                reference_sent=reference_sent,
                prompt=prompt,
                log_context=log_context,
            )
            raise PollinationsImageError(
                "Pollinations image response was empty",
                failure_class="invalid_image",
                response_content_type=content_type,
                request_url_length=request_url_length,
                prompt_length=prompt_length,
                reference_sent=reference_sent,
                safe_filter=safe_filter,
                diagnostic_hint=classify_failure_diagnostic_hint(
                    failure_class="invalid_image",
                    status_code=None,
                    response_body_preview=None,
                    response_content_type=content_type,
                ),
            )
        _log_success(
            model=model,
            content_type=content_type,
            byte_size=len(content),
            prompt_hash=prompt_hash,
            prompt_length=prompt_length,
            request_url_length=request_url_length,
            reference_sent=reference_sent,
            log_context=log_context,
        )
        return _PollinationsTransportResponse(content_type=content_type, content=content)

    return await asyncio.to_thread(_run_sync)


async def _request_image_via_lambda(
    *,
    api_key: str,
    model: str,
    prompt: str,
    reference_image_url: str | None,
    timeout_seconds: float,
    prompt_hash: str,
    log_context: dict[str, Any] | None,
    safe_filter: str | None,
    width: int,
    height: int,
    seed: int,
) -> _PollinationsTransportResponse:
    def _run_sync() -> _PollinationsTransportResponse:
        relay_url = settings.pollinations_image_relay_url
        relay_token = settings.pollinations_image_relay_token
        prompt_length = len(prompt)
        reference_sent = reference_image_url is not None
        if relay_url is None or relay_token is None:
            _log_failure(
                model=model,
                failure_class="relay_not_configured",
                status_code=None,
                response_body_preview=None,
                response_content_type=None,
                prompt_hash=prompt_hash,
                prompt_length=prompt_length,
                request_url_length=None,
                reference_sent=reference_sent,
                prompt=prompt,
                log_context=log_context,
            )
            raise PollinationsImageError(
                "Pollinations image relay is not configured",
                failure_class="relay_not_configured",
                prompt_length=prompt_length,
                reference_sent=reference_sent,
                safe_filter=safe_filter,
                diagnostic_hint=classify_failure_diagnostic_hint(
                    failure_class="relay_not_configured",
                    status_code=None,
                    response_body_preview=None,
                    response_content_type=None,
                ),
            )

        body: dict[str, Any] = {
            "model": model,
            "prompt": prompt,
            "width": width,
            "height": height,
            "seed": seed,
            "nologo": True,
            "timeout_seconds": max(1, int(timeout_seconds)),
        }
        if safe_filter is not None:
            body["safe"] = safe_filter
        if reference_image_url:
            body["image"] = reference_image_url
        encoded_body = json.dumps(body, ensure_ascii=False).encode("utf-8")
        request = Request(
            relay_url,
            data=encoded_body,
            headers={
                "Authorization": f"Bearer {relay_token}",
                "X-Pollinations-Api-Key": api_key,
                "Content-Type": "application/json",
                "Accept": "application/json",
                "Accept-Encoding": "identity",
                "User-Agent": POLLINATIONS_USER_AGENT,
                "Referer": POLLINATIONS_REFERER,
            },
            method="POST",
        )
        try:
            with _open_relay_request(request, timeout_seconds + 5) as response:
                response_content_type = (
                    response.headers.get("Content-Type", "")
                    .split(";", 1)[0]
                    .strip()
                    .lower()
                )
                response_body = bounded_http.read_bounded_response(
                    response,
                    max_bytes=bounded_http.MAX_PROVIDER_RELAY_JSON_BYTES,
                )
                status_code = getattr(response, "status", None)
        except bounded_http.ResponseTooLargeError as exc:
            raise PollinationsImageError(
                "Pollinations image relay response was too large",
                failure_class="relay_invalid_response",
            ) from exc
        except HTTPError as exc:
            failure_class = "relay_unauthorized" if exc.code in {401, 403} else "relay_invalid_response"
            diagnostic = provider_http.read_safe_http_error_diagnostic(
                exc,
                classify_body=lambda body, content_type: classify_failure_diagnostic_hint(
                    failure_class=failure_class,
                    status_code=exc.code,
                    response_body_preview=body,
                    response_content_type=content_type,
                ),
            )
            _log_failure(
                model=model,
                failure_class=failure_class,
                status_code=exc.code,
                response_body_preview=None,
                response_content_type=diagnostic.content_type,
                prompt_hash=prompt_hash,
                prompt_length=prompt_length,
                request_url_length=len(relay_url),
                reference_sent=reference_sent,
                prompt=prompt,
                log_context=log_context,
            )
            raise PollinationsImageError(
                "Pollinations image relay request failed",
                failure_class=failure_class,
                status_code=exc.code,
                response_body_preview=None,
                response_content_type=diagnostic.content_type,
                request_url_length=len(relay_url),
                prompt_length=prompt_length,
                reference_sent=reference_sent,
                safe_filter=safe_filter,
                diagnostic_hint=diagnostic.diagnostic_hint,
                provider_request_id=diagnostic.request_id,
            ) from exc
        except TimeoutError as exc:
            _log_failure(
                model=model,
                failure_class="relay_timeout",
                status_code=None,
                response_body_preview=None,
                response_content_type=None,
                prompt_hash=prompt_hash,
                prompt_length=prompt_length,
                request_url_length=len(relay_url),
                reference_sent=reference_sent,
                prompt=prompt,
                log_context=log_context,
            )
            raise PollinationsImageError(
                "Pollinations image relay request timed out",
                failure_class="relay_timeout",
                request_url_length=len(relay_url),
                prompt_length=prompt_length,
                safe_filter=safe_filter,
                reference_sent=reference_sent,
                diagnostic_hint=classify_failure_diagnostic_hint(
                    failure_class="relay_timeout",
                    status_code=None,
                    response_body_preview=None,
                    response_content_type=None,
                ),
            ) from exc
        except URLError as exc:
            reason = getattr(exc, "reason", None)
            failure_class = "relay_timeout" if isinstance(reason, TimeoutError) else "relay_network_error"
            _log_failure(
                model=model,
                failure_class=failure_class,
                status_code=None,
                response_body_preview=None,
                response_content_type=None,
                prompt_hash=prompt_hash,
                prompt_length=prompt_length,
                request_url_length=len(relay_url),
                reference_sent=reference_sent,
                prompt=prompt,
                log_context=log_context,
            )
            raise PollinationsImageError(
                "Pollinations image relay request failed",
                failure_class=failure_class,
                request_url_length=len(relay_url),
                prompt_length=prompt_length,
                reference_sent=reference_sent,
                safe_filter=safe_filter,
                diagnostic_hint=classify_failure_diagnostic_hint(
                    failure_class=failure_class,
                    status_code=None,
                    response_body_preview=None,
                    response_content_type=None,
                ),
            ) from exc

        if response_content_type != "application/json":
            _log_failure(
                model=model,
                failure_class="relay_invalid_response",
                status_code=status_code,
                response_body_preview=None,
                response_content_type=response_content_type,
                prompt_hash=prompt_hash,
                prompt_length=prompt_length,
                request_url_length=len(relay_url),
                reference_sent=reference_sent,
                prompt=prompt,
                log_context=log_context,
            )
            raise PollinationsImageError(
                "Pollinations image relay response was not JSON",
                failure_class="relay_invalid_response",
                status_code=status_code,
                response_content_type=response_content_type,
                request_url_length=len(relay_url),
                prompt_length=prompt_length,
                reference_sent=reference_sent,
                safe_filter=safe_filter,
                diagnostic_hint=classify_failure_diagnostic_hint(
                    failure_class="relay_invalid_response",
                    status_code=status_code,
                    response_body_preview=None,
                    response_content_type=response_content_type,
                ),
            )
        try:
            payload = json.loads(response_body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise PollinationsImageError(
                "Pollinations image relay response was invalid JSON",
                failure_class="relay_invalid_response",
                status_code=status_code,
                response_content_type=response_content_type,
                request_url_length=len(relay_url),
                prompt_length=prompt_length,
                reference_sent=reference_sent,
                safe_filter=safe_filter,
                diagnostic_hint=classify_failure_diagnostic_hint(
                    failure_class="relay_invalid_response",
                    status_code=status_code,
                    response_body_preview=None,
                    response_content_type=response_content_type,
                ),
            ) from exc
        finally:
            response_body = b""
        if not isinstance(payload, dict):
            raise PollinationsImageError(
                "Pollinations image relay response was invalid",
                failure_class="relay_invalid_response",
                status_code=status_code,
                response_content_type=response_content_type,
                request_url_length=len(relay_url),
                prompt_length=prompt_length,
                reference_sent=reference_sent,
                safe_filter=safe_filter,
                diagnostic_hint=classify_failure_diagnostic_hint(
                    failure_class="relay_invalid_response",
                    status_code=status_code,
                    response_body_preview=None,
                    response_content_type=response_content_type,
                ),
            )

        relay_url_length = _int_or_none(payload.get("url_length")) or len(relay_url)
        relay_prompt_length = _int_or_none(payload.get("prompt_length")) or prompt_length
        relay_elapsed_ms = _int_or_none(payload.get("elapsed_ms"))
        response_safe_filter = _str_or_none(payload.get("safe_filter"))
        effective_safe_filter = response_safe_filter if response_safe_filter is not None else safe_filter
        if not payload.get("ok"):
            failure_class = str(payload.get("failure_class") or "relay_invalid_response")
            unsafe_preview = payload.pop("response_body_preview", None)
            response_body_for_classification = (
                unsafe_preview if isinstance(unsafe_preview, str) else None
            )
            content_type_value = payload.get("response_content_type") or payload.get("content_type")
            failure_content_type = (
                str(content_type_value).split(";", 1)[0].strip().lower()
                if content_type_value
                else None
            )
            failure_status_code = _int_or_none(payload.get("status_code"))
            diagnostic_hint = classify_failure_diagnostic_hint(
                failure_class=failure_class,
                status_code=failure_status_code,
                response_body_preview=response_body_for_classification,
                response_content_type=failure_content_type,
            )
            del unsafe_preview, response_body_for_classification
            _log_failure(
                model=model,
                failure_class=failure_class,
                status_code=failure_status_code,
                response_body_preview=None,
                response_content_type=failure_content_type,
                prompt_hash=prompt_hash,
                prompt_length=relay_prompt_length,
                request_url_length=relay_url_length,
                reference_sent=reference_sent,
                prompt=prompt,
                log_context=log_context,
            )
            raise PollinationsImageError(
                "Pollinations image relay returned a failed result",
                failure_class=failure_class,
                status_code=failure_status_code,
                response_body_preview=None,
                response_content_type=failure_content_type,
                request_url_length=relay_url_length,
                prompt_length=relay_prompt_length,
                reference_sent=reference_sent,
                safe_filter=effective_safe_filter,
                diagnostic_hint=diagnostic_hint,
                relay_elapsed_ms=relay_elapsed_ms,
            )

        image_content_type = (
            str(payload.get("content_type") or "").split(";", 1)[0].strip().lower()
        )
        encoded_content = payload.get("content_base64")
        if image_content_type not in {"image/jpeg", "image/png", "image/webp"} or not isinstance(encoded_content, str):
            raise PollinationsImageError(
                "Pollinations image relay success response missed image content",
                failure_class="relay_invalid_response",
                status_code=_int_or_none(payload.get("status_code")),
                response_content_type=image_content_type or response_content_type,
                request_url_length=relay_url_length,
                prompt_length=relay_prompt_length,
                reference_sent=reference_sent,
                safe_filter=effective_safe_filter,
                relay_elapsed_ms=relay_elapsed_ms,
                diagnostic_hint=classify_failure_diagnostic_hint(
                    failure_class="relay_invalid_response",
                    status_code=_int_or_none(payload.get("status_code")),
                    response_body_preview=None,
                    response_content_type=image_content_type or response_content_type,
                ),
            )
        if len(encoded_content) > (bounded_http.MAX_PROVIDER_IMAGE_BYTES * 4 // 3) + 8:
            raise PollinationsImageError(
                "Pollinations image relay response was too large",
                failure_class="invalid_image",
                response_content_type=image_content_type,
            )
        try:
            content = base64.b64decode(encoded_content, validate=True)
        except ValueError as exc:
            raise PollinationsImageError(
                "Pollinations image relay response contained invalid image data",
                failure_class="relay_invalid_response",
                status_code=_int_or_none(payload.get("status_code")),
                response_content_type=image_content_type,
                request_url_length=relay_url_length,
                prompt_length=relay_prompt_length,
                reference_sent=reference_sent,
                safe_filter=effective_safe_filter,
                relay_elapsed_ms=relay_elapsed_ms,
                diagnostic_hint=classify_failure_diagnostic_hint(
                    failure_class="relay_invalid_response",
                    status_code=_int_or_none(payload.get("status_code")),
                    response_body_preview=None,
                    response_content_type=image_content_type,
                ),
            ) from exc
        if len(content) > bounded_http.MAX_PROVIDER_IMAGE_BYTES:
            raise PollinationsImageError(
                "Pollinations image relay response was too large",
                failure_class="invalid_image",
                response_content_type=image_content_type,
            )
        if not content:
            raise PollinationsImageError(
                "Pollinations image relay response was empty",
                failure_class="invalid_image",
                status_code=_int_or_none(payload.get("status_code")),
                response_content_type=image_content_type,
                request_url_length=relay_url_length,
                prompt_length=relay_prompt_length,
                reference_sent=reference_sent,
                safe_filter=effective_safe_filter,
                relay_elapsed_ms=relay_elapsed_ms,
                diagnostic_hint=classify_failure_diagnostic_hint(
                    failure_class="invalid_image",
                    status_code=_int_or_none(payload.get("status_code")),
                    response_body_preview=None,
                    response_content_type=image_content_type,
                ),
            )
        _log_success(
            model=model,
            content_type=image_content_type,
            byte_size=len(content),
            prompt_hash=prompt_hash,
            prompt_length=relay_prompt_length,
            request_url_length=relay_url_length,
            reference_sent=reference_sent,
            log_context=log_context,
        )
        return _PollinationsTransportResponse(
            content_type=image_content_type,
            content=content,
            relay_elapsed_ms=relay_elapsed_ms,
        )

    return await asyncio.to_thread(_run_sync)


def _prompt_hash(prompt: str) -> str:
    return hashlib.sha256(prompt.encode("utf-8")).hexdigest()


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _str_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _normalize_transport_response(value: Any) -> _PollinationsTransportResponse:
    if isinstance(value, _PollinationsTransportResponse):
        return value
    content_type, content = value
    return _PollinationsTransportResponse(content_type=content_type, content=content)


def classify_failure_diagnostic_hint(
    *,
    failure_class: str,
    status_code: int | None,
    response_body_preview: str | None,
    response_content_type: str | None,
) -> str | None:
    normalized_failure = failure_class.lower()
    haystack = " ".join(
        value.lower()
        for value in (
            normalized_failure,
            response_body_preview or "",
            response_content_type or "",
        )
    )
    if normalized_failure.startswith("relay_"):
        return "relay_infra"
    if normalized_failure in {"http_401", "http_402", "http_403", "http_429"}:
        return "auth_or_quota"
    if any(term in haystack for term in POLLINATIONS_SAFE_HINT_TERMS):
        return "safe_filter_possible"
    if any(term in haystack for term in POLLINATIONS_INPUT_HINT_TERMS):
        return "provider_input_or_model_policy"
    if (
        normalized_failure in {"timeout", "network_error", "invalid_response"}
        or normalized_failure.startswith("http_5")
        or (status_code is not None and status_code >= 500)
    ):
        return "provider_unstable"
    return None


def _open_pollinations_request(request: Request, timeout_seconds: float):
    try:
        return provider_http.open_validated_request(
            request,
            timeout_seconds=timeout_seconds,
            initial_validator=lambda url: provider_http.validate_public_https_url(
                url,
                allowed_hosts={"gen.pollinations.ai"},
                allowed_path_prefixes={"/image"},
            ),
            redirect_validator=provider_http.validate_public_https_url,
            sensitive_headers=POLLINATIONS_SENSITIVE_HEADERS,
            allow_cross_origin_redirects=True,
        )
    except provider_http.ProviderUrlError as exc:
        raise URLError("Pollinations URL was not allowed") from exc


def _open_relay_request(request: Request, timeout_seconds: float):
    try:
        return provider_http.open_validated_request(
            request,
            timeout_seconds=timeout_seconds,
            initial_validator=provider_http.validate_public_https_url,
            redirect_validator=provider_http.validate_public_https_url,
            sensitive_headers=POLLINATIONS_SENSITIVE_HEADERS,
            allow_cross_origin_redirects=False,
        )
    except provider_http.ProviderUrlError as exc:
        raise URLError("Pollinations relay URL was not allowed") from exc


def _redacted_prompt_preview(prompt: str) -> str:
    text = " ".join(prompt.split())
    text = re.sub(r"Bearer\s+[A-Za-z0-9._\-]+", "Bearer [redacted]", text)
    text = re.sub(r"sk-[A-Za-z0-9_\-]{8,}", "sk-[redacted]", text)
    text = re.sub(r"AIza[0-9A-Za-z_\-]{20,}", "AIza[redacted]", text)
    return text[:POLLINATIONS_PROMPT_PREVIEW_MAX]


def _log_success(
    *,
    model: str,
    content_type: str,
    byte_size: int,
    prompt_hash: str,
    prompt_length: int,
    request_url_length: int,
    reference_sent: bool,
    log_context: dict[str, Any] | None,
) -> None:
    logger.info(
        "pollinations_image_success model=%s content_type=%s bytes=%s "
        "prompt_hash=%s prompt_length=%s url_length=%s reference_sent=%s%s",
        model,
        content_type,
        byte_size,
        prompt_hash,
        prompt_length,
        request_url_length,
        reference_sent,
        _format_log_context(log_context),
    )


def _log_failure(
    *,
    model: str,
    failure_class: str,
    status_code: int | None,
    response_body_preview: str | None,
    response_content_type: str | None,
    prompt_hash: str,
    prompt_length: int,
    request_url_length: int,
    reference_sent: bool,
    prompt: str,
    log_context: dict[str, Any] | None,
) -> None:
    del response_body_preview
    logger.warning(
        "pollinations_image_failed model=%s failure_class=%s status_code=%s "
        "response_content_type=%s prompt_hash=%s "
        "prompt_length=%s url_length=%s reference_sent=%s prompt_preview=%r%s",
        model,
        failure_class,
        status_code,
        response_content_type,
        prompt_hash,
        prompt_length,
        request_url_length,
        reference_sent,
        _redacted_prompt_preview(prompt),
        _format_log_context(log_context),
    )


def _format_log_context(log_context: dict[str, Any] | None) -> str:
    if not log_context:
        return ""
    allowed_keys = (
        "key_source",
        "character_id",
        "post_id",
        "run_id",
        "job_id",
        "reference_source",
        "source",
        "route_mode",
    )
    parts = []
    for key in allowed_keys:
        value = log_context.get(key)
        if value is None:
            continue
        parts.append(f"{key}={value}")
    if not parts:
        return ""
    return " " + " ".join(parts)
