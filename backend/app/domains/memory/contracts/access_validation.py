"""Memoized lineage checks for one synchronous, read-only canonical operation."""
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING

from app.domains.memory.contracts.scope import MemoryScope
if TYPE_CHECKING:
    from app.domains.memory.contracts.activity_situation import DeliveredSourceEntry
    from app.domains.memory.contracts.situation_validation import SituationSourceAccess
    from app.domains.memory.contracts.source_evidence import CanonicalMemoryEvidence


@dataclass(frozen=True, slots=True)
class MemoryAccessMetrics:
    unique_nodes: int
    memo_hits: int


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
    rows: dict[tuple[type, object], object | None] = field(default_factory=dict)
    collections: dict[tuple[str, object], tuple] = field(default_factory=dict)
    restored: dict[int, object] = field(default_factory=dict)
    origins: dict[str, object | None] = field(default_factory=dict)
    runtime_sources: object | None = None
    memo_hits: int = 0

    def metrics(self):
        # Counts only completed privacy-policy nodes, not SQL rows or sources.
        return MemoryAccessMetrics(len(self.completed), self.memo_hits)

    def get(self, model, identifier):
        key = model, identifier
        if key not in self.rows:
            self.rows[key] = self.session.get(model, identifier, populate_existing=True)
        return self.rows[key]

    def check_context(self, session, now):
        if self.session is not session or self.now != now:
            raise ValueError("memory_access_validation_context_mismatch")
