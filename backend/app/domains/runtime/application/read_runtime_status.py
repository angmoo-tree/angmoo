from __future__ import annotations

from app.domains.runtime.contracts.status import ApplicationRuntimeStatus
from app.domains.runtime.contracts.status_reader import ApplicationRuntimeProbe


class ReadApplicationRuntimeStatus:
    def __init__(self, probe: ApplicationRuntimeProbe) -> None:
        self._probe = probe

    def execute(self) -> ApplicationRuntimeStatus:
        return self._probe.read_status()
