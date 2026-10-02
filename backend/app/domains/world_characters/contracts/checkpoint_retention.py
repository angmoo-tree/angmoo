"""Internal retention provenance and the durable V2 completion contract."""
from datetime import UTC, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, model_validator

RETENTION_KEY = "checkpoint_retention"
RETENTION_POLICY = "sns-completed-checkpoint-24h-v1"
TERMINAL_STATUSES = frozenset({"completed", "observed"})


class CheckpointRetention(BaseModel):
    model_config = ConfigDict(extra="forbid")
    policy: Literal["sns-completed-checkpoint-24h-v1"] = RETENTION_POLICY
    version: Annotated[StrictInt, Field(ge=1, le=1)] = 1
    applied_at_creation: StrictBool = True
    graph_complete: StrictBool = False
    state: Literal["retained", "claimed", "pruned"] = "retained"
    claim_token: str | None = None

    @model_validator(mode="after")
    def valid_claim(self):
        if not self.applied_at_creation:
            raise ValueError("checkpoint_creation_provenance_missing")
        if (self.state == "claimed") != bool(self.claim_token):
            raise ValueError("checkpoint_cleanup_claim_invalid")
        if self.state != "retained" and not self.graph_complete:
            raise ValueError("checkpoint_cleanup_confirmation_missing")
        return self


class LaneCompletion(BaseModel):
    model_config = ConfigDict(extra="allow")
    path: Literal["inbox", "feed", "routine"]
    status: Annotated[str, Field(min_length=1)]
    public_action_count: Annotated[StrictInt, Field(ge=0)]


class PublishCompletion(BaseModel):
    model_config = ConfigDict(extra="allow")
    public_action_count: Annotated[StrictInt, Field(ge=0)]


class ActivityCompletion(BaseModel):
    model_config = ConfigDict(extra="allow")
    engine: Literal["personalized_graph_v2"]
    contract_version: Literal[1, 2]
    execution_order: list[Literal["inbox", "feed", "routine"]]
    status: Literal["completed", "observed"]
    paths: dict[str, LaneCompletion]
    publish_result: PublishCompletion
    llm_usage_summary: dict
    llm_rate_limit_waits: list

    @model_validator(mode="after")
    def coherent_result(self):
        expected = ["inbox", "feed", "routine"] if self.contract_version == 2 else ["inbox", "routine", "feed"]
        if self.execution_order != expected or set(self.paths) != set(expected):
            raise ValueError("activity_completion_paths_invalid")
        if any(lane.path != name or lane.status == "failed" for name, lane in self.paths.items()):
            raise ValueError("activity_completion_lane_invalid")
        count = sum(lane.public_action_count for lane in self.paths.values())
        if count != self.publish_result.public_action_count or self.status != ("completed" if count else "observed"):
            raise ValueError("activity_completion_count_invalid")
        return self


def utc(value: datetime) -> datetime:
    # SQLite's mapped DateTime drops tzinfo; its canonical values are UTC.
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def completion(row) -> ActivityCompletion:
    """Malformed terminal records fail closed and never authorize a new graph."""
    try:
        value = ActivityCompletion.model_validate(row.result)
        if (row.engine != value.engine or row.contract_version != value.contract_version
                or row.status != value.status or row.stage != "Finalize"
                or not isinstance(row.finished_at, datetime)
                or not isinstance(row.started_at, datetime)
                or utc(row.finished_at) < utc(row.started_at)):
            raise ValueError("activity_completion_row_invalid")
        return value
    except (ValueError, TypeError) as exc:
        raise ValueError("activity_completed_result_invalid") from exc


def business_result(result: dict) -> dict:
    from app.domains.world_characters.contracts.social_io import POLICY_KEYS
    return {key: value for key, value in result.items() if key not in {RETENTION_KEY, *POLICY_KEYS, "normal_reservations"}}


def retention(result: dict | None) -> CheckpointRetention | None:
    try:
        return CheckpointRetention.model_validate((result or {}).get(RETENTION_KEY))
    except (ValueError, TypeError):
        return None
