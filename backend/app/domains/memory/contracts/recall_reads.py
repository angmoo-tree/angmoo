"""Read-only collaborators used inside each canonical Memory read Session."""
from __future__ import annotations
from collections.abc import Callable
from datetime import datetime
from typing import Protocol
from sqlalchemy.orm import Session
from app.domains.memory.contracts.recall import CanonicalRecallQuery
from app.domains.memory.contracts.source_evidence import MemorySourceEvidenceReaderPort


class SummaryWorldCharacter(Protocol):
    id: str
    updated_at: datetime


class SummaryCharacter(Protocol):
    id: str
    name: str
    one_liner: str | None
    persona_summary: str | None


SourceReaderFactory = Callable[[Session], MemorySourceEvidenceReaderPort]
CharacterRowsReader = Callable[
    [Session, CanonicalRecallQuery, tuple[str, ...]],
    tuple[list[tuple[SummaryWorldCharacter, SummaryCharacter]], set[str]],
]
