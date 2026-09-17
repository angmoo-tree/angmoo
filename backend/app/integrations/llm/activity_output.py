"""Compatibility import for activity output contracts; new consumers use contracts."""

from app.contracts.activity_thought_output import (
    LEGACY_SELF_VIEW_FIELDS, extract_activity_thought, resident_thought_payload,
    resident_thought_schema, thought_response_schema, without_legacy_self_view_prompt,
)
