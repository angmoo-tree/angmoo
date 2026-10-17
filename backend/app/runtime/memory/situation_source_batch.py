"""Runtime-owned foreign facts, scoped to a single canonical read operation."""
from app.domains.memory.repository.access_batch import indexed
from app.domains.chat.models import MessageThread, MessageMessage
from app.domains.social.models.posts import Post
from app.domains.relationships.models.social import RelationshipState, ActivityProposal, SocialEvent
from app.domains.media.models import MediaAsset, ImageInterpretation
from app.domains.routines.models.plans import DailyActivityPlan, DailyActivityPlanItem
from app.domains.memory.contracts.provenance import MemorySourceTypeV1
from app.domains.memory.service.source_evidence import SqlAlchemyMemorySourceEvidenceReader
from app.runtime.memory.situation_sources import SituationSources


def prepare_sources(session, contexts, *, validation, queries_factory):
    entries = tuple(entry for context in contexts for entry in (*context.sources, *context.result_sources))
    identities = tuple(dict.fromkeys((entry.source_type, entry.source_id) for entry in entries))
    queries = validation.runtime_queries
    if queries is None:
        queries = validation.runtime_queries = queries_factory(session, ())
    queries.prepare(session, identities, (context.snapshot.scope for context in contexts))
    for model, values in ((Post, queries.posts), (MessageMessage, queries.messages), (MessageThread, queries.threads)):
        validation.rows.update(((model, identifier), row) for identifier, row in values.items())
    mapping = {"RELATIONSHIP": RelationshipState, "ACTIVITY_PROPOSAL": ActivityProposal,
        "SOCIAL_EVENT": SocialEvent, "IMAGE_ASSET": MediaAsset, "IMAGE_INTERPRETATION": ImageInterpretation,
        "ROUTINE_ACTIVITY": DailyActivityPlanItem}
    for kind, model in mapping.items():
        indexed(validation, model, model.id, (identifier for source_type, identifier in identities if source_type == kind))
    indexed(validation, MessageThread, MessageThread.id, (entry.thread_id for entry in entries if entry.thread_id))
    interpretations = [row for (model, _), row in tuple(validation.rows.items()) if model is ImageInterpretation and row is not None]
    indexed(validation, MediaAsset, MediaAsset.id, (row.asset_id for row in interpretations))
    routine = [row for (model, _), row in tuple(validation.rows.items()) if model is DailyActivityPlanItem and row is not None]
    indexed(validation, DailyActivityPlan, DailyActivityPlan.id, (row.plan_id for row in routine))
    reader = SqlAlchemyMemorySourceEvidenceReader(session, queries=queries)
    validation.runtime_sources = SituationSources(session, reader=reader)
    # Evidence access decisions remain proof-specific. Only raw canonical facts
    # are shared across manifests, with the same fresh Session and timestamp.
    for context in contexts:
        scope = context.snapshot.scope
        for entry in (*context.sources, *context.result_sources):
            try:
                kind = MemorySourceTypeV1(entry.source_type)
            except ValueError:
                continue
            key = scope, kind.value, entry.source_id
            if key not in validation.evidence:
                validation.evidence[key] = reader.read_evidence(scope=scope, source_type=kind, source_id=entry.source_id)
