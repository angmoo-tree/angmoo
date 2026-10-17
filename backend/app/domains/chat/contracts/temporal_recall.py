"""Immutable request time and bounded v4 time interpretation; never authorization."""
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
import hashlib
import json
from zoneinfo import ZoneInfo

TEMPORAL_SELECTION_PROTOCOL = "selection-args.hybrid.v4"
TEMPORAL_ADMISSION_REVISION = "hybrid-admission.v4"
TIME_CONTEXT_KEY = "_chat_time_context"


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


@dataclass(frozen=True, slots=True)
class ChatTimeContext:
    reference_utc: str
    timezone: str
    local_date: str
    revision: str = "chat-time-context.v1"

    def __post_init__(self):
        try:
            instant = datetime.fromisoformat(self.reference_utc.replace("Z", "+00:00"))
            valid = (instant.tzinfo is not None and instant.utcoffset().total_seconds() == 0
                and instant.astimezone(ZoneInfo(self.timezone)).date().isoformat() == self.local_date
                and self.revision == "chat-time-context.v1")
        except (ValueError, TypeError, KeyError, AttributeError):
            valid = False
        if not valid:
            raise ValueError("chat_time_context_invalid")

    @classmethod
    def create(cls, instant: datetime, timezone: str):
        if instant.tzinfo is None:
            raise ValueError("chat_time_context_invalid")
        return cls(instant.astimezone(UTC).isoformat().replace("+00:00", "Z"), timezone,
            instant.astimezone(ZoneInfo(timezone)).date().isoformat())

    @classmethod
    def read(cls, value):
        if not isinstance(value, dict) or set(value) != {"reference_utc", "timezone", "local_date", "revision", "digest"}:
            raise ValueError("chat_time_context_invalid")
        result = cls(**{key: item for key, item in value.items() if key != "digest"})
        if result.payload()["digest"] != value["digest"]:
            raise ValueError("chat_time_context_binding_invalid")
        return result

    @property
    def instant(self):
        return datetime.fromisoformat(self.reference_utc.replace("Z", "+00:00"))

    def payload(self):
        fields = asdict(self)
        return {**fields, "digest": _digest(fields)}


@dataclass(frozen=True, slots=True)
class TemporalRecall:
    """Invalid model time is data, not a valid RetrievalTimeMeaning."""
    validation: str
    requested_kind: str | None = None
    expression: str | None = None
    validation_code: str | None = None
    field_path: str | None = None
    context: ChatTimeContext | None = None
    resolution: str = "not_requested"
    query_origin: str = "none"
    route_change_reason: str | None = None
    applied_bounds: tuple[str, str] | None = None

    def __post_init__(self):
        if (self.validation not in {"valid", "invalid", "not_requested"}
            or self.resolution not in {"resolved", "ambiguous", "invalid", "not_requested"}
            or self.query_origin not in {"model_search_text", "original_user_message", "none"}
            or self.route_change_reason not in {None, "time_scope_invalid", "time_scope_ambiguous"}
            or self.validation_code not in {None, "time_scope_invalid"}
            or self.field_path not in {None, "time_scope", "time_scope.kind", "time_scope.expression", "time_scope.unit",
                "time_scope.offset", "time_scope.period", "time_scope.timezone"}
            or self.requested_kind not in {None, "current_day", "historical_unspecified", "recent", "relative", "absolute_range"}
            or (self.expression is not None and (type(self.expression) is not str or len(self.expression) > 96))
            or (self.context is not None and not isinstance(self.context, ChatTimeContext))
            or (self.applied_bounds is not None and (not isinstance(self.applied_bounds, tuple)
                or len(self.applied_bounds) != 2 or self.resolution != "resolved"))
            or (self.validation == "invalid" and self.validation_code != "time_scope_invalid")):
            raise ValueError("temporal_recall_invalid")

    def payload(self):
        result = asdict(self)
        result["context"] = self.context.payload() if self.context else None
        return result

    def diagnostic(self):
        return {"time_resolution": self.resolution, "requested_kind": self.requested_kind,
            "validation_code": self.validation_code, "field_path": self.field_path,
            "reference_utc": self.context.reference_utc if self.context else None,
            "timezone": self.context.timezone if self.context else None,
            "local_date": self.context.local_date if self.context else None,
            "context_digest": self.context.payload()["digest"] if self.context else None,
            "query_origin": self.query_origin, "route_change_reason": self.route_change_reason,
            "time_filter_applied": self.applied_bounds is not None,
            "applied_from": None if self.applied_bounds is None else self.applied_bounds[0],
            "applied_to": None if self.applied_bounds is None else self.applied_bounds[1]}
