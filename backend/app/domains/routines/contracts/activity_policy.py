"""Immutable activity permission result and its original prompt representation."""
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol
from zoneinfo import ZoneInfo
from app.domains.routines.constants import TENDENCY_PUBLIC_ACTION_NAMES


@dataclass(frozen=True)
class ActivityPolicy:
    within_active_hours: bool
    allowed_actions: tuple[str, ...]
    blocked_reasons: dict[str, str]
    next_tick_at: datetime
    summary: str
    target_interval_seconds: int = 0
    schedule_spread_seconds: int = 0
    schedule_spread_reason: str = ""
    tendency_summary: str = ""
    tendency_action_ranges: dict[str, object] | None = None
    planner_tendency_profile: dict[str, object] | None = None

    @property
    def should_skip_llm(self) -> bool:
        return not self.within_active_hours or not any(
            action != "observe" for action in self.allowed_actions
        )

    def to_prompt(self) -> str:
        allowed = ", ".join(self.allowed_actions) if self.allowed_actions else "none"
        blocked = (
            "\n".join(f"  - {action}: {reason}" for action, reason in self.blocked_reasons.items())
            if self.blocked_reasons
            else "  - none"
        )
        tendency = _format_tendency_prompt(
            self.tendency_summary, self.tendency_action_ranges
        )
        return f"""Backend activity policy for this tick:
- Allowed actions: {allowed}
- Blocked actions:
{blocked}
- Persona public-action tendency notes:
{tendency}
- If a public action is not listed as allowed, do not call its tool.
- Observe is not a tendency action. If no public action fits and observe is allowed, finish without public writes so the backend can record an observed fallback.
- Next scheduled tick after this run: {self.next_tick_at.isoformat()}"""

    def to_result(self) -> dict[str, object]:
        return {
            "within_active_hours": self.within_active_hours,
            "allowed_actions": list(self.allowed_actions),
            "blocked_reasons": self.blocked_reasons,
            "next_tick_at": self.next_tick_at.isoformat(),
            "target_interval_seconds": self.target_interval_seconds,
            "schedule_spread_seconds": self.schedule_spread_seconds,
            "schedule_spread_reason": self.schedule_spread_reason,
            "summary": self.summary,
            "tendency_summary": self.tendency_summary,
            "tendency_action_ranges": self.tendency_action_ranges or {},
        }



def _format_tendency_prompt(
    tendency_summary: str, action_ranges: dict[str, object] | None
) -> str:
    lines: list[str] = []
    if tendency_summary.strip():
        lines.append(f"  - summary: {tendency_summary.strip()}")
    if action_ranges:
        for action in TENDENCY_PUBLIC_ACTION_NAMES:
            raw = action_ranges.get(action)
            if not isinstance(raw, dict):
                continue
            note = raw.get("note")
            if isinstance(note, str) and note.strip():
                lines.append(f"  - {action}: {note.strip()}")
    return "\n".join(lines) if lines else "  - none saved yet"



class ActivityTimezoneReader(Protocol):
    """Resolve the selected World clock at the caller's original read point."""

    def __call__(self, db: Any, *, character_id: str) -> ZoneInfo: ...
