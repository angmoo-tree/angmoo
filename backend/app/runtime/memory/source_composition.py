"""Connect actual Memory interpretation to the existing foreign row readers."""

from app.domains.memory.service.source_evidence import (
    SqlAlchemyMemorySourceEvidenceReader,
)
from app.runtime.memory import source_queries


def source_evidence_reader(session):
    from app.runtime.memory.situation_sources import SituationSources
    reader = SqlAlchemyMemorySourceEvidenceReader(session, queries=source_queries,
        situation_validator=lambda manifest, source, **values:
            SituationSources(session, reader=reader).validate(manifest, source, **values))
    return reader
