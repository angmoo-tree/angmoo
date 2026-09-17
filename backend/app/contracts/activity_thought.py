"""Short character self-expression, distinct from provider reasoning tokens.

This shared value performs no persistence or model calls. Each activity domain
owns attribution to its successful result and source revision.
"""

from dataclasses import dataclass
from typing import Literal

THOUGHT_VERSION = "activity-thought.v1"
MAX_THOUGHT_CHARACTERS = 280


@dataclass(frozen=True, slots=True)
class ActivityThought:
    text: str | None = None
    status: Literal["recorded", "missing", "invalid"] = "missing"
    truncated: bool = False

    def __post_init__(self) -> None:
        if self.status == "recorded":
            if not isinstance(self.text, str) or not self.text.strip() or len(self.text) > MAX_THOUGHT_CHARACTERS:
                raise ValueError("activity_thought_text_invalid")
        elif self.status not in {"missing", "invalid"} or self.text is not None or self.truncated:
            raise ValueError("activity_thought_state_invalid")


def parse_activity_thought(value: object) -> ActivityThought:
    """Keep a valid body even when optional self-expression is absent or bad."""
    if value is None:
        return ActivityThought()
    if not isinstance(value, str):
        return ActivityThought(status="invalid")
    value = value.strip()
    if not value:
        return ActivityThought()
    return ActivityThought(
        text=value[:MAX_THOUGHT_CHARACTERS],
        status="recorded",
        truncated=len(value) > MAX_THOUGHT_CHARACTERS,
    )


THOUGHT_PROMPT = """Alongside the visible body, return thought: a short fictional
character self-expression explaining how you received this situation and why
you chose this action. Put the main reason first, preferably within 280 Unicode
characters. Emotion may appear naturally; do not force it. This is character
product data, not private model reasoning, tool selection or chain of thought.
Distinguish personal impressions from facts about others. Do not fabricate an
earlier experience to justify this action. Do not repeat motivation/emotion
classification fields. Never put this field in the visible body."""
