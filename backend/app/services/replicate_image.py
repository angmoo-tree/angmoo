from __future__ import annotations

import asyncio
from dataclasses import dataclass
import ipaddress
import json
import re
import socket
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

from app.config import settings
from app.integrations import bounded_http
from app.services import provider_http


REPLICATE_PREDICTIONS_URL = "https://api.replicate.com/v1/predictions"
REPLICATE_P_IMAGE_EDIT_PREDICTIONS_URL = (
    "https://api.replicate.com/v1/models/prunaai/p-image-edit/predictions"
)
REPLICATE_IMAGE_TIMEOUT_SECONDS = 90.0
REPLICATE_POLL_INTERVAL_SECONDS = 0.5
REPLICATE_USER_AGENT = "Angmoo/1.0"
REPLICATE_API_HOST = "api.replicate.com"
REPLICATE_OUTPUT_HOST = "replicate.delivery"
_REPLICATE_API_CREATE_PATHS = frozenset(
    {
        urlparse(REPLICATE_PREDICTIONS_URL).path,
        urlparse(REPLICATE_P_IMAGE_EDIT_PREDICTIONS_URL).path,
    }
)
_REPLICATE_PREDICTION_STATUS_PATH = re.compile(
    r"^/v1/predictions/[A-Za-z0-9_-]{1,128}$"
)


class ReplicateImageError(Exception):
    def __init__(
        self,
        message: str,
        *,
        failure_class: str,
        status_code: int | None = None,
        response_body_preview: str | None = None,
        prediction_id: str | None = None,
    ) -> None:
        super().__init__(message)
        self.failure_class = failure_class
        self.status_code = status_code
        self.response_body_preview = None
        self.prediction_id = prediction_id


@dataclass(frozen=True)
class ReplicateGeneratedImage:
    content_type: str
    content: bytes
    fallback_used: bool = False
    prediction_id: str | None = None
    elapsed_ms: int | None = None


async def generate_image(
    *,
    api_key: str,
    prompt: str,
    width: int,
    height: int,
    seed: int = -1,
    timeout_seconds: float = REPLICATE_IMAGE_TIMEOUT_SECONDS,
    log_context: dict[str, object] | None = None,
) -> ReplicateGeneratedImage:
    del log_context
    return await asyncio.to_thread(
        _generate_image_sync,
        api_key,
        prompt,
        width,
        height,
        seed,
        timeout_seconds,
    )


async def generate_p_image_edit(
    *,
    api_key: str,
    prompt: str,
    reference_image_url: str,
    seed: int = -1,
    timeout_seconds: float = REPLICATE_IMAGE_TIMEOUT_SECONDS,
    log_context: dict[str, object] | None = None,
) -> ReplicateGeneratedImage:
    del log_context
    return await asyncio.to_thread(
        _generate_p_image_edit_sync,
        api_key,
        prompt,
        reference_image_url,
        seed,
        timeout_seconds,
    )


def _generate_image_sync(
    api_key: str,
    prompt: str,
    width: int,
    height: int,
    seed: int,
    timeout_seconds: float,
) -> ReplicateGeneratedImage:
    started = time.perf_counter()
    payload = {
        "version": settings.replicate_zimage_turbo_lora_version,
        "input": {
            "prompt": prompt,
            "width": width,
            "height": height,
            "num_inference_steps": 9,
            "guidance_scale": 0,
            "seed": seed,
            "output_format": "jpg",
            "output_quality": 80,
        },
    }
    prediction = _request_json(
        method="POST",
        url=REPLICATE_PREDICTIONS_URL,
        api_key=api_key,
        payload=payload,
        timeout_seconds=timeout_seconds,
    )
    return _poll_prediction_sync(
        prediction,
        api_key=api_key,
        timeout_seconds=timeout_seconds,
        started=started,
    )


def _generate_p_image_edit_sync(
    api_key: str,
    prompt: str,
    reference_image_url: str,
    seed: int,
    timeout_seconds: float,
) -> ReplicateGeneratedImage:
    started = time.perf_counter()
    payload = {
        "input": {
            "prompt": prompt,
            "images": [reference_image_url],
            "turbo": True,
            "aspect_ratio": "match_input_image",
            "seed": seed,
            "disable_safety_checker": False,
            "no_op": False,
        }
    }
    prediction = _request_json(
        method="POST",
        url=REPLICATE_P_IMAGE_EDIT_PREDICTIONS_URL,
        api_key=api_key,
        payload=payload,
        timeout_seconds=timeout_seconds,
    )
    return _poll_prediction_sync(
        prediction,
        api_key=api_key,
        timeout_seconds=timeout_seconds,
        started=started,
    )


def _poll_prediction_sync(
    prediction: dict[str, object],
    *,
    api_key: str,
    timeout_seconds: float,
    started: float,
) -> ReplicateGeneratedImage:
    prediction_id = _prediction_id(prediction)
    prediction_url = _prediction_url(prediction)
    if not prediction_url:
        raise ReplicateImageError(
            "Replicate prediction URL was missing",
            failure_class="invalid_response",
            prediction_id=prediction_id,
        )

    deadline = time.monotonic() + timeout_seconds
    while True:
        status_payload = _request_json(
            method="GET",
            url=prediction_url,
            api_key=api_key,
            payload=None,
            timeout_seconds=timeout_seconds,
        )
        status = status_payload.get("status")
        if status == "succeeded":
            output_url = _output_url(status_payload.get("output"))
            if not output_url:
                raise ReplicateImageError(
                    "Replicate prediction output was missing",
                    failure_class="invalid_image",
                    prediction_id=prediction_id,
                )
            content_type, content = _download_image(
                output_url,
                timeout_seconds=timeout_seconds,
            )
            return ReplicateGeneratedImage(
                content_type=content_type,
                content=content,
                prediction_id=prediction_id,
                elapsed_ms=round((time.perf_counter() - started) * 1000),
            )
        if status in {"failed", "canceled", "aborted"}:
            status_payload.pop("error", None)
            raise ReplicateImageError(
                "Replicate prediction did not succeed",
                failure_class=f"prediction_{status}",
                prediction_id=prediction_id,
            )
        if time.monotonic() >= deadline:
            raise ReplicateImageError(
                "Replicate prediction timed out",
                failure_class="timeout",
                prediction_id=prediction_id,
            )
        time.sleep(REPLICATE_POLL_INTERVAL_SECONDS)


def _request_json(
    *,
    method: str,
    url: str,
    api_key: str,
    payload: dict[str, object] | None,
    timeout_seconds: float,
) -> dict[str, object]:
    request = Request(
        url,
        data=json.dumps(payload).encode("utf-8") if payload is not None else None,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Accept-Encoding": "identity",
            "User-Agent": REPLICATE_USER_AGENT,
        },
        method=method,
    )
    try:
        with _open_validated_request(
            request,
            timeout_seconds=timeout_seconds,
            purpose="api",
        ) as response:
            raw = bounded_http.read_bounded_response(
                response,
                max_bytes=bounded_http.MAX_PROVIDER_JSON_BYTES,
            ).decode("utf-8")
    except ReplicateImageError:
        raise
    except HTTPError as exc:
        diagnostic = provider_http.read_safe_http_error_diagnostic(exc)
        raise ReplicateImageError(
            f"Replicate request failed with HTTP {exc.code}",
            failure_class=f"http_{exc.code}",
            status_code=diagnostic.status_code,
        ) from exc
    except bounded_http.ResponseTooLargeError as exc:
        raise ReplicateImageError(
            "Replicate response was too large",
            failure_class="invalid_response",
        ) from exc
    except (TimeoutError, URLError, OSError) as exc:
        raise ReplicateImageError(
            "Replicate request failed",
            failure_class="network_error" if not isinstance(exc, TimeoutError) else "timeout",
        ) from exc
    try:
        decoded = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ReplicateImageError(
            "Replicate response was not JSON",
            failure_class="invalid_response",
        ) from exc
    if not isinstance(decoded, dict):
        raise ReplicateImageError(
            "Replicate response was not an object",
            failure_class="invalid_response",
        )
    return decoded


def _download_image(url: str, *, timeout_seconds: float) -> tuple[str, bytes]:
    request = Request(
        url,
        headers={
            "Accept": "image/*",
            "Accept-Encoding": "identity",
            "User-Agent": REPLICATE_USER_AGENT,
        },
    )
    try:
        with _open_validated_request(
            request,
            timeout_seconds=timeout_seconds,
            purpose="output",
        ) as response:
            content_type = (response.headers.get("Content-Type") or "image/jpeg").split(";", 1)[0].lower()
            content = bounded_http.read_bounded_response(
                response,
                max_bytes=bounded_http.MAX_PROVIDER_IMAGE_BYTES,
            )
    except ReplicateImageError:
        raise
    except bounded_http.ResponseTooLargeError as exc:
        raise ReplicateImageError(
            "Replicate output was too large",
            failure_class="invalid_image",
        ) from exc
    except (HTTPError, TimeoutError, URLError, OSError) as exc:
        raise ReplicateImageError("Replicate output download failed", failure_class="download_failed") from exc
    if not content or not content_type.startswith("image/"):
        raise ReplicateImageError("Replicate output was not an image", failure_class="invalid_image")
    return content_type, content


def _validate_replicate_url(url: str, *, purpose: str) -> None:
    parsed = urlparse(url)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.fragment
    ):
        raise ReplicateImageError(
            "Replicate URL was not allowed",
            failure_class="invalid_provider_url",
        )
    try:
        port = parsed.port
        host = parsed.hostname.encode("ascii").decode("ascii").lower()
    except (UnicodeError, ValueError) as exc:
        raise ReplicateImageError(
            "Replicate URL was not allowed",
            failure_class="invalid_provider_url",
        ) from exc
    if port not in {None, 443}:
        raise ReplicateImageError(
            "Replicate URL was not allowed",
            failure_class="invalid_provider_url",
        )

    if purpose == "api":
        path_allowed = (
            parsed.path in _REPLICATE_API_CREATE_PATHS
            or _REPLICATE_PREDICTION_STATUS_PATH.fullmatch(parsed.path) is not None
        )
        if host != REPLICATE_API_HOST or not path_allowed or parsed.query:
            raise ReplicateImageError(
                "Replicate API URL was not allowed",
                failure_class="invalid_provider_url",
            )
    elif purpose == "output":
        host_allowed = host == REPLICATE_OUTPUT_HOST or host.endswith(
            f".{REPLICATE_OUTPUT_HOST}"
        )
        if not host_allowed or not parsed.path.startswith("/"):
            raise ReplicateImageError(
                "Replicate output URL was not allowed",
                failure_class="invalid_image",
            )
    else:
        raise ValueError(f"Unsupported Replicate URL purpose: {purpose}")

    try:
        addresses = socket.getaddrinfo(
            host,
            443,
            type=socket.SOCK_STREAM,
        )
    except OSError as exc:
        raise ReplicateImageError(
            "Replicate URL could not be resolved",
            failure_class="network_error",
        ) from exc
    if not addresses:
        raise ReplicateImageError(
            "Replicate URL could not be resolved",
            failure_class="network_error",
        )
    for address in addresses:
        try:
            resolved_ip = ipaddress.ip_address(address[4][0].split("%", 1)[0])
        except ValueError as exc:
            raise ReplicateImageError(
                "Replicate URL resolved to an invalid address",
                failure_class="invalid_provider_url",
            ) from exc
        if not resolved_ip.is_global:
            raise ReplicateImageError(
                "Replicate URL resolved to a non-public address",
                failure_class="invalid_provider_url",
            )


class _ValidatedRedirectHandler(HTTPRedirectHandler):
    def __init__(self, purpose: str) -> None:
        super().__init__()
        self._purpose = purpose

    def redirect_request(
        self,
        request,
        file_pointer,
        code,
        message,
        headers,
        new_url,
    ):
        _validate_replicate_url(new_url, purpose=self._purpose)
        return super().redirect_request(
            request,
            file_pointer,
            code,
            message,
            headers,
            new_url,
        )


def _open_validated_request(
    request: Request,
    *,
    timeout_seconds: float,
    purpose: str,
):
    _validate_replicate_url(request.full_url, purpose=purpose)
    response = build_opener(_ValidatedRedirectHandler(purpose)).open(
        request,
        timeout=max(1, int(timeout_seconds)),
    )
    try:
        _validate_replicate_url(response.geturl(), purpose=purpose)
    except Exception:
        response.close()
        raise
    return response


def _prediction_id(payload: dict[str, object]) -> str | None:
    value = payload.get("id")
    return value if isinstance(value, str) else None


def _prediction_url(payload: dict[str, object]) -> str | None:
    urls = payload.get("urls")
    if isinstance(urls, dict):
        value = urls.get("get")
        if isinstance(value, str):
            return value
    value = payload.get("url")
    return value if isinstance(value, str) else None


def _output_url(output: object) -> str | None:
    if isinstance(output, str):
        return output
    if isinstance(output, list):
        for item in output:
            if isinstance(item, str):
                return item
    return None
