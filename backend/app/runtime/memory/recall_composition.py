"""Bind canonical read implementations to concrete same-Session source readers."""
from datetime import UTC, datetime
from app.domains.memory.repository.recall import SqlAlchemyCanonicalRecallRepository, SqlAlchemyMemoryRecallDocumentSource
from app.runtime.memory.recall_queries import read_character_summary_rows
from app.runtime.memory.source_composition import source_evidence_reader as SqlAlchemyMemorySourceEvidenceReader


def canonical_recall_repository(session_factory):
    return SqlAlchemyCanonicalRecallRepository(
        session_factory,
        source_reader_factory=SqlAlchemyMemorySourceEvidenceReader,
        character_rows=read_character_summary_rows,
    )


def recall_document_source(session_factory, *, now_factory=lambda: datetime.now(UTC)):
    return SqlAlchemyMemoryRecallDocumentSource(
        session_factory,
        source_reader_factory=SqlAlchemyMemorySourceEvidenceReader,
        now_factory=now_factory,
    )
