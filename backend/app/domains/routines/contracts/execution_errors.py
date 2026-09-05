"""Execution failures that other domain HTTP workflows can handle."""

from app.domains.routines.exceptions import (
    AgentRunServiceError,
    AgentSlotUnavailableError,
)

__all__ = ["AgentRunServiceError", "AgentSlotUnavailableError"]
