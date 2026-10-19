from copy import deepcopy
from dataclasses import replace
from datetime import UTC, datetime
import pytest
from app.domains.chat.contracts.evidence_display import bounded_segments, projection, validate_projection, excerpt_segments, LABELS
from app.domains.chat.contracts.today_sns_activity import TodaySnsActivityEntry, TodaySnsSubjectiveContext
from app.domains.chat.service.evidence_assembly import EvidenceBundleAssembler
from app.domains.chat.repository.response_lifecycle import _validate_evidence_inspector_snapshot
from app.domains.chat.contracts.generation_lifecycle import GenerationContractError


def entry(**extra):
    values = dict(opaque_reference="today-example", kind="posts_authored", event_type="post_published",
        source_type="post", source_id="post-one", source_revision="a"*64, occurred_at=datetime.now(UTC),
        actor_label="Ian", counterpart_label="Marco", content_mode="full", title="A title",
        body="Hello 제목: literal | <b>🙂</b>  and\nmore", parent_title=None, parent_body=None,
        root_title=None, root_body=None, root_post_id=None, source_post_id="post-one", target_post_id=None,
        content_complete=True, truncated=False, subjective_context=None)
    return TodaySnsActivityEntry(**{**values, **extra})


def test_labels_preserve_provider_prose_and_literal_boundaries():
    item = EvidenceBundleAssembler._today_item(entry())
    expected = "오늘 SNS 활동 종류: posts_authored | 실제 행동: post_published | 행동 주체: Ian | 상대: Marco | 제목: A title | 내용: Hello 제목: literal | <b>🙂</b> and more"
    assert item.text == expected
    parts = validate_projection(item.display_projection, item.opaque_reference, item.text)
    assert any(s["key"] is None and "제목: literal" in s["text"] for s in parts)
    from app.domains.chat.contracts.evidence_bundle import compute_evidence_hash
    from app.domains.chat.contracts.retrieval_intent import RetrievalRoute
    from app.domains.chat.contracts.response_request import RetrievalOutcome
    params = dict(request_id="request", request_scope_hash="a"*64, route=RetrievalRoute.CURRENT_CONTEXT,
        retrieval_outcome=RetrievalOutcome.CURRENT_CONTEXT, partial_axes=(), degraded_reason=None, clarification_slot=None)
    assert compute_evidence_hash(**params, items=(item,)) == compute_evidence_hash(**params, items=(replace(item, display_projection=None),))


def test_unicode_bounds_and_partial_labels_have_no_offset_dependency():
    item = EvidenceBundleAssembler._today_item(entry(body="🙂" * 2100))
    assert len(item.text) == 2000
    parts = excerpt_segments(item.display_projection, item.opaque_reference, item.text)
    assert "".join(p["text"] for p in parts) == item.text[:500]
    value = bounded_segments([("title", LABELS["title"]), (None, "🙂")], 2)
    assert value == [{"key": None, "text": "제목"}]


@pytest.mark.parametrize("change", ["ref", "digest", "key", "literal", "extra"])
def test_projection_tampering_is_rejected_at_final_save(change):
    item = EvidenceBundleAssembler._today_item(entry())
    value = deepcopy(item.display_projection)
    if change == "ref": value["ref"] = "another"
    elif change == "digest": value["text_digest"] = "0"*64
    elif change == "key": value["segments"][0]["key"] = "unknown"
    elif change == "literal": value["segments"][-1]["text"] += "not delivered"
    else: value["extra"] = True
    raw = dict(ref=item.opaque_reference, kind=item.kind.value, text=item.text, occurred_at=None, axes=["canonical"], locator=None, display_projection=value)
    with pytest.raises(GenerationContractError):
        _validate_evidence_inspector_snapshot({"version":"evidence-inspector.v2","items":[raw]}, public_evidence_count=1)


def test_v1_compatibility_and_v2_explicit_projection_contract():
    item = EvidenceBundleAssembler._today_item(entry())
    raw = dict(ref=item.opaque_reference, kind=item.kind.value, text=item.text, occurred_at=None, axes=["canonical"], locator=None)
    _validate_evidence_inspector_snapshot({"version":"evidence-inspector.v1","items":[raw]}, public_evidence_count=1)
    raw["display_projection"] = item.display_projection
    _validate_evidence_inspector_snapshot({"version":"evidence-inspector.v2","items":[raw]}, public_evidence_count=1)
    with pytest.raises(GenerationContractError):
        _validate_evidence_inspector_snapshot({"version":"evidence-inspector.v1","items":[raw]}, public_evidence_count=1)


def test_subjective_labels_keep_original_text_including_intensity():
    item = EvidenceBundleAssembler._today_item(entry(subjective_context=TodaySnsSubjectiveContext(
        motivation_kind="connection", motivation_text="share a walk", emotion_label="joy", emotion_text="calm", emotion_intensity=12)))
    assert item.text.endswith("행동 결정 시 직접 선언한 동기: share a walk (connection) | 행동 결정 시 직접 선언한 감정: joy: calm (강도 12/100)")
    assert {p["key"] for p in item.display_projection["segments"]} >= {"motivation", "emotion", "intensity"}
