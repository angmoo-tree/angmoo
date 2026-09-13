"""Run memory search -> dependent detail against isolated real SQLite and FTS5."""
import asyncio
import json
from collections import Counter
from dataclasses import replace
from types import SimpleNamespace

import pytest

from model_fixture_support import models
from app.contracts.retrieval_observation import Observation, current
from app.domains.memory.contracts.recall import (
    CanonicalRecallOperation as Op, CanonicalRecallRecord, CanonicalRecallResult,
    CanonicalRecallStatus, RecallDocumentKind, CanonicalRecallQuery,
)
from app.domains.memory.contracts.scope import MemoryScope
from app.domains.memory.contracts.provenance import MemoryKindV1, MemorySourceTypeV1
from app.domains.memory.policies.retrieval_planner import parse_canonical_retrieval_plan_payload
from app.domains.memory.service.retrieval_plan import (
    CanonicalPlanExecutionContext, CanonicalRetrievalPlanExecutor,
)
from app.domains.memory.service.recall import CanonicalRecallService
from app.domains.memory.service.items import MemoryWriteLifecycleService
from app.domains.memory.service.scope import MemoryScopeService
from app.domains.memory.repository.recall import SqlAlchemyCanonicalRecallRepository
from app.runtime.memory.composition import memory_repository
from app.runtime.memory.recall_composition import recall_document_source
from app.runtime.memory.recall_queries import read_character_summary_rows
from app.runtime.memory.source_composition import source_evidence_reader
from app.runtime.memory.sqlite_fts5_recall import SqliteMemoryRecallIndex
from app.runtime.persistence.runtime_data_path import StaticRuntimeDataPath
from app.domains.chat.service.evidence_assembly import EvidenceBundleAssembler
from app.domains.chat.contracts.character_response_generator import (
    CharacterResponseGeneratorRequest, CharacterResponseProfile,
)
from app.domains.identity.contracts import CredentialMaterial, CredentialPurpose
from app.integrations import direct_llm
from app.integrations.llm.character_response_generator import DirectLlmCharacterResponseGenerator
from memory.test_p8_l_h_canonical_recall import (
    NOW, runtime_factory, _seed_world, _accept_chat_memory,
)


def _plan(scope, *, search="search_memory_items", detail="canonical_event_details", query="미세"):
    context = CanonicalPlanExecutionContext(
        request_id="dependency-request", envelope_version="resolved-retrieval.v1",
        envelope_hash="a" * 64, scope=scope, thread_id="fixture-thread",
        entity_bindings=(), operation_allowlist=tuple(op.value for op in Op), row_limit=20,
    )
    plan = parse_canonical_retrieval_plan_payload({
        "version": "canonical-plan.v1", "request_id": context.request_id,
        "envelope_version": context.envelope_version, "envelope_hash": context.envelope_hash,
        "steps": [
            {"id": "step1", "operation": search, "input_ref": None, "parameters": {"search_text": query}},
            {"id": "step2", "operation": detail, "input_ref": "step1.source_refs", "parameters": {}},
        ],
    })
    return plan, context


def _seed_posts(factory, *, replies=False):
    with factory() as session:
        scope, counterpart = _seed_world(session)
        subject = session.get(models.WorldCharacter, scope.subject_world_character_id)
        repo = memory_repository(session)
        initial = MemoryScopeService(repo).get_or_create(scope)
        setting = MemoryScopeService(repo).update(scope, expected_version=initial.version, enabled=True, retention_days=180)
        session.commit()
        lifecycle = MemoryWriteLifecycleService(repo, source_evidence_reader(session))
        if replies:
            other = session.get(models.WorldCharacter, counterpart)
            session.add(models.Post(
                id="dependency-parent", author_character_id=other.character_id,
                author_world_character_id=other.id, world_id=scope.world_id,
                post_type="post", visibility="public", author_name="Other",
                title="훈련", body="훈련 이야기", search_document="훈련", created_at=NOW,
            ))
            session.commit()
        ids = []
        for i in range(2):
            post = models.Post(
                id=f"dependency-post-{i}", author_character_id=subject.character_id,
                author_world_character_id=subject.id, world_id=scope.world_id,
                post_type="post", visibility="public", author_name="Fixture",
                title="미세 제어 훈련", body=f"미세 출력 조절 관찰. 원문전용상세{i}",
                search_document="미세 제어", created_at=NOW,
                reply_to_post_id="dependency-parent" if replies else None,
            )
            session.add(post)
            session.commit()
            proposed = lifecycle.propose_candidate(
                scope=scope, source_type=MemorySourceTypeV1.REPLY if replies else MemorySourceTypeV1.POST, source_id=post.id,
                memory_kind=MemoryKindV1.AUTOBIOGRAPHICAL_EVENT,
            )
            assert proposed.candidate is not None, proposed.code
            accepted = lifecycle.accept_candidate(
                scope=scope, candidate_id=proposed.candidate.id,
                expected_candidate_version=proposed.candidate.version,
                expected_scope_version=setting.version, summary_proposal=f"미세 제어 경험 {i}",
                enqueue_maintenance=False, now=NOW,
            )
            assert accepted.item is not None, accepted.code
            assert accepted.item.counterpart_world_character_id == (counterpart if replies else None)
            session.commit()
            ids.append(accepted.item.id)
        return scope, counterpart, tuple(ids)


def _recall(factory, tmp_path):
    index = SqliteMemoryRecallIndex(StaticRuntimeDataPath(tmp_path / "recall"))
    index.open()
    index.rebuild(recall_document_source(factory, now_factory=lambda: NOW).all_documents())
    reads = []

    def reader_factory(session):
        reader = source_evidence_reader(session)
        def read(**kwargs):
            reads.append(kwargs["source_id"])
            return reader.read_evidence(**kwargs)
        return SimpleNamespace(read_evidence=read)

    repository = SqlAlchemyCanonicalRecallRepository(
        factory, source_reader_factory=reader_factory, character_rows=read_character_summary_rows,
    )
    return CanonicalRecallService(repository, index), reads


@pytest.mark.parametrize("search,detail,search_text", [
    ("search_memory_items", "canonical_event_details", "미세"),
    ("search_posts", "get_post_thread", "미세"),
    ("search_memory_items", "canonical_event_details", "미세제어 경험"),
])
def test_real_search_detail_and_crg_input(runtime_factory, tmp_path, monkeypatch, search, detail, search_text):
    scope, _, item_ids = _seed_posts(runtime_factory)
    recall, reads = _recall(runtime_factory, tmp_path)
    plan, context = _plan(scope, search=search, detail=detail, query=search_text)
    observation = Observation()
    token = current.set(observation)
    try:
        execution = CanonicalRetrievalPlanExecutor(recall).execute(plan, context, now=NOW)
    finally:
        current.reset(token)
    first, second = execution.steps
    assert len(first.result.records) == 2
    assert {r.memory_item_id for r in first.result.records} == set(item_ids)
    assert all(r.reference.startswith("memory-") for r in first.result.records)
    assert len(second.result.records) == 2
    assert set(second.query.source_references) == {"source:POST:dependency-post-0", "source:POST:dependency-post-1"}
    assert Counter(reads) == {"dependency-post-0": 2, "dependency-post-1": 2}
    assert all("원문전용상세" in r.text for r in second.result.records)
    result = SimpleNamespace(request_id=context.request_id, execution=execution, metrics=SimpleNamespace(short_circuit_reason=None))
    bundle = EvidenceBundleAssembler().canonical(request_scope_hash="b" * 64, result=result)
    # Post search and details identify the same sources and are deduplicated;
    # memory summaries remain distinct from their original source details.
    assert len(bundle.items) == (4 if search == "search_memory_items" else 2)
    calls = []

    async def generate(**kwargs):
        calls.append(kwargs)
        kwargs["tracker"].next_call_order()
        evidence = json.loads(kwargs["user_prompt"].split("\n", 1)[1])["frozen_evidence"]
        serialized = json.dumps(evidence, ensure_ascii=False)
        assert "원문전용상세0" in serialized and "원문전용상세1" in serialized
        assert "dependency-post-" not in serialized
        return direct_llm.DirectLlmResponse(text="확인한 근거로 답합니다.", parsed=None, usage={}, finish_reason="STOP")

    monkeypatch.setattr(direct_llm, "generate_text", generate)
    generator = DirectLlmCharacterResponseGenerator(CredentialMaterial(
        credential_id="fixture", provider="google", model="gemini-3.1-flash-lite",
        fingerprint="fixture", purpose=CredentialPurpose.MESSAGE_LLM,
        _secret="synthetic-key", thinking_level="high",
    ))
    response = asyncio.run(generator.generate(CharacterResponseGeneratorRequest(
        user_message="저장 기억과 원문을 찾아줘", recent_context=(), evidence=bundle,
        profile=CharacterResponseProfile("Fixture", "fixture", "", "", "", "", "", ""),
    )))
    assert response.text == "확인한 근거로 답합니다." and len(calls) == 1
    assert calls[0]["max_output_tokens"] == 3072
    assert any(row["event"] == "dependency_refs" and row["output"] == 2 for row in observation.events)
    if search_text == "미세제어 경험":
        assert any(row.get("method") == "korean_spacing_fallback" and row["returned"] == 2
                   for row in observation.events)


@pytest.mark.parametrize("change", ["deleted", "hidden", "digest"])
def test_detail_revalidates_sources_changed_after_search(runtime_factory, tmp_path, change):
    scope, _, _ = _seed_posts(runtime_factory)
    recall, reads = _recall(runtime_factory, tmp_path)

    class ChangingRecall:
        def execute(self, query, *, now=None):
            result = recall.execute(query, now=now)
            if query.operation is Op.SEARCH_MEMORY_ITEMS:
                assert len(result.records) == 2
                with runtime_factory() as session:
                    post = session.get(models.Post, "dependency-post-0")
                    if change == "deleted":
                        post.deleted_at = NOW
                    elif change == "hidden":
                        post.report_hidden_at = NOW
                    else:
                        post.body = "changed original"
                    session.commit()
            return result

    plan, context = _plan(scope)
    execution = CanonicalRetrievalPlanExecutor(ChangingRecall()).execute(plan, context, now=NOW)
    assert len(execution.steps[0].result.records) == 2
    assert [r.canonical_source_id for r in execution.steps[1].result.records] == ["dependency-post-1"]
    assert Counter(reads) == {"dependency-post-0": 2, "dependency-post-1": 2}


@pytest.mark.parametrize("scope_field", ["owner_id", "world_id", "subject_world_character_id"])
def test_search_and_detail_keep_exact_scope(runtime_factory, tmp_path, scope_field):
    scope, _, _ = _seed_posts(runtime_factory)
    recall, _ = _recall(runtime_factory, tmp_path)
    other_scope = replace(scope, **{scope_field: "unrelated"})
    result = recall.execute(CanonicalRecallQuery(
        operation=Op.CANONICAL_EVENT_DETAILS, scope=other_scope,
        source_references=("source:POST:dependency-post-0",),
    ), now=NOW)
    assert result.records == ()
    plan, context = _plan(other_scope)
    execution = CanonicalRetrievalPlanExecutor(recall).execute(plan, context, now=NOW)
    assert not execution.records and execution.steps[1].dependency_short_circuited


def test_real_reply_dependency_preserves_other_participant_filter(runtime_factory, tmp_path):
    scope, counterpart, _ = _seed_posts(runtime_factory, replies=True)
    recall, _ = _recall(runtime_factory, tmp_path)
    plan, context = _plan(scope)
    context = replace(context, entity_bindings=(("mentor", counterpart),))
    search = replace(plan.steps[0], parameters=(*plan.steps[0].parameters, ("counterpart_ref", "mentor")))
    plan = replace(plan, steps=(search, plan.steps[1]))
    execution = CanonicalRetrievalPlanExecutor(recall).execute(plan, context, now=NOW)
    assert [len(step.result.records) for step in execution.steps] == [2, 2]
    assert execution.steps[0].query.counterpart_world_character_id == counterpart
    assert set(execution.steps[1].query.source_references) == {
        "source:REPLY:dependency-post-0", "source:REPLY:dependency-post-1",
    }
    # Resolving the filter to another ID must not silently broaden the search.
    wrong = replace(context, entity_bindings=(("mentor", "unrelated"),))
    excluded = CanonicalRetrievalPlanExecutor(recall).execute(plan, wrong, now=NOW)
    assert not excluded.records and excluded.steps[1].dependency_short_circuited


def test_real_message_source_dependency(runtime_factory, tmp_path):
    scope, _, _, message_id, _ = _accept_chat_memory(runtime_factory)
    recall, _ = _recall(runtime_factory, tmp_path)
    plan, context = _plan(scope, search="search_thread_messages", query="폭우")
    execution = CanonicalRetrievalPlanExecutor(recall).execute(plan, context, now=NOW)
    assert len(execution.steps[1].result.records) == 1
    assert execution.steps[1].query.source_references == (f"source:OWNER_MEMORY_REQUEST:{message_id}",)


@pytest.mark.parametrize("count", [0, 1, 50, 51])
def test_dependency_refs_are_deduplicated_bounded_and_never_fall_back(count):
    refs = tuple(f"source:POST:{i}" for i in range(count))
    records = (
        CanonicalRecallRecord(
            reference="memory-item:one", kind=RecallDocumentKind.MEMORY_ITEM,
            canonical_source_id="one", memory_item_id="one", text="fixture",
            occurred_at=NOW, evidence_references=refs,
        ),
        CanonicalRecallRecord(
            reference="source:POST:unverified-fallback", kind=RecallDocumentKind.POST,
            canonical_source_id="two", text="fixture", occurred_at=NOW,
            evidence_references=refs[:1],
        ),
    )
    calls = []
    class Recall:
        def execute(self, query, *, now=None):
            calls.append(query)
            return CanonicalRecallResult(
                operation=query.operation, status=CanonicalRecallStatus.READY,
                records=records if len(calls) == 1 else (),
            )
    plan, context = _plan(MemoryScope("owner", "world", "subject"))
    observation = Observation()
    token = current.set(observation)
    try:
        execution = CanonicalRetrievalPlanExecutor(Recall()).execute(plan, context, now=NOW)
    finally:
        current.reset(token)
    assert len(calls) == (2 if count else 1)
    if count:
        assert calls[1].source_references == refs[:50]
    else:
        assert execution.steps[1].dependency_short_circuited
    event = next(row for row in observation.events if row["event"] == "dependency_refs")
    assert event["input"] == count + bool(count)
    assert event["duplicates"] == int(bool(count))
    assert event["output"] == min(count, 50)
    assert event["excluded"] == max(0, count - 50)
    assert event["truncated"] is (count > 50)
    assert "unverified-fallback" not in json.dumps(observation.payload())
