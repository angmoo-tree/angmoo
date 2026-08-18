from __future__ import annotations

from datetime import UTC, datetime, timedelta
import json
import os
import socket
from typing import Any
from urllib.parse import urlparse

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.domains.runtime.domain.diagnostic_codes import RuntimeDiagnosticCode
from app.domains.runtime.domain.installation_state import (
    ActivityRuntimeStatus,
    ApplicationRuntimeStatus,
    InstallationState,
    MigrationRuntimeStatus,
    OwnerRuntimeStatus,
    ProjectorRuntimeStatus,
    ProviderFailureClass,
    ProviderUsageRuntimeStatus,
    RuntimeCapabilityStatus,
    RuntimeComponentState,
    RuntimeComponentStatus,
    RuntimeDependencyStatus,
    SchedulerRuntimeStatus,
)


RUNTIME_MIGRATION_HEAD = "20260818_0081"
LOCAL_INSTALLATION_KEY = "local-installation"
SCHEDULER_SINGLETON_KEY = "resident-tick-scheduler"
RECENT_PROVIDER_WINDOW = timedelta(hours=1)


class SqlAlchemyApplicationRuntimeProbe:
    """Read privacy-safe application facts from canonical local stores.

    Host paths, Docker objects, and container identifiers deliberately do not
    belong here. Those are collected by the thin launcher on the host.
    """

    def __init__(self, db: Session, *, now: datetime | None = None) -> None:
        self._db = db
        self._now = _aware_utc(now or datetime.now(UTC))

    def read_status(self) -> ApplicationRuntimeStatus:
        migration = self._migration_status()
        owner = self._owner_status()
        scheduler = self._scheduler_status()
        projector, neo4j_state = self._projector_status()
        activity, provider_usage = self._activity_status(owner.owner_user_id)

        components = (
            RuntimeComponentStatus(
                name="backend",
                state=RuntimeComponentState.READY,
                version=_runtime_version(),
                dependencies=(
                    RuntimeDependencyStatus(
                        name="postgresql",
                        state=RuntimeComponentState.READY,
                    ),
                ),
            ),
            RuntimeComponentStatus(
                name="postgresql",
                state=RuntimeComponentState.READY,
                reason_code=migration.reason_code,
            ),
            RuntimeComponentStatus(
                name="neo4j",
                state=neo4j_state,
                reason_code=(
                    RuntimeDiagnosticCode.GRAPH_DEGRADED
                    if neo4j_state is RuntimeComponentState.DEGRADED
                    else None
                ),
            ),
        )
        installation_state = _installation_state(
            owner=owner,
            migration=migration,
            scheduler=scheduler,
            projector=projector,
            neo4j_state=neo4j_state,
        )
        return ApplicationRuntimeStatus(
            installation_state=installation_state,
            version=_runtime_version(),
            components=components,
            migration=migration,
            scheduler=scheduler,
            projector=projector,
            provider_usage=provider_usage,
            owner=owner,
            activity=activity,
            capabilities=(
                RuntimeCapabilityStatus(
                    name="world_package_import",
                    state=RuntimeComponentState.NOT_AVAILABLE,
                ),
                RuntimeCapabilityStatus(
                    name="world_package_staging",
                    state=RuntimeComponentState.NOT_AVAILABLE,
                ),
                RuntimeCapabilityStatus(
                    name="world_package_rollback",
                    state=RuntimeComponentState.NOT_AVAILABLE,
                ),
            ),
        )

    def _migration_status(self) -> MigrationRuntimeStatus:
        current = self._db.execute(text("SELECT version_num FROM alembic_version")).scalar()
        current_revision = str(current) if current is not None else None
        is_current = current_revision == RUNTIME_MIGRATION_HEAD
        return MigrationRuntimeStatus(
            state=(
                RuntimeComponentState.READY
                if is_current
                else RuntimeComponentState.DEGRADED
            ),
            current_revision=current_revision,
            head_revision=RUNTIME_MIGRATION_HEAD,
            reason_code=(
                None
                if is_current
                else RuntimeDiagnosticCode.MIGRATION_NOT_CURRENT
            ),
        )

    def _owner_status(self) -> OwnerRuntimeStatus:
        row = self._db.execute(
            text(
                """
                SELECT bootstrap_state, owner_user_id
                FROM installation_identities
                WHERE singleton_key = :singleton_key
                """
            ),
            {"singleton_key": LOCAL_INSTALLATION_KEY},
        ).mappings().first()
        if row is None:
            return OwnerRuntimeStatus(bootstrap_state="unclaimed")
        owner_user_id = _optional_string(row["owner_user_id"])
        if owner_user_id is None:
            return OwnerRuntimeStatus(
                bootstrap_state=str(row["bootstrap_state"] or "unclaimed")
            )

        registered_world_count = int(
            self._db.execute(
                text(
                    """
                    SELECT COUNT(*) FROM worlds
                    WHERE owner_user_id = :owner_user_id AND status <> 'archived'
                    """
                ),
                {"owner_user_id": owner_user_id},
            ).scalar_one()
        )
        active_world_count = int(
            self._db.execute(
                text(
                    """
                    SELECT COUNT(DISTINCT wc.world_id)
                    FROM character_active_worlds caw
                    JOIN world_characters wc ON wc.id = caw.world_character_id
                    JOIN characters c ON c.id = caw.character_id
                    WHERE c.owner_id = :owner_user_id
                    """
                ),
                {"owner_user_id": owner_user_id},
            ).scalar_one()
        )
        active_world_character_count = int(
            self._db.execute(
                text(
                    """
                    SELECT COUNT(*)
                    FROM world_characters wc
                    JOIN characters c ON c.id = wc.character_id
                    WHERE c.owner_id = :owner_user_id AND wc.status = 'active'
                    """
                ),
                {"owner_user_id": owner_user_id},
            ).scalar_one()
        )
        return OwnerRuntimeStatus(
            bootstrap_state=str(row["bootstrap_state"]),
            owner_user_id=owner_user_id,
            registered_world_count=registered_world_count,
            active_world_count=active_world_count,
            active_world_character_count=active_world_character_count,
        )

    def _scheduler_status(self) -> SchedulerRuntimeStatus:
        row = self._db.execute(
            text(
                """
                SELECT lease_owner_id, fencing_epoch, state, heartbeat_at,
                       lease_expires_at, next_tick_at, last_error_code
                FROM runtime_scheduler_leases
                WHERE singleton_key = :singleton_key
                """
            ),
            {"singleton_key": SCHEDULER_SINGLETON_KEY},
        ).mappings().first()
        if row is None:
            return SchedulerRuntimeStatus(state=RuntimeComponentState.STOPPED)
        lease_expires_at = _optional_datetime(row["lease_expires_at"])
        heartbeat_at = _optional_datetime(row["heartbeat_at"])
        active = (
            str(row["state"]) == "active"
            and row["lease_owner_id"] is not None
            and lease_expires_at is not None
            and lease_expires_at > self._now
        )
        stale = str(row["state"]) == "active" and not active
        return SchedulerRuntimeStatus(
            state=(
                RuntimeComponentState.RUNNING
                if active
                else (
                    RuntimeComponentState.DEGRADED
                    if stale
                    else RuntimeComponentState.STOPPED
                )
            ),
            active_owner_id=(
                _optional_string(row["lease_owner_id"])
                if active
                else None
            ),
            fencing_epoch=int(row["fencing_epoch"] or 0),
            last_heartbeat_at=heartbeat_at,
            lease_expires_at=lease_expires_at,
            next_tick_at=_optional_datetime(row["next_tick_at"]),
            reason_code=(
                RuntimeDiagnosticCode.SCHEDULER_HEARTBEAT_STALE
                if stale
                else None
            ),
        )

    def _projector_status(
        self,
    ) -> tuple[ProjectorRuntimeStatus, RuntimeComponentState]:
        row = self._db.execute(
            text(
                """
                SELECT
                    SUM(CASE WHEN status IN ('pending','processing') THEN 1 ELSE 0 END) AS pending_count,
                    SUM(CASE WHEN status = 'pending' AND attempt_count > 0 THEN 1 ELSE 0 END) AS retry_count,
                    SUM(CASE WHEN status = 'pending' AND last_error_class IS NOT NULL THEN 1 ELSE 0 END) AS failed_count,
                    SUM(CASE WHEN status = 'dead' THEN 1 ELSE 0 END) AS dead_letter_count,
                    MIN(CASE WHEN status IN ('pending','processing') THEN created_at END) AS oldest_pending_at,
                    MAX(updated_at) AS last_projection_at
                FROM graph_projection_outbox
                """
            )
        ).mappings().one()
        pending_count = int(row["pending_count"] or 0)
        retry_count = int(row["retry_count"] or 0)
        failed_count = int(row["failed_count"] or 0)
        dead_letter_count = int(row["dead_letter_count"] or 0)
        oldest_pending_at = _optional_datetime(row["oldest_pending_at"])
        lag_seconds = (
            max(0.0, (self._now - oldest_pending_at).total_seconds())
            if oldest_pending_at is not None
            else 0.0
        )

        if not settings.graph_projection_enabled:
            projector_state = RuntimeComponentState.NOT_AVAILABLE
            neo4j_state = RuntimeComponentState.NOT_AVAILABLE
        else:
            neo4j_available = _neo4j_available()
            degraded = (
                not neo4j_available
                or failed_count > 0
                or dead_letter_count > 0
            )
            projector_state = (
                RuntimeComponentState.DEGRADED
                if degraded
                else RuntimeComponentState.READY
            )
            neo4j_state = (
                RuntimeComponentState.READY
                if neo4j_available
                else RuntimeComponentState.DEGRADED
            )
        return (
            ProjectorRuntimeStatus(
                state=projector_state,
                # There is no canonical worker-heartbeat row yet. Do not
                # mislabel the latest Outbox mutation as a process heartbeat.
                last_heartbeat_at=None,
                lag_seconds=lag_seconds,
                pending_count=pending_count,
                retry_count=retry_count,
                failed_count=failed_count,
                dead_letter_count=dead_letter_count,
                reason_code=(
                    RuntimeDiagnosticCode.GRAPH_DEGRADED
                    if projector_state is RuntimeComponentState.DEGRADED
                    else None
                ),
            ),
            neo4j_state,
        )

    def _activity_status(
        self, owner_user_id: str | None
    ) -> tuple[ActivityRuntimeStatus, ProviderUsageRuntimeStatus]:
        if owner_user_id is None:
            return ActivityRuntimeStatus(), ProviderUsageRuntimeStatus(
                kill_switch_enabled=settings.AGENT_ACTIVITY_MAINTENANCE_ENABLED
            )
        rows = self._db.execute(
            text(
                """
                SELECT id, post_id, status, gateway_result, created_at, completed_at
                FROM agent_runs
                WHERE user_id = :owner_user_id AND created_at >= :since
                ORDER BY COALESCE(completed_at, created_at) DESC
                LIMIT 200
                """
            ),
            {
                "owner_user_id": owner_user_id,
                "since": self._now - RECENT_PROVIDER_WINDOW,
            },
        ).mappings().all()
        provider_call_count = 0
        recent_failure_class: ProviderFailureClass | None = None
        last_success: Any | None = None
        last_gateway_result: dict[str, Any] = {}
        for row in rows:
            gateway_result = _json_object(row["gateway_result"])
            provider_call_count += _provider_call_count(gateway_result)
            if recent_failure_class is None:
                recent_failure_class = _provider_failure_class(
                    str(row["status"]), gateway_result
                )
            if (
                last_success is None
                and str(row["status"]) in {"completed", "succeeded"}
                and row["post_id"] is not None
            ):
                last_success = row
                last_gateway_result = gateway_result

        activity = ActivityRuntimeStatus()
        if last_success is not None:
            activity = ActivityRuntimeStatus(
                last_successful_run_id=_optional_string(last_success["id"]),
                last_successful_post_id=_optional_string(last_success["post_id"]),
                last_successful_beat_id=_find_opaque_id(
                    last_gateway_result, ("activity_beat_id", "beat_id")
                ),
                last_successful_episode_id=_find_opaque_id(
                    last_gateway_result, ("activity_episode_id", "episode_id")
                ),
                last_successful_at=_optional_datetime(
                    last_success["completed_at"] or last_success["created_at"]
                ),
                inbox_result_code=_lane_result_code(last_gateway_result, "inbox"),
                feed_result_code=_lane_result_code(last_gateway_result, "feed"),
            )
        return activity, ProviderUsageRuntimeStatus(
            recent_call_count=provider_call_count,
            recent_failure_class=recent_failure_class,
            kill_switch_enabled=settings.AGENT_ACTIVITY_MAINTENANCE_ENABLED,
        )


def _runtime_version() -> str:
    return os.getenv("ANGMOO_VERSION", "development").strip() or "development"


def _installation_state(
    *,
    owner: OwnerRuntimeStatus,
    migration: MigrationRuntimeStatus,
    scheduler: SchedulerRuntimeStatus,
    projector: ProjectorRuntimeStatus,
    neo4j_state: RuntimeComponentState,
) -> InstallationState:
    if owner.bootstrap_state == "recovery_required":
        return InstallationState.RECOVERY_REQUIRED
    if owner.bootstrap_state != "claimed":
        return InstallationState.STARTING
    if migration.state is not RuntimeComponentState.READY:
        return InstallationState.DEGRADED
    if scheduler.state not in {
        RuntimeComponentState.RUNNING,
        RuntimeComponentState.STOPPED,
    }:
        return InstallationState.DEGRADED
    if projector.state is RuntimeComponentState.DEGRADED:
        return InstallationState.DEGRADED
    if neo4j_state is RuntimeComponentState.DEGRADED:
        return InstallationState.DEGRADED
    return InstallationState.READY


def _neo4j_available() -> bool:
    parsed = urlparse(settings.NEO4J_URI)
    if not parsed.hostname:
        return False
    port = parsed.port or 7687
    try:
        with socket.create_connection((parsed.hostname, port), timeout=0.5):
            return True
    except OSError:
        return False


def _provider_call_count(value: dict[str, Any]) -> int:
    summary = value.get("llm_usage_summary")
    if isinstance(summary, dict):
        return _nonnegative_int(summary.get("provider_call_count"))
    if "provider_call_count" in value:
        return _nonnegative_int(value.get("provider_call_count"))
    return 0


def _provider_failure_class(
    status: str, value: dict[str, Any]
) -> ProviderFailureClass | None:
    normalized_status = status.lower()
    reason = " ".join(
        str(value.get(key) or "")
        for key in ("reason", "error_code", "failure_class", "status")
    ).lower()
    if normalized_status not in {"failed", "error"} and not any(
        token in reason
        for token in ("failed", "error", "timeout", "unavailable", "rate_limit")
    ):
        return None
    if any(token in reason for token in ("auth", "credential", "api_key")):
        return ProviderFailureClass.AUTHENTICATION
    if any(token in reason for token in ("rate_limit", "quota", "429")):
        return ProviderFailureClass.RATE_LIMIT
    if "timeout" in reason:
        return ProviderFailureClass.TIMEOUT
    if any(token in reason for token in ("unavailable", "connection", "503")):
        return ProviderFailureClass.UNAVAILABLE
    if any(token in reason for token in ("invalid_response", "schema", "parse")):
        return ProviderFailureClass.INVALID_RESPONSE
    if "safety" in reason:
        return ProviderFailureClass.SAFETY
    return ProviderFailureClass.UNKNOWN


def _lane_result_code(value: dict[str, Any], lane: str) -> str | None:
    candidates = (
        value.get(f"{lane}_result"),
        value.get(f"{lane}_lane"),
        value.get(lane),
        value.get("feed_perception") if lane == "feed" else None,
    )
    for candidate in candidates:
        if isinstance(candidate, str):
            safe = _safe_code(candidate)
            if safe is not None:
                return safe
        if isinstance(candidate, dict):
            for key in ("result_code", "reason", "status", "action", "decision"):
                safe = _safe_code(candidate.get(key))
                if safe is not None:
                    return safe
    return None


def _safe_code(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip().lower()
    if not normalized or len(normalized) > 80:
        return None
    if not all(character.isalnum() or character in {"_", "-", "."} for character in normalized):
        return None
    return normalized


def _find_opaque_id(value: Any, keys: tuple[str, ...]) -> str | None:
    if isinstance(value, dict):
        for key in keys:
            candidate = value.get(key)
            if isinstance(candidate, str) and 0 < len(candidate) <= 128:
                return candidate
        for item in value.values():
            found = _find_opaque_id(item, keys)
            if found is not None:
                return found
    elif isinstance(value, list):
        for item in value:
            found = _find_opaque_id(item, keys)
            if found is not None:
                return found
    return None


def _json_object(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except (TypeError, ValueError):
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _nonnegative_int(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _optional_string(value: Any) -> str | None:
    return str(value) if value is not None else None


def _optional_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return _aware_utc(value)
    try:
        return _aware_utc(datetime.fromisoformat(str(value)))
    except ValueError:
        return None


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
