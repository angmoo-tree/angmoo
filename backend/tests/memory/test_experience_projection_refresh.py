"""Rebuild derived authorization without paying to re-embed unchanged text."""
import asyncio
from sqlalchemy import text
from app.runtime.memory.vector_projection import MemoryVectorProjection
from app.runtime.memory.experience_projection import refresh_policy
from app.providers.contracts import MeasuredEmbeddingResponse,ProviderUsage
from memory.test_p8_l_h_canonical_recall import runtime_factory
from memory.test_vector_projection_lifecycle import setup_projection_scope
from memory.projection_fixture import index,A


def test_policy_refresh_is_atomic_replayable_and_reuses_saved_vector(runtime_factory,index,monkeypatch):
    item_id,_=setup_projection_scope(runtime_factory,monkeypatch)
    class Provider:
        calls=0
        async def embed_measured(self,request,*,timeout_seconds):
            self.calls+=1
            return MeasuredEmbeddingResponse(tuple(A),ProviderUsage(),1)
    provider=Provider();projection=MemoryVectorProjection(runtime_factory,index,provider=provider)
    assert asyncio.run(projection.sync_item(item_id))=='indexed'
    original=index.identity('memory-item:'+item_id)
    assert refresh_policy(projection) is True
    assert refresh_policy(projection) is False
    with runtime_factory() as db:
        assert db.execute(text('SELECT count(*) FROM memory_vector_work WHERE generation=:g AND item_id=:id'),
            {'g':projection.generation,'id':item_id}).scalar_one()==1
    assert asyncio.run(projection.sync_item(item_id))=='current'
    assert provider.calls==1
    assert index.identity('memory-item:'+item_id)==original
