"""Memoized lineage checks for one synchronous, read-only canonical operation."""
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING

from app.domains.memory.contracts.scope import MemoryScope
if TYPE_CHECKING:
    from app.domains.memory.contracts.activity_situation import DeliveredSourceEntry
    from app.domains.memory.contracts.situation_validation import SituationSourceAccess
    from app.domains.memory.contracts.source_evidence import CanonicalMemoryEvidence


@dataclass
class MemoryAccessValidation:
    # Never keep this object on a Session, reader, runtime or projection. Each
    # operation must see fresh permissions and source rows, even in one Session.
    session: object
    now: datetime
    completed: dict[tuple[MemoryScope, str, int], bool] = field(default_factory=dict)
    # Strong references prevent an expired manifest's identity being reused.
    manifests: dict[int, object] = field(default_factory=dict)
    sources: dict[tuple[int, "DeliveredSourceEntry"], "SituationSourceAccess"] = field(default_factory=dict)
    evidence: dict[tuple[MemoryScope, str, str], "CanonicalMemoryEvidence | None"] = field(default_factory=dict)
    scopes: dict[MemoryScope, bool] = field(default_factory=dict)
    participants: dict[tuple[str, frozenset[str]], frozenset[str]] = field(default_factory=dict)
    blocks: dict[tuple[str, str, str], bool] = field(default_factory=dict)

    def check_context(self, session, now):
        if self.session is not session or self.now != now:
            raise ValueError("memory_access_validation_context_mismatch")
