"""Connect actual Memory interpretation to the existing foreign row readers."""

from app.domains.memory.service.source_evidence import (
    SqlAlchemyMemorySourceEvidenceReader,
)
from app.runtime.memory import source_queries


def source_evidence_reader(session):
    from app.runtime.memory.situation_sources import SituationSources
    def prepare(contexts, *, validation):
        from app.runtime.memory.situation_source_batch import prepare_sources
        from app.runtime.memory.source_batch_queries import _SourceQueries
        prepare_sources(session, contexts, validation=validation, queries_factory=_SourceQueries)
    reader = SqlAlchemyMemorySourceEvidenceReader(session, queries=source_queries,
        situation_validator=lambda manifest, source, **values:
            situations.validate(manifest, source, **values), situation_preparer=prepare)
    situations = SituationSources(session, reader=reader)
    return reader
