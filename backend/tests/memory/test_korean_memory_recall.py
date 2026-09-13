"""Real projection safety, bounded search and operation policy regressions."""
from dataclasses import replace
from types import SimpleNamespace
from time import perf_counter
from math import ceil
from datetime import UTC, datetime
import json
import os
from pathlib import Path

import pytest

from app.contracts.retrieval_observation import Observation, current
from app.domains.memory.contracts.recall import (
    MemoryRecallSearchQuery, MemoryRecallSearchIncomplete, RecallDocumentKind,
    CanonicalRecallQuery, CanonicalRecallOperation as Op, CanonicalRecallStatus,
)
from app.domains.memory.service.recall import CanonicalRecallService
from app.runtime.memory import sqlite_fts5_recall as adapter
from memory.test_korean_memory_recall_quality import SCOPE, document, build_index


def query(text="체력훈련 지구력 심박수", **kwargs):
    return MemoryRecallSearchQuery(SCOPE, text, (RecallDocumentKind.MEMORY_ITEM,), 5,
                                  korean_spacing_fallback=True, **kwargs)


@pytest.mark.parametrize("text,search,expected", [
    ("체력 훈련 지구력 심박수 회복", "체력훈련 지구력 심박수", True),
    ("심박수 회복을 지구력 노트에 기록", "심박수회복 지구력", True),
    ("체력 훈련에서 지구력 심박수", "체력훈련 지구력 심박수", True),
    ("체력 훈련 지구력 심박수", "체력훈련", False),
    ("아버지 가방에 물건을 넣음", "아버지가 방에", False),
    ("체력. 훈련 지구력 심박수", "체력훈련 지구력 심박수", False),
    ("체력 | 훈련 지구력 심박수", "체력훈련 지구력 심박수", False),
    ("체력 훈련 미세 제어 1.0초", "체력훈련 0.1초", False),
    ("체력 훈련 미세 제어 10.1초", "체력훈련 0.1초", False),
    ("체력 훈련 미세 제어 0.1초", "체력훈련 0.1초", True),
    ("체력 훈련 power lifting", "체력훈련 powerlifting", False),
    ("体力 訓練 心拍 回復", "体力訓練 心拍", False),
    ("体力 訓練 心拍 回復", "体力 訓練 心拍", True),
    ("power lifting recovery", "power lifting", True),
    ("체력 훈련 심박수 상승", "체력훈련 심박수 회복", False),
    ("체력 훈련을 하지 않았음", "체력훈련 실시", False),
])
def test_spacing_and_adversarial_text(tmp_path, text, search, expected):
    index = build_index(tmp_path, [document("target", text)])
    assert bool(index.search(query(search))) is expected
    index.close()


@pytest.mark.parametrize("field,value", [
    ("owner_id", "other"), ("world_id", "other"),
    ("subject_world_character_id", "other"), ("searchable", False),
    ("kind", RecallDocumentKind.POST),
])
def test_spacing_does_not_widen_scope(tmp_path, field, value):
    doc = replace(document("wrong", "체력 훈련 지구력 심박수"), **{field: value})
    index = build_index(tmp_path, [doc])
    assert index.search(query()) == ()
    index.close()


def test_participant_and_thread_filters(tmp_path):
    index = build_index(tmp_path, [document("right", "체력 훈련 지구력 심박수",
                        counterpart_world_character_id="partner", thread_id="thread")])
    assert len(index.search(query(counterpart_world_character_id="partner", thread_id="thread"))) == 1
    assert not index.search(query(counterpart_world_character_id="other"))
    assert not index.search(query(thread_id="other"))
    index.close()


def test_strict_results_and_order_bypass_new_scan(tmp_path, monkeypatch):
    index = build_index(tmp_path, [document(f"m-{n}", "미세 제어 0.1초 기술") for n in range(8)])
    before = index.search(replace(query("0.1초 기술"), korean_spacing_fallback=False))
    def forbidden(*args):
        pytest.fail("strict nonempty query must not run spacing scan")
    monkeypatch.setattr(index, "_spacing_rows", forbidden)
    assert index.search(query("0.1초 기술")) == before
    index.close()


def test_fts_failure_is_not_a_spacing_opportunity(tmp_path, monkeypatch):
    index = build_index(tmp_path, [document("target", "체력 훈련 지구력 심박수")])
    monkeypatch.setattr(adapter, "_quote_fts_term", lambda term: '"')
    def forbidden(*args):
        pytest.fail("FTS execution failure must not start spacing search")
    monkeypatch.setattr(index, "_spacing_rows", forbidden)
    assert not index.search(query())
    index.close()


@pytest.mark.parametrize("budget,reason", [
    ("_SPACING_MAX_ROWS", "row_budget"), ("_SPACING_MAX_BYTES", "text_budget"),
    ("_SPACING_SECONDS", "time_budget"),
])
def test_budget_is_incomplete_not_absence(tmp_path, monkeypatch, budget, reason):
    index = build_index(tmp_path, [document(f"m-{n}", "체력 훈련 일반 기록") for n in range(5)])
    monkeypatch.setattr(adapter, budget, 0)
    obs = Observation()
    token = current.set(obs)
    try:
        with pytest.raises(MemoryRecallSearchIncomplete):
            index.search(query())
    finally:
        current.reset(token)
    event = obs.events[-1]
    assert event["reason"] == reason
    assert event["truncated"] and event["returned"] == 0
    assert "search_text" not in json.dumps(obs.payload())
    # The connection's progress callback cannot leak into another search.
    assert index.search(query("일반 기록"))
    index.close()


def test_service_preserves_incomplete_status_and_skips_revalidation():
    class Index:
        def doctor(self): return SimpleNamespace(healthy=True)
        def search(self, request): raise MemoryRecallSearchIncomplete()
    repo = SimpleNamespace(memory_enabled=lambda scope: True)
    result = CanonicalRecallService(repo, Index()).execute(CanonicalRecallQuery(
        operation=Op.SEARCH_MEMORY_ITEMS, scope=SCOPE, text="체력훈련 심박수"))
    assert result.status == CanonicalRecallStatus.DEGRADED
    assert result.reason_code == "memory_recall_search_incomplete"
    assert result.truncated and not result.records


@pytest.mark.parametrize("operation,timed,enabled", [
    (Op.SEARCH_MEMORY_ITEMS, False, True),
    (Op.SEARCH_MEMORY_ITEMS, True, False),
    (Op.SEARCH_POSTS, False, False),
    (Op.SEARCH_THREAD_MESSAGES, False, False),
])
def test_backend_operation_selects_policy(operation, timed, enabled):
    seen = []
    class Index:
        def doctor(self): return SimpleNamespace(healthy=True)
        def search(self, request):
            seen.append(request)
            return ()
    repo = SimpleNamespace(memory_enabled=lambda scope: True, revalidate_candidates=lambda **kw: ())
    CanonicalRecallService(repo, Index()).execute(CanonicalRecallQuery(
        operation=operation, scope=SCOPE, text="체력훈련 심박수",
        occurred_from=datetime(2026, 1, 1, tzinfo=UTC) if timed else None))
    assert seen[0].korean_spacing_fallback is enabled


def test_default_and_other_document_kinds_do_not_opt_in(tmp_path):
    index = build_index(tmp_path, [
        document("memory", "체력 훈련 지구력 심박수"),
        replace(document("post", "체력 훈련 지구력 심박수"), kind=RecallDocumentKind.POST),
    ])
    assert not index.search(replace(query(), korean_spacing_fallback=False))
    assert not index.search(replace(query(), kinds=(RecallDocumentKind.POST,)))
    index.close()


def test_new_candidates_still_revalidated_and_memory_off_does_no_io(tmp_path):
    index = build_index(tmp_path, [document("gone", "체력 훈련 지구력 심박수")])
    seen = []
    class OptInIndex:
        def doctor(self): return index.doctor()
        def search(self, request): return index.search(replace(request, korean_spacing_fallback=True))
    def revalidate(**kwargs):
        seen.extend(kwargs["candidates"])
        return ()  # e.g. canonical lifecycle/source changed since projection
    repo = SimpleNamespace(memory_enabled=lambda scope: True, revalidate_candidates=revalidate)
    service = CanonicalRecallService(repo, OptInIndex())
    request = CanonicalRecallQuery(operation=Op.SEARCH_MEMORY_ITEMS, scope=SCOPE, text=query().text)
    result = service.execute(request)
    assert len(seen) == 1 and result.excluded_count == 1 and not result.records
    repo.memory_enabled = lambda scope: False
    seen.clear()
    assert service.execute(request).status == CanonicalRecallStatus.DISABLED
    assert not seen
    index.close()


@pytest.mark.parametrize("count", [1_000, 10_000])
def test_old_target_and_bounded_cost(tmp_path, count):
    # All filler sorts ahead of target. Necessary-character filtering must not
    # silently turn this into a newest-N search.
    docs = [document(f"a-{n:05}", "전혀 다른 일반 산책 기록") for n in range(count)]
    docs.append(document("z-old-target", "체력 훈련 지구력 심박수"))
    index = build_index(tmp_path, docs)
    samples = {"B0": [], "B1": []}
    stage_times = []
    for _ in range(60):
        for variant in samples:
            obs = Observation()
            token = current.set(obs)
            try:
                start = perf_counter()
                result = index.search(replace(query(), korean_spacing_fallback=variant == "B1"))
                samples[variant].append((perf_counter()-start)*1000)
            finally:
                current.reset(token)
            stage_times.extend(e["elapsed_ms"] for e in obs.events if e.get("method") == "korean_spacing_fallback")
            assert [r.memory_item_id for r in result] == (["z-old-target"] if variant == "B1" else [])
    p95 = {k: sorted(v)[ceil(len(v)*.95)-1] for k, v in samples.items()}
    if output := os.environ.get("MEMORY_PERF_OUTPUT"):
        with Path(output).open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({"count": count, "samples_ms": samples, "p95_ms": p95, "spacing_ms": stage_times}) + "\n")
    assert p95["B1"] - p95["B0"] <= 25
    assert max(stage_times) <= 100
    index.close()


def test_more_than_two_thousand_plausible_rows_are_not_false_zero(tmp_path):
    docs = [document(f"a-{n:05}", "체력 훈련 다른 기록") for n in range(2001)]
    docs.append(document("z-target", "체력 훈련 지구력 심박수"))
    index = build_index(tmp_path, docs)
    with pytest.raises(MemoryRecallSearchIncomplete):
        index.search(query())
    index.close()
