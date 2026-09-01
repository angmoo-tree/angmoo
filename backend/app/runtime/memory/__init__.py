"""Runtime composition for canonical Memory evidence and private recall."""

from app.runtime.memory.recall_projection import (
    EmbeddedMemoryRecallProjection,
    MemoryRecallProjectionState,
)
from app.runtime.memory.sqlalchemy_recall import (
    SqlAlchemyCanonicalRecallRepository,
    SqlAlchemyMemoryRecallDocumentSource,
)
from app.runtime.memory.sqlalchemy_source_reader import (
    SqlAlchemyMemorySourceEvidenceReader,
)
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
