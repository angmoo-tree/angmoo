"""Real event and own/received-post producers retain separate parent identity."""
from dataclasses import asdict
from datetime import UTC, datetime
import pytest
from test_p8_l_r_today_sns_activity import today_session, _seed_today_activity, NOW
from app.runtime.social.today_activity import today_social_activity_reader
from app.domains.social.contracts.today_activity import validate_today_activity_payload


def test_event_and_post_paths_keep_exact_parent_body_identity(today_session):
    db, fixture = today_session
    _seed_today_activity(db, fixture)
    result = today_social_activity_reader(db).read(owner_id=fixture["owner"].id,
        world_id=fixture["world"].id, subject_world_character_id=fixture["subject"].id,
        started_at=datetime(2026, 9, 3, 15, tzinfo=UTC), complete_through=NOW)
    records = {record.source_post_id: record for record in result.records}
    authored = records["subject-reply"]
    received = records["peer-direct-reply"]
    root = records["subject-root"]
    assert authored.record_key.startswith("event:")
    assert received.record_key.startswith("post:")
    assert (authored.source_post_id, authored.parent_post_id, authored.target_post_id, authored.root_post_id) == (
        "subject-reply", "peer-root", "peer-root", "peer-root")
    assert (received.source_post_id, received.parent_post_id, received.root_post_id) == (
        "peer-direct-reply", "subject-reply", "peer-root")
    assert received.parent_body == authored.body
    assert root.parent_post_id is None and root.parent_body is None
    payload = {"context": {"today_activity": {"records": [asdict(record) for record in result.records]}}}
    validate_today_activity_payload(payload)
    assert all(record.source_post_id not in {"hidden-direct-reply", "blocked-direct-reply", "peer-unrelated-sibling"} for record in result.records)


@pytest.mark.parametrize("record", [
    {"parent_body": "actual text", "source_post_id": "child"},
    {"parent_title": "title", "source_post_id": "child"},
    {"parent_post_id": "child", "source_post_id": "child"},
    {"parent_post_id": "parent", "source_post_id": None},
])
def test_inconsistent_final_parent_pair_is_rejected(record):
    with pytest.raises(ValueError, match="parent_identity_invalid"):
        validate_today_activity_payload({"today_activity": {"records": [record]}})
