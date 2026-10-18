"""Provider-neutral auxiliary output and opaque delivery participation values."""
from dataclasses import dataclass
from typing import Literal, Protocol
from app.contracts.environment import validate_memory_search_locale

SITUATION_POLICY = "activity-situation.v1"


class SituationDelivery(Protocol):
    """Activity transports delivery proof; the Memory owner interprets it."""
    payload_digest: str


@dataclass(frozen=True)
class SituationDraft:
    target_key: str
    description: str | None
    status: Literal["valid", "missing", "invalid", "output_order_invalid"]
    error_code: str | None = None


def admitted_locale(value):
    if value is None:
        return None
    if not isinstance(value, dict) or value.get("policy") != SITUATION_POLICY:
        raise ValueError("situation_admission_policy_invalid")
    snapshot = value.get("snapshot")
    if snapshot is None:
        return None
    locale = snapshot.get("memory_search_locale") if isinstance(snapshot, dict) else None
    try:
        return validate_memory_search_locale(locale)
    except (TypeError, ValueError):
        raise ValueError("situation_admission_locale_invalid") from None
