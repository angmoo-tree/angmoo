"""Read-only persona/state inputs already held by resident execution."""

from typing import Protocol

from app.domains.routines.contracts.planning_context import ResidentPlanningContext
from app.domains.routines.contracts.prompt_context import (
    CharacterPromptView,
    StatePromptView,
)


class ResidentPersonaView(CharacterPromptView, Protocol):
    one_liner: str
    personality: str
    worldview: str
    topic_preferences: str
    safety_rules: str


class ResidentPromptContext(ResidentPlanningContext, Protocol):
    character: ResidentPersonaView
    state: StatePromptView | None
