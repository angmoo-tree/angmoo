"""Owner detail from the saved experience, never current source contents."""
from datetime import datetime
from app.domains.memory.contracts.inspector import SituationDetailMaterial, MemoryEvidenceRead, MemoryEvidenceAvailability
from app.domains.memory.contracts.provenance import MemorySourceTypeV1
from app.domains.memory.models.items import MemoryItem
from app.domains.memory.repository.access_batch import prepare_access
from app.domains.memory.repository.experience import accessible, read_snapshot
from app.domains.memory.repository.episode_packets import SqlAlchemyEpisodePackets
from app.domains.memory.policies.episode_packets import bounded_episode_packets
from app.domains.memory.policies.episode_provider_view import episode_provider_view
from app.runtime.memory.episode_inspector import public_episode_packet


def situation_detail(db, scope, item_id, now, *, validation=None, reader=None):
    item=db.get(MemoryItem,item_id,populate_existing=True)
    if item is None or (item.owner_id,item.world_id,item.subject_world_character_id)!=(
            scope.owner_id,scope.world_id,scope.subject_world_character_id):
        return SituationDetailMaterial((),None)
    validation=prepare_access(db,(item,),now,validation=validation)
    if not accessible(db,scope,item,now,validation=validation,require_enabled=False):
        return SituationDetailMaterial((),None)
    snapshot=read_snapshot(db,item,validation=validation)
    evidence=[]
    for source in ([] if snapshot is None else snapshot.payload['sources'])[:50]:
        try:kind=MemorySourceTypeV1(source['source_type'])
        except ValueError:continue
        original=source.get('text')
        # Historical references are not a grant to navigate a deleted/live post.
        # No current-source existence probe is needed for this detail card.
        evidence.append(MemoryEvidenceRead(kind,
            datetime.fromisoformat(source['occurred_at']) if source.get('occurred_at') else item.valid_from,
            MemoryEvidenceAvailability.AVAILABLE if original is not None else MemoryEvidenceAvailability.UNAVAILABLE,
            original[:500] if original is not None else None,
            source.get('author_id'),None,source.get('counterpart_id'),item.thread_id,None))
    packets=SqlAlchemyEpisodePackets(db,detail_reader=reader).read(scope=scope,item_ids=(item_id,),
        now=now,require_enabled=False,validation=validation)
    view=bounded_episode_packets(episode_provider_view(packets))
    return SituationDetailMaterial(tuple(evidence),public_episode_packet(view.packets[0]) if view.packets else None)
