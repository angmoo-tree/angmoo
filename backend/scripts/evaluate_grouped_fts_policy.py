"""Replay frozen synthetic retrieval with recorded vector ranks; no API calls."""
import argparse
from dataclasses import replace
import json
from pathlib import Path
import sys
from time import monotonic

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.domains.memory.contracts.recall import MemoryRecallSearchQuery, MemoryRecallLexicalPolicy, RecallDocumentKind, MemoryRecallCandidate
from app.domains.memory.contracts.scope import MemoryScope
from app.domains.memory.contracts.hybrid_recall import RankedMemoryCandidate
from app.domains.memory.service.hybrid_recall import reciprocal_rank_fusion
from app.runtime.memory.sqlite_fts5_recall import SqliteMemoryRecallIndex


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fts-db',type=Path,required=True)
    parser.add_argument('--baseline',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--owner',default='quality-owner')
    parser.add_argument('--world',default='quality-world')
    parser.add_argument('--subject',default='quality-midoriya')
    args=parser.parse_args()
    index=SqliteMemoryRecallIndex.reader(args.fts_db)
    baseline=json.loads(args.baseline.read_text(encoding='utf-8'))
    scope=MemoryScope(args.owner,args.world,args.subject)
    output=[]
    for original in baseline:
        query=MemoryRecallSearchQuery(scope,original['query'],(RecallDocumentKind.MEMORY_ITEM,),50,
            korean_spacing_fallback=True,lexical_policy=MemoryRecallLexicalPolicy.GROUP_OR_V1)
        start=monotonic()
        batch=index.search_grouped(query,deadline=start+5)
        fts=tuple(RankedMemoryCandidate(c,int(c.metadata['item_version']),c.metadata['document_content_hash']) for c in batch.candidates)
        # Replay ranks, preserving matching document identity; no semantic claims
        # about new embeddings are made by this evaluator.
        byid={c.candidate.memory_item_id:c for c in fts}
        vector=tuple(byid[mid] if mid in byid else RankedMemoryCandidate(
            MemoryRecallCandidate('memory-item:'+mid,mid,RecallDocumentKind.MEMORY_ITEM,mid,0,''),1,'0'*64)
            for mid in original['ranking']['vector'])
        hybrid=reciprocal_rank_fusion(fts,vector)
        ranks={'fts':[c.candidate.memory_item_id for c in fts],
               'vector':original['ranking']['vector'],
               'hybrid':[c.candidate.memory_item_id for c in hybrid]}
        output.append({'id':original['id'],'query':original['query'],'expected':original['expected'],
            'subset':original['subset'],'split':original['split'],'ranking':ranks,
            'hit10':{a:bool(set(v[:10]) & set(original['expected'])) for a,v in ranks.items()},
            'status':batch.status.value,'reason':batch.reason_code,'stats':batch.stats,'fts_ms':(monotonic()-start)*1000})
    args.out.mkdir(parents=True,exist_ok=True)
    (args.out/'results.json').write_text(json.dumps(output,ensure_ascii=False,indent=2),encoding='utf-8')
    summary={'n':len(output),'hit10':{a:sum(r['hit10'][a] for r in output) for a in ('fts','vector','hybrid')},
        'vector_regressions':[r['id'] for r,o in zip(output,baseline) if o['hit_at_10']['vector'] and not r['hit10']['hybrid']],
        'legacy_lexical_regressions':[r['id'] for r,o in zip(output,baseline) if o['subset']=='lexical' and o['hit_at_10']['fts'] and not r['hit10']['fts']],
        'ai_calls':0,'vector_source':'recorded ranks; native behavior separately tested'}
    summary['metrics']={axis:{
        'recall10':sum(len(set(r['ranking'][axis][:10]) & set(r['expected']))/len(r['expected']) for r in output)/len(output),
        'mrr10':sum(next((1/(n+1) for n,item in enumerate(r['ranking'][axis][:10]) if item in r['expected']),0) for r in output)/len(output)
    } for axis in ('fts','vector','hybrid')}
    (args.out/'summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    print(json.dumps(summary))


if __name__=='__main__': main()
