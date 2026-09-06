"""Stable skipped/failed Social image results and service-key failure reasons."""
from typing import Any
from app.integrations import pollinations_image, replicate_image
from app.domains.social.contracts.image_generation import PreparedPostImage


def _service_failure_class(failure_class: str, *, key_source: str) -> str:
    if key_source != "service":
        return failure_class
    if failure_class == "http_402":
        return "service_key_budget_exhausted"
    if failure_class == "http_429":
        return "service_rate_limited"
    return failure_class



def _skipped(skip_reason: str, **extra: Any) -> PreparedPostImage:
    return PreparedPostImage(
        attempt={"status": "skipped", "skip_reason": skip_reason, **extra}
    )



def _failed(failure_class: str, **extra: Any) -> PreparedPostImage:
    return PreparedPostImage(
        attempt={"status": "failed", "failure_class": failure_class, **extra}
    )


def _pollinations_failed(
    exc: pollinations_image.PollinationsImageError,
    *,
    key_source: str,
    reference_source: str | None,
    reference_sent: bool,
    prompt_hash: str,
    prompt_length: int,
    quota_reservation_id: int | None,
    **extra: Any,
) -> PreparedPostImage:
    return _failed(
        _service_failure_class(exc.failure_class, key_source=key_source),
        reference_source=reference_source,
        reference_sent=(
            exc.reference_sent if exc.reference_sent is not None else reference_sent
        ),
        key_source=key_source,
        prompt_hash=prompt_hash,
        prompt_length=exc.prompt_length if exc.prompt_length is not None else prompt_length,
        pollinations_status_code=exc.status_code,
        pollinations_response_body_preview=exc.response_body_preview,
        pollinations_content_type=exc.response_content_type,
        pollinations_url_length=exc.request_url_length,
        safe_filter=exc.safe_filter,
        diagnostic_hint=exc.diagnostic_hint,
        relay_elapsed_ms=exc.relay_elapsed_ms,
        quota_reservation_id=quota_reservation_id,
        **extra,
    )


def _replicate_failed(
    exc: replicate_image.ReplicateImageError,
    *,
    key_source: str,
    reference_source: str | None,
    prompt_hash: str,
    prompt_length: int,
    quota_reservation_id: int | None,
    **extra: Any,
) -> PreparedPostImage:
    return _failed(
        _service_failure_class(exc.failure_class, key_source=key_source),
        reference_source=reference_source,
        reference_sent=False,
        key_source=key_source,
        prompt_hash=prompt_hash,
        prompt_length=prompt_length,
        provider_status_code=exc.status_code,
        provider_response_body_preview=exc.response_body_preview,
        provider_prediction_id=exc.prediction_id,
        quota_reservation_id=quota_reservation_id,
        **extra,
    )
