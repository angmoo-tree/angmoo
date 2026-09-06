from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from sqlalchemy.orm import Session

from app.domains.routines.constants import (
    MODEL_OVERLOADED_REPEATED_RETRY_MINUTES,
    MODEL_OVERLOADED_RETRY_MINUTES,
)
from app.domains.routines.contracts.backoff import RuntimeBackoff
from app.domains.routines.repository.run_backoff import recent_runs_for_model_overload


def _is_runtime_rate_limit_error(raw: str) -> bool:
    lowered = raw.lower()
    uppered = raw.upper()
    return any(
        marker in lowered or marker in uppered
        for marker in ("429", "RESOURCE_EXHAUSTED", "rate_limit", "rate limit", "throttl")
    )


def _is_runtime_model_overloaded_error(raw: str) -> bool:
    if _is_runtime_rate_limit_error(raw):
        return False
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


def _gateway_result_indicates_model_overloaded(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    if value.get("failure_class") == "model_overloaded":
        return True
    reason = value.get("reason")
    error = value.get("error")
    joined = " ".join(
        str(item)
        for item in (reason, error)
        if isinstance(item, str) and item.strip()
    )
    return bool(joined and _is_runtime_model_overloaded_error(joined))


def _has_recent_model_overloaded_run(
    db: Session | None,
    *,
    now: datetime,
    character_id: str | None,
    credential_id: str | None,
) -> bool:
    if db is None or (not character_id and not credential_id):
        return False
    rows = recent_runs_for_model_overload(
        db, now=now, character_id=character_id, credential_id=credential_id,
    )
    return any(_gateway_result_indicates_model_overloaded(run.gateway_result) for run in rows)


def _runtime_error_backoff(
    exc: Exception,
    *,
    now: datetime,
    db: Session | None = None,
    character_id: str | None = None,
    credential_id: str | None = None,
) -> RuntimeBackoff | None:
    raw = str(exc).strip()
    lowered = raw.lower()
    uppered = raw.upper()
    if _is_runtime_rate_limit_error(raw):
        return RuntimeBackoff(
            "model_rate_limit",
            "모델 사용 제한으로 잠시 대기 중",
            now + timedelta(minutes=45),
        )
    if _is_runtime_model_overloaded_error(raw):
        repeated_overload = _has_recent_model_overloaded_run(
            db,
            now=now,
            character_id=character_id,
            credential_id=credential_id,
        )
        retry_minutes = (
            MODEL_OVERLOADED_REPEATED_RETRY_MINUTES
            if repeated_overload
            else MODEL_OVERLOADED_RETRY_MINUTES
        )
        return RuntimeBackoff(
            "model_overloaded",
            "모델 일시 과부하로 재시도 예정",
            now + timedelta(minutes=retry_minutes),
            repeated_overload=repeated_overload,
        )
    if any(
        marker in lowered or marker in uppered
        for marker in (
            "timeout",
            "timed out",
            "unknown error occurred",
        )
    ):
        return RuntimeBackoff(
            "provider_timeout",
            "모델 응답 지연으로 재시도 예정",
            now + timedelta(minutes=10),
        )
    return None
