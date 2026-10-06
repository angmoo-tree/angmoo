"""Frozen execution policies, independent from the SNS contract and Routine content."""
from typing import Literal

from pydantic import BaseModel, ConfigDict

COMMON_IO = "social-io.common.v1"
LANE_IO = "social-io.lane-scoped.v1"
LEGACY_ROUTINE_OUTPUT = "routine-split-output.legacy.v1"
BOUNDED_ROUTINE_OUTPUT = "routine-split-output.bounded.v1"
POLICY_KEYS = frozenset({"social_io_policy", "routine_output_policy"})


class SocialExecutionPolicies(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    social_io_policy: Literal["social-io.common.v1", "social-io.lane-scoped.v1"] = COMMON_IO
    routine_output_policy: Literal["routine-split-output.legacy.v1", "routine-split-output.bounded.v1"] = LEGACY_ROUTINE_OUTPUT


def read_policies(result: dict | None) -> SocialExecutionPolicies:
    """Missing metadata means the old policy; invalid metadata is never upgraded silently."""
    return SocialExecutionPolicies.model_validate({key: result[key] for key in POLICY_KEYS
        if result is not None and key in result})


def new_policies() -> dict:
    return SocialExecutionPolicies(social_io_policy=LANE_IO,
        routine_output_policy=BOUNDED_ROUTINE_OUTPUT).model_dump()
