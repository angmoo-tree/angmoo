"""Runtime composition for canonical Memory evidence and private recall."""

from app.runtime.memory.recall_projection import (
    EmbeddedMemoryRecallProjection,
    MemoryRecallProjectionState,
)
from app.runtime.memory.recall_composition import canonical_recall_repository as SqlAlchemyCanonicalRecallRepository, recall_document_source as SqlAlchemyMemoryRecallDocumentSource
from app.runtime.memory.source_composition import source_evidence_reader as SqlAlchemyMemorySourceEvidenceReader
from app.runtime.memory.sqlite_fts5_recall import (
    MemoryRecallIndexError,
    MemoryRecallIndexSchemaError,
    MemoryRecallIndexSettings,
    SqliteMemoryRecallIndex,
)

__all__ = [
    "EmbeddedMemoryRecallProjection",
    "MemoryRecallIndexError",
    "MemoryRecallIndexSchemaError",
    "MemoryRecallIndexSettings",
    "MemoryRecallProjectionState",
    "SqlAlchemyCanonicalRecallRepository",
    "SqlAlchemyMemoryRecallDocumentSource",
    "SqlAlchemyMemorySourceEvidenceReader",
    "SqliteMemoryRecallIndex",
]
