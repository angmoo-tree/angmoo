"""Frozen SNS generation policy; absence preserves legacy checkpoint semantics."""
from pydantic import BaseModel, ConfigDict
from typing import Literal

COMBINED_ONLY = "sns-combined-only.v1"
MODEL_TOKEN_BUDGET = "sns-model-token-budget.v1"
MODEL_BUDGET_REVISION = "gemini-models-countTokens.v1"
POLICY_KEYS = ("sns_generation_policy", "sns_input_budget_policy", "model_budget_revision")


class SnsGenerationPolicies(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    sns_generation_policy: Literal["sns-combined-only.v1"] | None = None
    sns_input_budget_policy: Literal["sns-model-token-budget.v1"] | None = None
    model_budget_revision: Literal["gemini-models-countTokens.v1"] | None = None


def read_generation_policies(value):
    result = SnsGenerationPolicies.model_validate({key: value[key] for key in POLICY_KEYS if value and key in value})
    if any(getattr(result, key) is None for key in POLICY_KEYS) and any(getattr(result, key) is not None for key in POLICY_KEYS):
        raise ValueError("activity_generation_policy_invalid")
    return result


def new_generation_policies():
    return SnsGenerationPolicies(sns_generation_policy=COMBINED_ONLY,
        sns_input_budget_policy=MODEL_TOKEN_BUDGET, model_budget_revision=MODEL_BUDGET_REVISION).model_dump()
