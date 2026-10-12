"""Only the proved obsolete World topic view may leave the source stock."""
import importlib.util
import json
from pathlib import Path

import pytest

spec=importlib.util.spec_from_file_location('retired_view_changes',Path(__file__).resolve().parents[2]/'scripts/ci/post_refactor_contract_changes.py')
changes=importlib.util.module_from_spec(spec)
spec.loader.exec_module(changes)
VIEW='frontend/src/composition/screens/world-recommendation-tools.tsx'
OWNERS=('frontend/src/composition/screens/world-creator-screen.tsx','backend/app/domains/social/recommendation_router.py',
        'backend/tests/social/test_world_topics_retirement.py','browser-tests/home-activity-memory.spec.ts')
BEFORE='export function WorldRecommendationTools() { return null; }\n'

@pytest.mark.parametrize('tamper',[None,'preimage','present','consumer','other_view','missing_owner'])
def test_retired_view_needs_exact_committed_deletion_and_absent_consumers(tmp_path,tamper):
    commit='a'*40
    item={'source':VIEW,'before_sha256':changes.text_digest(BEFORE)}
    record={'id':'retired-world-topic-view','implementation_commit':commit,'reason':'World preparation retired',
            'review':'exact removal and owner/behavior evidence','source_blobs':{owner:'b'*40 for owner in OWNERS},
            'retired_frontend_product_views':[item]}
    if tamper=='preimage': item['before_sha256']=changes.text_digest('invented')
    if tamper=='other_view': item['source']=VIEW.replace('world-recommendation-tools','other-screen')
    if tamper=='missing_owner': record['source_blobs'].pop(OWNERS[-1])
    if tamper=='present':
        path=tmp_path/VIEW; path.parent.mkdir(parents=True); path.write_text(BEFORE)
    if tamper=='consumer':
        path=tmp_path/OWNERS[0]; path.parent.mkdir(parents=True); path.write_text("import { WorldRecommendationTools } from './world-recommendation-tools';\n")
    manifest=tmp_path/changes.MANIFEST
    manifest.parent.mkdir()
    manifest.write_text(json.dumps({'schema_version':1,'records':[record]}))
    def reader(*args,root):
        if args[0] in ('log','merge-base','ls-tree'): return b''
        if args[0]=='rev-parse': return ('b'*40).encode()
        assert args[0]=='show' and args[1]==commit+'^:'+VIEW
        return BEFORE.encode()
    if tamper is None:
        assert changes.load(tmp_path,reader=reader)==[record]
    else:
        with pytest.raises(ValueError,match='World topic view'):
            changes.load(tmp_path,reader=reader)
