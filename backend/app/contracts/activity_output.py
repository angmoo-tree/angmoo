"""Separate visible fictional content from optional activity self-expression."""

from __future__ import annotations

import json

from app.contracts.activity_thought import ActivityThought, parse_activity_thought


def activity_output_schema() -> dict:
    return {
        "type": "object",
        "properties": {"text": {"type": "string"}, "thought": {"type": "string"}},
        "required": ["text", "thought"],
        "additionalProperties": False,
    }


def parse_activity_output(raw: str, parsed: object = None) -> tuple[str, ActivityThought]:
    """Never regenerate a usable body because its optional thought is absent/bad.

    An invalid envelope/body is an output failure, not visible fallback JSON.
    Thought is product data, not provider reasoning metadata.
    """
    if not isinstance(parsed, dict):
        try:
            parsed = json.loads(raw)
        except (ValueError, TypeError) as exc:
            raise ValueError("activity_output_invalid_json") from exc
    text = parsed.get("text") if isinstance(parsed, dict) else None
    if not isinstance(text, str) or not text.strip() or len(text.strip()) > 16_000:
        raise ValueError("activity_output_invalid_body")
    return text.strip(), parse_activity_thought(parsed.get("thought"))
