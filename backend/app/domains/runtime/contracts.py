"""Runtime-neutral failure contracts shared with HTTP and caller workflows.

Execution/adapters/lease policy stay outside this contract.
"""
from typing import Any


class ResidentRuntimeError(Exception):
    def __init__(
        self, message: str, *, diagnostics: dict[str, Any] | None = None
    ) -> None:
        super().__init__(message)
        self.diagnostics = diagnostics or {}


class ResidentRuntimeAuthError(ResidentRuntimeError):
    pass


class ResidentRuntimeUnavailableError(ResidentRuntimeError):
    pass


class ResidentRuntimeRegistrationError(ResidentRuntimeError):
    pass


class AgentRunServiceError(Exception):
    pass


class AgentSlotUnavailableError(AgentRunServiceError):
    pass

# Historical API names identify the exact same runtime-neutral classes.
OpenClawGatewayError = ResidentRuntimeError
OpenClawGatewayAuthError = ResidentRuntimeAuthError
