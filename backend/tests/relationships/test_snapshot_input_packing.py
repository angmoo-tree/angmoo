"""Relationship summary inputs exclude original snapshots; recall keeps them."""
import pytest
from app.domains.relationships.policies.daily_review import fits_input, partition_review_inputs, prompt_payload


def test_private_guard_metadata_personas_scores_and_originals_are_not_model_input():
    payload={"owner_id":"owner","identity":{"subject_persona":"private persona"},
        "credential_id":"credential","existing_relationship":{"relationship_label":"친구","perception":"믿을 만하다","trust":90},
        "memories":[{"memory_id":"m","summary":"상대가 도와줬다.","occurred_at":"2026-10-28",
            "digest":"a"*64,"snapshots":[{"text":"not relationship input"}],"source_refs":["POST:p"]}]}
    assert prompt_payload(payload)=={"existing_relationship":{"relationship_label":"친구","perception":"믿을 만하다"},
        "memories":[{"memory_id":"m","summary":"상대가 도와줬다.","occurred_at":"2026-10-28"}]}
    assert payload['memories'][0]['snapshots'][0]['text']=='not relationship input'


def test_many_summary_bodies_are_bounded_without_truncating_or_repeating_memories():
    entries=[{"memory_id":str(i),"summary":"관계 경험 😊 "*200,"occurred_at":str(i)} for i in range(80)]
    parts=partition_review_inputs({},entries)
    assert len(parts)>1 and all(fits_input(p) for p in parts)
    assert [m for p in parts for m in p['memories']]==entries
    with pytest.raises(ValueError,match='single_entry_exceeds_budget'):
        partition_review_inputs({},[{**entries[0],'summary':'x'*50000}])


def test_partial_result_reduction_preserves_saved_results_without_sources():
    results=[{'part_id':str(i),'findings':['Result '*250],'uncertainty':'','memory_refs':['m']} for i in range(30)]
    parts=partition_review_inputs({},results,key='partial_results')
    assert all(fits_input(p) for p in parts)
    assert [r for p in parts for r in p['partial_results']]==results
    assert all('source_refs' not in r for p in parts for r in p['partial_results'])
