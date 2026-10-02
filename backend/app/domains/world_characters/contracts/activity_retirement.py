"""Historical engine identities and explicit retirement outcomes."""
from dataclasses import dataclass

LEGACY_ABANDONED = "legacy_sns_abandoned"
HISTORICAL_TERMINAL = frozenset({"completed", "observed", "failed", "aborted", "abandoned", "cancelled"})


def retired_identity(engine: str, contract_version: int) -> bool:
    return engine == "current" or (engine == "personalized_graph_v2" and contract_version == 1)


@dataclass(frozen=True)
class ActivityTransition:
    state: str
    reason: str | None = None
    abandoned_count: int = 0
    converted_count: int = 0
