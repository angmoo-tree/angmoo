"""Real PostgreSQL flat snapshot reads retain current memory deletion rights."""
import json
from copy import deepcopy

from sqlalchemy import event, select
from sqlalchemy.orm import Session

from postgresql.test_activity_transactions import store
from memory.test_p8_l_o_memory_consolidation import _stack
from memory.test_lineage_validation_cost import lineage, NOW
from app.domains.memory.models.activity_configuration import MemoryEpisodeRestriction
from app.domains.memory.models.activity_situation import MemoryActivitySituationInfo, MemorySituationReceipt, MemorySituationManifest
from app.domains.memory.models.items import MemoryItem
from app.domains.memory.repository.access_batch import prepare_access
from app.domains.memory.repository.episode_privacy import currently_accessible


def _lineage(engine):
    db=Session(engine)
    scope,setting,_,memory,*_=_stack(db)
    return lineage((db,scope,setting,memory),levels=8)


def _compare(db,roots,monkeypatch):
    counts=[]
    def count(*_):counts.append(1)
    event.listen(db.get_bind(),'before_cursor_execute',count)
    try:
        batched=prepare_access(db,roots,NOW)
        batch_count=len(counts);counts.clear()
        with monkeypatch.context() as patch:
            def forbidden(*args,**kwargs):raise AssertionError('runtime ancestor traversal')
            patch.setattr('app.domains.memory.repository.postgresql_ancestry.reachable_ids',forbidden)
            iterative=prepare_access(db,roots,NOW)
        original_count=len(counts)
    finally:
        event.remove(db.get_bind(),'before_cursor_execute',count)
    assert batched.prepared_items == iterative.prepared_items
    assert batched.rows.keys() == iterative.rows.keys()
    assert batched.collections == iterative.collections
    return batched,iterative,batch_count,original_count


def test_flat_batch_has_bounded_roundtrips_without_current_source_reads(store,monkeypatch):
    db,scope,post,nodes,reader=_lineage(store[0])
    try:
        first,second,batch,original=_compare(db,nodes[-2:],monkeypatch)
        assert batch == original and batch <= 8
        assert currently_accessible(db,reader,scope,nodes[-1],NOW,validation=first)
        assert currently_accessible(db,reader,scope,nodes[-1],NOW,validation=second)
        post.report_hidden_at=NOW
        db.commit()
        fresh,_,_,_=_compare(db,nodes[-2:],monkeypatch)
        assert currently_accessible(db,reader,scope,nodes[-1],NOW,validation=fresh)
    finally:db.close()


def test_legacy_prior_edits_do_not_replace_flat_dependencies_but_explicit_delete_revokes(store,monkeypatch):
    db,scope,post,nodes,reader=_lineage(store[0])
    try:
        for raw in (json.dumps([{'id':nodes[-1].id,'version':1}]),
                    json.dumps([{'id':'missing-prior','version':1}]),
                    'not-json','{"invalid":"shape"}'):
            row=db.get(MemoryEpisodeRestriction,nodes[0].id)
            row.priors_json=raw;db.flush()
            first,second,_,_=_compare(db,nodes[-2:],monkeypatch)
            assert currently_accessible(db,reader,scope,nodes[-1],NOW,validation=first)
            assert currently_accessible(db,reader,scope,nodes[-1],NOW,validation=second)
        from app.domains.memory.repository.experience import tombstone,read_snapshot
        tombstone(db,nodes[0],read_snapshot(db,nodes[0]).scope_setting_id,now=NOW)
        db.commit()
        fresh=prepare_access(db,nodes[-2:],NOW)
        assert not currently_accessible(db,reader,scope,nodes[-1],NOW,validation=fresh)
    finally:db.close()


def test_legacy_manifest_edges_cannot_reconstruct_a_saved_snapshot(store,monkeypatch):
    db,scope,post,nodes,reader=_lineage(store[0])
    try:
        info=db.scalar(select(MemoryActivitySituationInfo))
        root=db.get(MemoryItem,info.memory_item_id)
        receipt=db.get(MemorySituationReceipt,info.receipt_sequence)
        manifest=db.get(MemorySituationManifest,receipt.manifest_id)
        payload=deepcopy(manifest.payload)
        payload['sources']=[{'source_type':'MEMORY_ITEM','source_id':nodes[-1].id},
                            {'source_type':'MEMORY_ITEM','source_id':'missing-direct'},
                            {'source_type':'MEMORY_ITEM','source_id':123}]
        manifest.payload=payload
        # After migration, these legacy relationships cannot replace the
        # independent snapshot or expand a runtime traversal.
        db.add(MemoryEpisodeRestriction(memory_item_id=root.id,mode='public',thread_id=None,
               sources_json='[]',priors_json='[{"id":"ignored-fallback","version":1}]'))
        root.superseded_by_id=nodes[-1].id
        root.status='superseded'
        db.flush()
        first,second,_,_=_compare(db,(nodes[-1],),monkeypatch)
        assert first.prepared_items == {nodes[-1].id}
        assert 'missing-direct' not in first.prepared_items and 'ignored-fallback' not in first.prepared_items
        assert currently_accessible(db,reader,scope,nodes[-1],NOW,validation=first)
        assert currently_accessible(db,reader,scope,nodes[-1],NOW,validation=second)
    finally:db.close()
