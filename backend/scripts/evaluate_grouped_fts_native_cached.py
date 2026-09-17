"""Read an explicit synthetic Chat fixture with a matching cached query vector.

No credentials, installed database discovery or provider calls. This verifies
native fusion and canonical hydration, not a new CRG answer or embedding quality.
"""
import argparse
import asyncio
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import sys
from time import monotonic

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.domains.memory.contracts.embedding import EMBEDDING_PROFILE, embedding_text
from app.domains.memory.contracts.hybrid_recall import HybridRecallRequest
from app.domains.memory.contracts.recall import RecallDocumentKind
from app.domains.memory.contracts.scope import MemoryScope
from app.domains.memory.repository.hybrid_recall import SqlAlchemyHybridCanonicalReader
from app.domains.memory.service.hybrid_recall import HybridRecallService
from app.providers.contracts import MeasuredEmbeddingResponse, ProviderUsage
from app.runtime.memory.fts_worker import FtsReadWorkers
from app.runtime.memory.hybrid_axes import FtsHybridAxis, VectorHybridAxis
from app.runtime.memory.recall_composition import canonical_recall_repository
from app.runtime.memory.source_composition import source_evidence_reader
from app.runtime.memory.vector_worker import VectorReadWorkers
from app.runtime.persistence.model_registration import register_models


async def main(args):
    register_models()
    cached=json.loads(args.embedding.read_text(encoding='utf-8'))
    expected=hashlib.sha256(embedding_text(args.query,query=True).encode()).hexdigest()
    if cached['text_sha256'] != expected or cached['profile'] != EMBEDDING_PROFILE:
        raise ValueError('cached_query_identity_mismatch')
    scope=MemoryScope('p-owner','p-world','p-responding')
    engine=create_engine('sqlite:///'+args.canonical.resolve().as_posix())
    factory=sessionmaker(bind=engine)
    canonical=SqlAlchemyHybridCanonicalReader(factory,source_reader_factory=source_evidence_reader,
        canonical=canonical_recall_repository(factory))
    fts=FtsReadWorkers(database_path=args.fts)
    vector=VectorReadWorkers(database_path=args.vector,extension_path=args.extension,
        extension_sha256=hashlib.sha256(args.extension.read_bytes()).hexdigest())
    mapping=json.loads(args.item_map.read_text(encoding='utf-8'))
    request=HybridRecallRequest('cached-native','cached-call','a'*64,scope,args.query,EMBEDDING_PROFILE,
        (RecallDocumentKind.MEMORY_ITEM,RecallDocumentKind.OWNER_MEMORY_REQUEST))
    results=[]
    try:
        for mode in ('present','disabled','unavailable'):
            class CachedEmbedder:
                async def query(self, request, *, deadline):
                    if mode=='disabled': return None
                    if mode=='unavailable': raise RuntimeError('synthetic_axis_unavailable')
                    return MeasuredEmbeddingResponse(tuple(cached['vector']),ProviderUsage(),0)
            service=HybridRecallService(fts=FtsHybridAxis(fts,lexical_policy='group_or_v1'),
                vector=VectorHybridAxis(vector,CachedEmbedder()),canonical=canonical)
            result=await service.execute(request,deadline=monotonic()+15)
            found=any(r.memory_item_id==mapping[args.expected] for r in result.records)
            assert found, (mode,'expected_memory_not_hydrated')
            assert not fts.active_processes and not vector.active_processes
            results.append({'mode':mode,'status':result.status.value,'axes':[asdict(a) for a in result.axes],
                'expected_hydrated':found,'source_receipts':len(result.sources),'remaining_workers':0})
    finally:
        engine.dispose()
    args.out.write_text(json.dumps({'query':args.query,'results':results,'ai_calls':0,
        'limitation':'Cached matching q47 query, not the original e10 Supervisor search; no new CRG execution'},indent=2),encoding='utf-8')
    print(json.dumps(results))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('canonical','fts','vector','extension','embedding','item-map','out'):
        parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--query',required=True)
    parser.add_argument('--expected',required=True)
    asyncio.run(main(parser.parse_args()))
