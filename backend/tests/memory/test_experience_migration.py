"""One-time recovery may read originals; serving never does."""
import pytest
from sqlalchemy import delete,select
from memory.test_activity_situation_contract import stack,NOW
from memory.test_activity_situation_application import real_source,receipt,apply
from app.domains.memory.models.items import MemoryItem
from app.domains.memory.models.experience import MemoryExperienceSnapshot
from app.domains.memory.models.activity_situation import MemorySituationManifest
from app.domains.memory.repository.experience import read_snapshot
from app.runtime.persistence.experience_migration import migrate


@pytest.mark.parametrize('changed',[False,True])
def test_legacy_source_recovered_only_with_exact_original_digest_and_old_hashes_preserved(stack,changed):
    db,scope,setting,memory=stack
    post=real_source(db,scope);original=post.body
    row=receipt(db,scope,post);apply(db,setting,memory)
    item_id=row.applied_item_id
    frozen=db.get(MemorySituationManifest,row.manifest_id)
    identity=(frozen.id,frozen.content_digest,row.content_digest,dict(frozen.payload),dict(row.result))
    db.execute(delete(MemoryExperienceSnapshot));db.commit()
    if changed:post.body='different later source';db.commit()
    counts=migrate(db,now=NOW);db.commit()
    item=db.get(MemoryItem,item_id);snapshot=read_snapshot(db,item)
    assert snapshot.status==('snapshot_unavailable' if changed else 'historical_snapshot'), (snapshot.payload['unavailable_reason'],len(snapshot.payload['sources']))
    assert snapshot.payload['sources'][0]['text']==(None if changed else original)
    assert counts[snapshot.status]==1
    frozen=db.get(MemorySituationManifest,row.manifest_id)
    assert (frozen.id,frozen.content_digest,row.content_digest,dict(frozen.payload),dict(row.result))==identity
    digest=snapshot.content_digest
    repeated=migrate(db,now=NOW);db.commit()
    assert repeated['existing']==1
    assert db.get(MemoryExperienceSnapshot,item_id).content_digest==digest
    from app.runtime.persistence.experience_report import audit
    report=audit(db)
    assert report['valid'],report
    assert report['counts']['memories']==1
    assert report['snapshot_json_bytes']>0


def test_interrupted_migration_rolls_back_and_resumes(stack):
    db,scope,setting,memory=stack
    post=real_source(db,scope);row=receipt(db,scope,post);apply(db,setting,memory)
    identifier=row.applied_item_id
    db.execute(delete(MemoryExperienceSnapshot));db.commit()
    migrate(db,now=NOW);db.rollback()
    assert db.get(MemoryExperienceSnapshot,identifier) is None
    migrate(db,now=NOW);db.commit()
    assert db.get(MemoryExperienceSnapshot,identifier).status=='historical_snapshot'
