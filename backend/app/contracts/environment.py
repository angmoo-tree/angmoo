"""Frozen language and calendar inputs shared by admitted work."""
from dataclasses import asdict, dataclass
from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
import langcodes


def validate_memory_search_locale(value: str) -> str:
    """Validate admitted language data without normalizing or choosing a language."""
    if (not isinstance(value, str) or not 1 <= len(value) <= 80
        or "_" in value or not langcodes.tag_is_valid(value)
        or value.lower().split("-")[0] in {"und", "x"}):
        raise ValueError("environment_snapshot_invalid")
    return value


@dataclass(frozen=True)
class EnvironmentSnapshot:
    memory_search_locale: str = "en"
    timezone: str = "UTC"
    environment_revision: int = 0
    timezone_revision: int = 0
    output_policy: str = "persona-language.v1"

    def __post_init__(self):
        validate_memory_search_locale(self.memory_search_locale)
        if (type(self.environment_revision) is not int or self.environment_revision < 0
            or type(self.timezone_revision) is not int or self.timezone_revision < 0
            or self.output_policy != "persona-language.v1"):
            raise ValueError("environment_snapshot_invalid")
        try:
            if not isinstance(self.timezone, str):
                raise ValueError()
            ZoneInfo(self.timezone)
        except (ValueError, ZoneInfoNotFoundError):
            raise ValueError("environment_snapshot_invalid") from None

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict | None):
        if value is None:
            return cls()
        if not isinstance(value, dict):
            raise ValueError("environment_snapshot_invalid")
        return cls(**{key: value[key] for key in cls.__dataclass_fields__ if key in value})


@dataclass(frozen=True)
class AccountingPeriod:
    """UTC union of natural periods and unexpired transition protection.

    Owners retain charge IDs and settlement; this value owns no quota SQL.
    """
    key: str
    timezone: str
    ranges: tuple[tuple[datetime, datetime], ...]
    allowance_available_at: datetime
    protected: bool = False
    natural_bounds: tuple[datetime, datetime] | None = None
