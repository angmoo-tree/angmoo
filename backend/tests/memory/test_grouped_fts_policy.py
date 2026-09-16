import pytest
from app.domains.memory.policies.grouped_fts import build_groups, match_groups
from app.runtime.memory.grouped_fts_search import render_match


@pytest.mark.parametrize('query,text,expected', [
    ('아버지가','아버지가 편지를 가져왔다',True),
    ('아버지가','아버지 가방에 편지가 있었다',False),
    ('축제','별빛축제',True), ('1','13',False), ('1','0.1',False),
    ('13','13일',True), ('07:10','17:10',False), ('07:10','07:10:30',False),
    ('A-17','a-170',False), ('A-17','a-17',True), ('7장','17장',False),
    ('린','린은',True), ('린','어린이',False), ('API','api_key',False),
])
def test_literal_group_boundaries(query,text,expected):
    assert bool(match_groups(build_groups(query).groups,text)) is expected


def test_group_structure_and_truncation():
    query=build_groups('아시도와 축제 공연을 진행했는지 확인')
    assert len(query.groups)==5
    assert '("아시" AND "시도" AND "도와") OR ("축제")' in render_match(query.groups)
    assert len(build_groups('축제 '*100).groups)==1
    long=build_groups('축제 '+ '가'*1001)
    assert long.truncated and [g.text for g in long.groups]==['축제']
    assert '"or"' in render_match(build_groups('OR * "축제"').groups)
