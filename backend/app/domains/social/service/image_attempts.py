"""Stable skipped/failed Social image results and service-key failure reasons."""
from typing import Any
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
