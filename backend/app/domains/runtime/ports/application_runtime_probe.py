from __future__ import annotations

from typing import Protocol

from app.domains.runtime.domain.installation_state import ApplicationRuntimeStatus


class ApplicationRuntimeProbe(Protocol):
    """Reads application facts without exposing host or container internals."""

    def read_status(self) -> ApplicationRuntimeStatus: ...
