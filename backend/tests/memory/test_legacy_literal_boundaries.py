"""Legacy strict and modern grouped queries share literal identifier boundaries."""
from dataclasses import replace
from time import monotonic
import pytest

from memory.test_grouped_fts_index import document, build_index, query
from app.domains.memory.contracts.recall import MemoryRecallLexicalPolicy

@pytest.mark.parametrize('text,positive,negative', [
    ('art.', 'We discussed art.', 'A party began.'),
    ('coffee!', 'coffee!', 'coffeeshop'),
    ('A-17', 'A-17 was cancelled.', 'A-170 was accepted.'),
    ('v1.2', 'v1.2.', 'v1.20'),
    ('café', 'Cafe\u0301!', 'caféteria'),
    ('قهوة', 'قهوة', 'القهويات'),
    ('می\u200cروم', 'می\u200cروم', 'می\u200cرومند'),
    ('축제', '축제에서 친구를 만났다.', '책을 읽었다.'),
    ('図書館', '図書館で会った', '海辺で会った'),
])
def test_legacy_and_grouped_boundary_results_agree(tmp_path, text, positive, negative):
    index=build_index(tmp_path,[document('positive',positive),document('negative',negative)])
    try:
        strict=index.search(replace(query(text),lexical_policy=MemoryRecallLexicalPolicy.LEGACY_STRICT_V1))
        grouped=index.search_grouped(query(text),deadline=monotonic()+5)
        assert [r.memory_item_id for r in strict] == ['positive']
        assert [r.memory_item_id for r in grouped.candidates] == ['positive']
        assert strict[0].snippet == grouped.candidates[0].snippet == positive
        # The substring fallback runs only when FTS has no exact hit. Remove
        # the positive record rather than letting it hide a fallback defect.
        index.rebuild([document('negative',negative)])
        assert not index.search(replace(query(text),lexical_policy=MemoryRecallLexicalPolicy.LEGACY_STRICT_V1))
        assert not index.search_grouped(query(text),deadline=monotonic()+5).candidates
    finally:index.close()
