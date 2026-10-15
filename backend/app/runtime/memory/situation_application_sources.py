"""Compose batched proof validation only at the situation application boundary."""
from app.domains.memory.models.items import MemoryItem
from app.runtime.memory.situation_sources import SituationSources


class PreparedSituationSources(SituationSources):
    def prepare_validation(self, context, *, validation):
        from sqlalchemy import select
        from app.domains.memory.repository.access_batch import prepare_access
        from app.runtime.memory.episode_details import RuntimeEpisodeDetailReader
        validation.check_context(self.session, validation.now)
        prior_ids = {source.source_id for source in (*context.sources, *context.result_sources)
            if source.source_type == "MEMORY_ITEM"}
        priors = list(self.session.scalars(select(MemoryItem).where(MemoryItem.id.in_(prior_ids))
            .execution_options(populate_existing=True))) if prior_ids else []
        reader = RuntimeEpisodeDetailReader(self.session)
        prepare_access(self.session, priors, validation.now, reader=reader, validation=validation)
        reader.prepare_situation_sources((context,), validation=validation)
