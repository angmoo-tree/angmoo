import json
from pathlib import Path
from time import monotonic
from memory.test_korean_memory_recall_quality import document, build_index
from memory.test_grouped_fts_index import query


def test_frozen_development_and_heldout(tmp_path):
    rows=json.loads((Path(__file__).parent/'fixtures/grouped_fts_frozen.json').read_text(encoding='utf-8'))
    docs={r['expected']:document(r['expected'],r['text']) for r in rows}
    index=build_index(tmp_path,list(docs.values()))
    for split in ('development','heldout'):
        selected=[r for r in rows if r['split']==split]
        hits=0
        for row in selected:
            result=index.search_grouped(query(row['query']),deadline=monotonic()+5)
            hits+=row['expected'] in [c.memory_item_id for c in result.candidates[:10]]
        assert hits/len(selected)>=.9
