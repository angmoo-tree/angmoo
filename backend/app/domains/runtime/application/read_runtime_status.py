from __future__ import annotations

from app.domains.runtime.domain.installation_state import ApplicationRuntimeStatus
from app.domains.runtime.ports.application_runtime_probe import ApplicationRuntimeProbe


class ReadApplicationRuntimeStatus:
    def __init__(self, probe: ApplicationRuntimeProbe) -> None:
        self._probe = probe

    def execute(self) -> ApplicationRuntimeStatus:
        return self._probe.read_status()
