"""Optional semantic-recall boundary.

ER2 deliberately defines only the domain-facing port.  No vector extension,
embedding model, image, or default runtime adapter is selected here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping, Protocol, runtime_checkable


@dataclass(frozen=True)
class VectorRecallQuery:
    world_id: str
    text: str
    limit: int = 20
    character_id: str | None = None
    counterparty_id: str | None = None
    kinds: tuple[str, ...] = ()


@dataclass(frozen=True)
class VectorRecallHit:
    document_id: str
    score: float
    metadata: Mapping[str, str] = field(default_factory=dict)


@runtime_checkable
class VectorRecallPort(Protocol):
    def recall(self, query: VectorRecallQuery) -> tuple[VectorRecallHit, ...]: ...


__all__ = ["VectorRecallHit", "VectorRecallPort", "VectorRecallQuery"]
