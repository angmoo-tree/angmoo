"""Current scope and private-thread rights, without original-source contents."""
from typing import Protocol
from app.domains.memory.contracts.scope import MemoryScope


class MemoryExperienceAccess(Protocol):
    def scope_present(self, scope: MemoryScope) -> bool: ...
    def thread_accessible(self, scope: MemoryScope, thread_id: str, *, validation) -> bool: ...
