"""Shared immutable generation policy; no domain queries or persistence.

World-character run creation and Routine generation use this same value,
without either domain importing the other domain's implementation.
"""
from dataclasses import dataclass

LEGACY_OUTPUT = "routine-output.legacy.v1"
ENUM_OUTPUT = "routine-output.enum-preserved.v1"


@dataclass(frozen=True)
class RoutineOutputPolicy:
    output_contract: str = LEGACY_OUTPUT
    state_schema_version: int = 1
    thought_policy: str = "thought_v1"

    def __post_init__(self):
        if self.output_contract not in {LEGACY_OUTPUT, ENUM_OUTPUT}:
            raise ValueError("routine_output_contract_unsupported")
        expected = 2 if self.output_contract == ENUM_OUTPUT else 1
        if self.state_schema_version != expected or self.thought_policy not in {"legacy", "thought_v1"}:
            raise ValueError("routine_policy_version_invalid")
        if expected == 2 and self.thought_policy != "thought_v1":
            raise ValueError("routine_policy_thought_invalid")


def select_policy(*, engine: str, sns_version: int, output_policy: str, thought_policy: str) -> RoutineOutputPolicy:
    enabled = engine == "personalized_graph_v2" and sns_version == 2 and thought_policy == "thought_v1" and output_policy == "enum_preserved_v1"
    return RoutineOutputPolicy(ENUM_OUTPUT if enabled else LEGACY_OUTPUT, 2 if enabled else 1, thought_policy)


def saved_policy(result: dict | None) -> RoutineOutputPolicy:
    # Missing metadata is an old run; never infer an upgrade from the environment.
    value = (result or {}).get("routine_policy")
    return RoutineOutputPolicy(**value) if value is not None else RoutineOutputPolicy()
