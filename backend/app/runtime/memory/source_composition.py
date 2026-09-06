"""Connect actual Memory interpretation to the existing foreign row readers."""

from app.domains.memory.service.source_evidence import (
    SqlAlchemyMemorySourceEvidenceReader,
)
from app.runtime.memory import source_queries


def source_evidence_reader(session):
    return SqlAlchemyMemorySourceEvidenceReader(session, queries=source_queries)
