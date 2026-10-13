from dataclasses import replace
from datetime import UTC, datetime, timedelta
import pytest
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import Session

from app.runtime.persistence.model_registration import register_models
from app.domains.memory.contracts.activity_situation import (
    CommittedActivityResult, CommittedEffect, DeliveredInputManifest, DeliveredSourceEntry, stable_digest,
)
from app.domains.memory.policies.situation_output import parse_description, parse_situations
from app.domains.memory.repository.situation_admission import snapshot_for, admit
from app.domains.memory.repository.situation_runs import get_or_create_settings, request_run, claim_run, next_due
from app.domains.memory.repository.situation_apply import apply_page, SituationSourceAccess
from app.domains.memory.models.activity_situation import MemorySituationReceipt, MemorySituationApplyRun, MemorySituationManifest
from app.domains.memory.models.items import MemoryItem
from app.domains.memory.exceptions import MemoryConflictError
from memory.test_p8_l_o_memory_consolidation import _stack

NOW = datetime(2026, 10, 8, 10, tzinfo=UTC)


@pytest.fixture
def stack():
    engine = create_engine("sqlite://")
    event.listen(engine, "connect", lambda db, _: db.execute("PRAGMA foreign_keys=ON"))
    register_models().create_all(engine)
    with Session(engine) as session:
        scope, setting, _, memory, *_ = _stack(session)
        yield session, scope, setting, memory
    engine.dispose()


def values(session, scope, *, target="p1", logical="a1", call="c1"):
    snapshot = snapshot_for(session, scope, locale="ko-KR")
    source = DeliveredSourceEntry("post", target, "1", stable_digest("full"), stable_digest("delivered"),
        "/target/body", "core", 0, scope.world_id, target_key=target)
    manifest = DeliveredInputManifest(call, snapshot, stable_digest({"target": target}), (source,))
    result = CommittedActivityResult(logical, "feed", target, ("like",),
        (CommittedEffect("like", "reaction", "reaction-1", "succeeded"),),
        stable_digest("output"), stable_digest("output"), NOW)
    return manifest, parse_description("평범한 하루 이야기에 공감하며 좋아요를 눌렀다.", target_key=target), result


@pytest.mark.parametrize("raw,status", [(None,"missing"), (12,"invalid"), (" ","invalid"), ("가"*1001,"invalid"), ("🙂"*1000,"valid")])
def test_description_validation_is_independent_and_codepoint_bounded(raw, status):
    assert parse_description(raw, target_key="p1").status == status


def test_duplicate_or_missing_situations_do_not_change_base_decision():
    payload = {"decision": {"action": "like"}, "draft": {}, "situations": [
        {"target_id": "p1", "description": "first"}, {"target_id": "p1", "description": "second"},
        {"target_id": "p2", "description": "ordinary moment"}]}
    parsed = parse_situations(payload, ("p1", "p2", "p3"))
    assert [row.status for row in parsed.values()] == ["invalid", "valid", "missing"]
    assert payload["decision"] == {"action": "like"}


def test_admission_rolls_back_with_activity_and_replay_conflicts(stack):
    session, scope, *_ = stack
    manifest, draft, result = values(session, scope)
    row = admit(session, manifest=manifest, draft=draft, result=result, now=NOW)
    assert row.state == "pending"
    assert session.scalar(select(func.count()).select_from(MemoryItem)) == 0
    session.rollback()
    assert session.scalar(select(func.count()).select_from(MemorySituationReceipt)) == 0
    assert session.scalar(select(func.count()).select_from(MemorySituationManifest)) == 0
    row = admit(session, manifest=manifest, draft=draft, result=result, now=NOW)
    session.commit()
    assert admit(session, manifest=manifest, draft=draft, result=result, now=NOW).sequence == row.sequence
    with pytest.raises(MemoryConflictError, match="content_conflict"):
        admit(session, manifest=manifest, draft=replace(draft, description="changed"), result=result, now=NOW)


@pytest.mark.parametrize("mode,code", [("missing","situation_description_missing"), ("partial","situation_result_mismatch"), ("unknown","situation_result_unknown")])
def test_invalid_description_and_partial_result_are_audited_without_items(stack, mode, code):
    session, scope, *_ = stack
    manifest, draft, result = values(session, scope)
    if mode == "missing":
        draft = parse_description(None, target_key=result.target_key)
    else:
        result = replace(result, effects=(replace(result.effects[0], status="unknown" if mode == "unknown" else "failed"),))
    row = admit(session, manifest=manifest, draft=draft, result=result, now=NOW)
    assert row.state == "blocked" and row.error_code == code
    assert session.scalar(select(func.count()).select_from(MemoryItem)) == 0


class Access:
    def __init__(self, state="available"):
        self.state = state
    def validate(self, manifest, source, *, now):
        return SituationSourceAccess(self.state)


def test_fixed_cutoff_replay_bounded_pages_and_no_recreation_after_delete(stack):
    session, scope, setting, memory = stack
    config = get_or_create_settings(session, setting.id, timezone="Asia/Seoul", now=NOW)
    assert not config.daily_enabled and config.local_time == "22:30" and config.shutdown_apply_enabled
    session.commit()
    empty = request_run(session, setting, trigger="manual", request_key="empty-request-0001", expected_version=1, now=NOW)
    assert empty.result_code == "empty" and empty.run_id is None
    for number in range(3):
        manifest, draft, result = values(session, scope, target=f"p{number}", logical=f"a{number}", call=f"c{number}")
        admit(session, manifest=manifest, draft=draft, result=result, now=NOW)
    first = request_run(session, setting, trigger="manual", request_key="save-request-0001", expected_version=1, now=NOW)
    cutoff = session.get(MemorySituationApplyRun, first.run_id).cutoff_sequence
    manifest, draft, result = values(session, scope, target="later", logical="later", call="later")
    admit(session, manifest=manifest, draft=draft, result=result, now=NOW)
    second = request_run(session, setting, trigger="manual", request_key="save-request-0002", expected_version=1, now=NOW)
    assert second.run_id == first.run_id and session.get(MemorySituationApplyRun, first.run_id).cutoff_sequence == cutoff
    assert request_run(session, setting, trigger="manual", request_key="empty-request-0001", expected_version=1, now=NOW).run_id is None
    session.commit()
    for n in range(3):
        token = claim_run(session, first.run_id, now=NOW)
        assert token
        session.commit()
        assert apply_page(session, memory, Access("deleted"), run_id=first.run_id, token=token, now=NOW, page_size=1) == 1
        session.commit()
        with pytest.raises(MemoryConflictError, match="fence_lost"):
            apply_page(session, memory, Access(), run_id=first.run_id, token=token, now=NOW)
    assert session.get(MemorySituationApplyRun, first.run_id).state == "completed"
    assert session.scalar(select(func.count()).select_from(MemoryItem)) == 3
    assert session.scalar(select(func.count()).select_from(MemorySituationReceipt).where(MemorySituationReceipt.state == "pending")) == 1
    original = session.scalar(select(MemorySituationReceipt).where(MemorySituationReceipt.state == "applied"))
    session.delete(session.get(MemoryItem, original.applied_item_id))
    session.commit()
    session.expire_all()
    assert original.state == "applied" and original.applied_item_id is None
    assert config.next_due_at is None


def test_closed_activation_is_not_reopened_by_turning_memory_back_on(stack):
    from app.domains.memory.service.scope import MemoryScopeService
    session, scope, setting, memory = stack
    manifest, draft, result = values(session, scope)
    off = MemoryScopeService(memory).update(scope, expected_version=setting.version, enabled=False, retention_days=180)
    MemoryScopeService(memory).update(scope, expected_version=off.version, enabled=True, retention_days=180)
    row = admit(session, manifest=manifest, draft=draft, result=result, now=NOW)
    assert row.state == "skipped" and row.error_code == "situation_activation_closed"


def test_dst_next_due_is_future_and_in_declared_timezone():
    assert next_due(datetime(2026, 3, 8, 6, tzinfo=UTC), "02:30", "America/New_York") == datetime(2026, 3, 8, 7, tzinfo=UTC)
