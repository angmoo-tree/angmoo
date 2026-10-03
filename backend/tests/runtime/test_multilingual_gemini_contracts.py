"""Production transport, durable recovery, calendar and literal-source cross checks.

Only the physical Provider boundary is synthetic; production validators,
generation_json, RecoveryLedger, Combined lane and SQLite FTS execute unchanged.
"""
import asyncio
from copy import deepcopy
from datetime import UTC, date, datetime
import json
from time import monotonic

import pytest
from sqlalchemy.orm import Session

from app.contracts.environment import EnvironmentSnapshot
from app.core.calendar import day_bounds, wall_time
from app.core.time_meaning import resolve_calendar_meaning
from app.domains.world_characters.contracts.social_io import LANE_IO
from app.integrations import direct_llm
from app.runtime.autonomous_activity import provider as transport
from app.runtime.autonomous_activity.combined_provider import RecoveryLedger
from runtime.test_activity_combined_delivery import fixture
from runtime.test_activity_combined_contracts import assignment
from runtime.test_gemini_schema_missing_contract import candidate
from social.test_feed_reaction_intent import _engine

pytestmark = pytest.mark.usefixtures("deny_external_network")


def install_transport(monkeypatch, responses, *, after_first=None):
    calls = []
    async def generate(**kwargs):
        calls.append(deepcopy(kwargs))
        value, finish = responses[len(calls) - 1]
        if len(calls) == 1 and after_first:
            after_first()
        return direct_llm.DirectLlmResponse(json.dumps(value), None, {}, finish)
    monkeypatch.setattr(direct_llm, "generate_text", generate)
    monkeypatch.setattr(transport, "_api_key", lambda _: "synthetic-key")
    monkeypatch.setattr(transport, "_llm_context", lambda ctx, **kw: direct_llm.DirectLlmCallContext(
        "test", "actor", "run", kw["node"], kw["lane"], "google", "gemini-3.1-flash-lite"))
    return calls


def decision(valid):
    row = {"target_id": "post", "action": "comment", "brief": "Ask about A-17 without assuming agreement"}
    if valid:
        row.update(interaction_intent="ordinary_comment", comment_purpose="question")
    return {"decision": {"decisions": [row], "state_update": None}, "draft": {"replies": []}}


@pytest.mark.parametrize("locale", ["ko-KR", "en-US", "ja-JP", "ar-AE"])
def test_combined_retry_freezes_environment_and_receipt_blocks_writer(monkeypatch, locale):
    async def run():
        with Session(_engine(), expire_on_commit=False) as db:
            lane, _, row, _ = fixture(db)
            lane.provider.social_io_policy = LANE_IO
            original = EnvironmentSnapshot(locale, "America/New_York", 1, 1).to_dict()
            current = {**original}
            calls = install_transport(monkeypatch, [(decision(False), "STOP"), (decision(True), "STOP")],
                after_first=lambda: current.update(memory_search_locale="en", timezone="Asia/Tokyo", environment_revision=2))
            result = await lane.provider.plan(lane="feed", context={"environment": original}, candidates=[candidate()])
            assert current["environment_revision"] == 2
            assert result["_json_recovery_receipt"] == {"reason": "comment_intent_missing", "attempt": 2, "node": "FeedDecisionDraft"}
            assert len(calls) == 2 and [r["max_output_tokens"] for r in calls] == [8192, 8192]
            assert calls[1]["user_prompt"].startswith(calls[0]["user_prompt"])
            assert json.dumps(original, ensure_ascii=False) in calls[0]["user_prompt"]
            assert calls[0]["response_schema"] == calls[1]["response_schema"]
            assert calls[0]["thinking_level"] == calls[1]["thinking_level"]
            assert "language" in calls[0]["system_prompt"].lower()
            assert len(calls[1]["user_prompt"]) - len(calls[0]["user_prompt"]) <= 512
            task = assignment("post"); task["comment_purpose"] = "question"
            with pytest.raises(ValueError, match="recovery|draft"):
                await lane.write({"generation_mode": "combined", "decision": result,
                    "decision_context": {"environment": original}, "assignments": [task], "decision_input_receipt": {}})
            assert len(calls) == 2
            db.expire(row)
            assert row.result["recovery_reservations"] == ["FeedActionPlanner:json"]
            with pytest.raises(ValueError, match="recovery_exhausted"):
                RecoveryLedger(db, row.activity_id).reserve("FeedActionPlanner:json")
    asyncio.run(run())


@pytest.mark.parametrize("guard_reason", ["claim_changed", "source_changed", "permission_changed", "budget_exhausted"])
def test_latest_guard_prevents_second_physical_transmission(monkeypatch, guard_reason):
    async def run():
        with Session(_engine(), expire_on_commit=False) as db:
            lane, _, row, _ = fixture(db)
            lane.provider.social_io_policy = LANE_IO
            calls = install_transport(monkeypatch, [(decision(False), "STOP")])
            async def reject(attempt):
                assert attempt == 2
                raise ValueError(guard_reason)
            with pytest.raises(Exception):
                await lane.provider.plan(lane="feed", context={"environment": EnvironmentSnapshot().to_dict()},
                    candidates=[candidate()], before_json_retry=reject)
            assert len(calls) == 1
            db.expire(row)
            assert not row.result.get("recovery_reservations")
    asyncio.run(run())


@pytest.mark.parametrize("unit,offset,start,end", [
    ("day", -3, datetime(2026, 3, 6, 5, tzinfo=UTC), datetime(2026, 3, 7, 5, tzinfo=UTC)),
    ("week", -1, datetime(2026, 3, 2, 5, tzinfo=UTC), datetime(2026, 3, 9, 4, tzinfo=UTC)),
    ("month", -1, datetime(2026, 2, 1, 5, tzinfo=UTC), datetime(2026, 3, 1, 5, tzinfo=UTC)),
])
def test_closed_relative_meaning_has_independent_civil_boundary_oracle(unit, offset, start, end):
    now = datetime(2026, 3, 9, 5, tzinfo=UTC)
    result = resolve_calendar_meaning(now, "America/New_York", unit=unit, offset=offset)
    assert result == (start, end)


def test_morning_dst_and_skipped_date_have_civil_boundaries():
    start, end = resolve_calendar_meaning(datetime(2026, 3, 8, 15, tzinfo=UTC), "America/New_York", unit="day", period="morning")
    assert (end - start).total_seconds() == 11 * 3600
    assert wall_time(date(2026, 3, 8), 2, 30, "America/New_York") == datetime(2026, 3, 8, 7, tzinfo=UTC)
    assert wall_time(date(2026, 11, 1), 1, 30, "America/New_York") == datetime(2026, 11, 1, 5, 30, tzinfo=UTC)
    assert day_bounds(date(2011, 12, 30), "Pacific/Apia")[0] == day_bounds(date(2011, 12, 30), "Pacific/Apia")[1]
    with pytest.raises(ValueError):
        resolve_calendar_meaning(start, "UTC", unit="day", offset=1)


@pytest.mark.parametrize("query,positive,negative", [
    ("art", "We discussed art.", "A party began."),
    ("coffee", "coffee!", "coffeeshop"),
    ("A-17", "A-17 was cancelled.", "A-170 was accepted."),
    ("v1.2", "v1.2.", "v1.20"),
    ("café", "Cafe\u0301!", "caféteria"),
    ("قهوة", "قهوة", "القهويات"),
    ("می\u200cروم", "می\u200cروم", "می\u200cرومند"),
    ("축제", "축제에서 친구를 만났다.", "책을 읽었다."),
    ("図書館", "図書館で会った", "海辺で会った"),
])
def test_actual_fts_literal_boundaries_preserve_original_sources(tmp_path, query, positive, negative):
    from memory.test_grouped_fts_index import document, build_index, query as grouped_query
    index = build_index(tmp_path, [document("positive", positive), document("negative", negative)])
    try:
        result = index.search_grouped(grouped_query(query), deadline=monotonic()+5)
        assert [r.memory_item_id for r in result.candidates] == ["positive"]
        assert result.candidates[0].snippet == positive
    finally:
        index.close()


@pytest.mark.parametrize("values", [
    {"memory_search_locale": "en_US"}, {"timezone": "Mars/Base"},
    {"memory_search_locale": "UND"}, {"memory_search_locale": "X-private"},
    {"environment_revision": True}, {"timezone_revision": -1}, {"output_policy": "unknown"},
])
def test_corrupt_checkpoint_environment_never_becomes_a_fresh_default(values):
    with pytest.raises(ValueError, match="environment_snapshot_invalid"):
        EnvironmentSnapshot.from_dict(values)


def test_backward_snapshot_defaults_and_hash_inputs_are_stable():
    assert EnvironmentSnapshot.from_dict(None) == EnvironmentSnapshot()
    original = {"memory_search_locale": "ja-JP", "timezone": "Asia/Tokyo", "environment_revision": 2,
        "timezone_revision": 1, "output_policy": "persona-language.v1"}
    assert EnvironmentSnapshot.from_dict(original).to_dict() == original
    assert original == deepcopy(original)
