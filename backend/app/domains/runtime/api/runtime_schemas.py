from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.domains.runtime.domain.diagnostic_codes import RuntimeDiagnosticCode
from app.domains.runtime.domain.installation_state import (
    RUNTIME_STATUS_SCHEMA_VERSION,
    ApplicationRuntimeStatus,
    InstallationState,
    ProviderFailureClass,
    RuntimeComponentState,
)


class RuntimeStatusSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="before")
    @classmethod
    def normalize_utc_instants(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        return {
            key: (
                item.replace(tzinfo=UTC)
                if isinstance(item, datetime)
                and (item.tzinfo is None or item.utcoffset() is None)
                else item.astimezone(UTC)
                if isinstance(item, datetime)
                else item
            )
            for key, item in value.items()
        }


class RuntimeDependencyRead(RuntimeStatusSchema):
    name: str
    state: RuntimeComponentState
    required: bool = True
    reason_code: RuntimeDiagnosticCode | None = None


class RuntimeComponentRead(RuntimeStatusSchema):
    name: str
    state: RuntimeComponentState
    version: str | None = None
    started_at: datetime | None = None
    last_heartbeat_at: datetime | None = None
    reason_code: RuntimeDiagnosticCode | None = None
    dependencies: list[RuntimeDependencyRead] = Field(default_factory=list)


class MigrationRuntimeRead(RuntimeStatusSchema):
    state: RuntimeComponentState
    current_revision: str | None = None
    head_revision: str | None = None
    reason_code: RuntimeDiagnosticCode | None = None


class SchedulerRuntimeRead(RuntimeStatusSchema):
    state: RuntimeComponentState
    active_owner_id: str | None = None
    fencing_epoch: int | None = Field(default=None, ge=0)
    last_heartbeat_at: datetime | None = None
    lease_expires_at: datetime | None = None
    next_tick_at: datetime | None = None
    reason_code: RuntimeDiagnosticCode | None = None


class ProjectorRuntimeRead(RuntimeStatusSchema):
    state: RuntimeComponentState
    last_heartbeat_at: datetime | None = None
    lag_seconds: float | None = Field(default=None, ge=0)
    pending_count: int = Field(default=0, ge=0)
    retry_count: int = Field(default=0, ge=0)
    failed_count: int = Field(default=0, ge=0)
    dead_letter_count: int = Field(default=0, ge=0)
    reason_code: RuntimeDiagnosticCode | None = None


class ProviderUsageRuntimeRead(RuntimeStatusSchema):
    recent_call_count: int = Field(default=0, ge=0)
    recent_failure_class: ProviderFailureClass | None = None
    kill_switch_enabled: bool = False


class OwnerRuntimeRead(RuntimeStatusSchema):
    bootstrap_state: str
    owner_user_id: str | None = None
    registered_world_count: int = Field(default=0, ge=0)
    active_world_count: int = Field(default=0, ge=0)
    active_world_character_count: int = Field(default=0, ge=0)


class ActivityRuntimeRead(RuntimeStatusSchema):
    last_successful_run_id: str | None = None
    last_successful_post_id: str | None = None
    last_successful_beat_id: str | None = None
    last_successful_episode_id: str | None = None
    last_successful_at: datetime | None = None
    inbox_result_code: str | None = None
    feed_result_code: str | None = None


class RuntimeCapabilityRead(RuntimeStatusSchema):
    state: RuntimeComponentState
    reason_code: RuntimeDiagnosticCode | None = None


class LocalRuntimeStatusRead(RuntimeStatusSchema):
    schema_version: Literal["local-runtime-status-v1"] = (
        RUNTIME_STATUS_SCHEMA_VERSION
    )
    installation_state: InstallationState
    version: str
    runtime_profile: Literal[
        "LOCAL_EMBEDDED",
        "CONTRIBUTOR_EMBEDDED",
        "TEST",
    ] | None = None
    canonical_generation: str | None = None
    persistence_provider: Literal["sqlite"] | None = None
    graph_provider: Literal["ladybug", "none"] | None = None
    components: list[RuntimeComponentRead] = Field(default_factory=list)
    migration: MigrationRuntimeRead
    scheduler: SchedulerRuntimeRead
    projector: ProjectorRuntimeRead
    provider_usage: ProviderUsageRuntimeRead
    owner: OwnerRuntimeRead
    activity: ActivityRuntimeRead
    capabilities: dict[str, RuntimeCapabilityRead] = Field(default_factory=dict)


def runtime_status_read(
    status: ApplicationRuntimeStatus,
    *,
    runtime_profile: Literal[
        "LOCAL_EMBEDDED",
        "CONTRIBUTOR_EMBEDDED",
        "TEST",
    ] | None = None,
    canonical_generation: str | None = None,
    persistence_provider: Literal["sqlite"] | None = None,
    graph_provider: Literal["ladybug", "none"] | None = None,
) -> LocalRuntimeStatusRead:
    return LocalRuntimeStatusRead(
        installation_state=status.installation_state,
        version=status.version,
        runtime_profile=runtime_profile,
        canonical_generation=canonical_generation,
        persistence_provider=persistence_provider,
        graph_provider=graph_provider,
        components=[
            RuntimeComponentRead(
                name=component.name,
                state=component.state,
                version=component.version,
                started_at=component.started_at,
                last_heartbeat_at=component.last_heartbeat_at,
                reason_code=component.reason_code,
                dependencies=[
                    RuntimeDependencyRead(
                        name=dependency.name,
                        state=dependency.state,
                        required=dependency.required,
                        reason_code=dependency.reason_code,
                    )
                    for dependency in component.dependencies
                ],
            )
            for component in status.components
        ],
        migration=MigrationRuntimeRead(
            state=status.migration.state,
            current_revision=status.migration.current_revision,
            head_revision=status.migration.head_revision,
            reason_code=status.migration.reason_code,
        ),
        scheduler=SchedulerRuntimeRead(
            state=status.scheduler.state,
            active_owner_id=status.scheduler.active_owner_id,
            fencing_epoch=status.scheduler.fencing_epoch,
            last_heartbeat_at=status.scheduler.last_heartbeat_at,
            lease_expires_at=status.scheduler.lease_expires_at,
            next_tick_at=status.scheduler.next_tick_at,
            reason_code=status.scheduler.reason_code,
        ),
        projector=ProjectorRuntimeRead(
            state=status.projector.state,
            last_heartbeat_at=status.projector.last_heartbeat_at,
            lag_seconds=status.projector.lag_seconds,
            pending_count=status.projector.pending_count,
            retry_count=status.projector.retry_count,
            failed_count=status.projector.failed_count,
            dead_letter_count=status.projector.dead_letter_count,
            reason_code=status.projector.reason_code,
        ),
        provider_usage=ProviderUsageRuntimeRead(
            recent_call_count=status.provider_usage.recent_call_count,
            recent_failure_class=status.provider_usage.recent_failure_class,
            kill_switch_enabled=status.provider_usage.kill_switch_enabled,
        ),
        owner=OwnerRuntimeRead(
            bootstrap_state=status.owner.bootstrap_state,
            owner_user_id=status.owner.owner_user_id,
            registered_world_count=status.owner.registered_world_count,
            active_world_count=status.owner.active_world_count,
            active_world_character_count=status.owner.active_world_character_count,
        ),
        activity=ActivityRuntimeRead(
            last_successful_run_id=status.activity.last_successful_run_id,
            last_successful_post_id=status.activity.last_successful_post_id,
            last_successful_beat_id=status.activity.last_successful_beat_id,
            last_successful_episode_id=status.activity.last_successful_episode_id,
            last_successful_at=status.activity.last_successful_at,
            inbox_result_code=status.activity.inbox_result_code,
            feed_result_code=status.activity.feed_result_code,
        ),
        capabilities={
            capability.name: RuntimeCapabilityRead(
                state=capability.state,
                reason_code=capability.reason_code,
            )
            for capability in status.capabilities
        },
    )
