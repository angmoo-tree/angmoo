from sqlalchemy import select
from memory.test_episode_apply import preparation
from memory.test_p8_l_g_memory_write_lifecycle import memory_session, NOW
from app.domains.memory.contracts.episode import EpisodeSelection, EpisodeProposal
from app.domains.memory.models.items import MemoryItem
from app.runtime.relationships.review_memories import episode_lineage_ids


def test_episode_correction_chain_retains_eligibility_without_rewriting_episode(memory_session):
    db=memory_session
    apply,setting,bundle,values=preparation(db)
    ids=apply.apply(bundle=bundle,selection=EpisodeSelection((EpisodeProposal('원래 사건',('S1',)),),('S2',)),
        setting=setting,now=NOW,revalidate=lambda _:values,job_fence=lambda:None)
    previous=db.get(MemoryItem,ids[0])
    for index in range(2):
        replacement=MemoryItem(id=f'corrected-{index}',owner_id=previous.owner_id,world_id=previous.world_id,
            subject_world_character_id=previous.subject_world_character_id,memory_kind=previous.memory_kind,
            summary='정정된 경험',confidence=1,salience=1)
        db.add(replacement)
        db.flush()
        previous.status="superseded"
        previous.superseded_by_id=replacement.id
        previous=replacement
    db.flush()
    lineage=episode_lineage_ids(bundle.scope)
    assert set(db.scalars(select(lineage.c.id))) == {ids[0],'corrected-0','corrected-1'}
