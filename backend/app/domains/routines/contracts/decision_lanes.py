"""Existing client and credential values used by the two decision requests."""

from typing import Any, Protocol


class DecisionClient(Protocol):
    async def run_agent(self, **kwargs: Any) -> dict[str, Any]: ...


class DecisionCredential(Protocol):
    provider: str
    model: str
    auth_profile_id: str
