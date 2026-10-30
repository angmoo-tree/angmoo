"""Real episode retrieval, Chat commit/admission and provider-wait invalidation."""
import asyncio
from datetime import UTC, datetime, timedelta
import json
import sqlite3
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import Session, sessionmaker

from chat import test_p8_l_p_evidence_response_streaming as f
from chat.test_p8_l_p_evidence_response_streaming import response_session
from chat.test_named_selection_lifecycle import admission
from chat.test_advisory_person_hints import core
from memory.test_activity_situation_application import receipt, apply
from memory.test_activity_situation_recall import readers
from app.config import Settings
from app.domains.memory.contracts.scope import MemoryScope
from app.domains.memory.contracts.hybrid_recall import HybridAxisResult, RecallAxisReceipt, RecallAxisStatus
from app.domains.memory.models.items import MemoryItem, MemoryScopeSettingModel
from app.domains.memory.models.activity_situation import MemorySituationReceipt, MemorySituationManifest
from app.domains.memory.service.hybrid_recall import HybridRecallService
from app.runtime.memory.composition import memory_repository
from app.runtime.memory.canonical_worker import CanonicalReadWorker, DeadlineSessionFactory
from app.runtime.chat.message_composition import generation_service
from app.integrations import direct_llm
from app.providers.contracts import ProviderToolCall

pytestmark = pytest.mark.usefixtures("deny_external_network")


@pytest.mark.parametrize("change", ["none", "deleted", "hidden", "body"])
def test_episode_evidence_survives_commit_and_rejects_provider_wait_changes(response_session, tmp_path, monkeypatch, change):
    from app.domains.chat.service import response_workflow
    failures = []
    classify = response_workflow._classify_failure
    def capture(exc):
        failures.append((type(exc).__name__, str(exc)))
        return classify(exc)
    monkeypatch.setattr(response_workflow, "_classify_failure", capture)
    # Copy only the isolated fixture to a WAL file for the real worker thread.
    response_session.commit()
    path = tmp_path / "chat.sqlite"
    with sqlite3.connect(path) as target:
        response_session.connection().connection.driver_connection.backup(target)
    engine = create_engine(f"sqlite:///{path}")
    event.listen(engine, "connect", lambda conn, _: (conn.execute("PRAGMA foreign_keys=ON"), conn.execute("PRAGMA journal_mode=WAL")))
    with Session(engine) as db:
        owner, accepted, _ = admission(db, monkeypatch, memory=True, question="오늘 무슨 일이 있었어?", protocol=None)
        scope = MemoryScope("p-owner", "p-world", "p-responding")
        now = datetime.now(UTC)
        occurred = now - timedelta(minutes=5)
        monkeypatch.setattr("memory.test_activity_situation_contract.NOW", occurred)
        monkeypatch.setattr("memory.test_activity_situation_application.NOW", now)
        post = f.models.Post(id="guard-post", world_id=scope.world_id, author_world_character_id=scope.subject_world_character_id,
            author_character_id="p-responding-character", author_name="Bram", title="Practice", body="오늘 연습했다.",
            visibility="public", created_at=occurred, updated_at=occurred)
        db.add(post)
        db.commit()
        seed_receipt = receipt(db, scope, post)
        setting = memory_repository(db).get_scope_setting(scope)
        apply(db, setting, memory_repository(db))
        item = db.get(MemoryItem, seed_receipt.applied_item_id)
        assert item is not None
        reader, _, candidate, _ = readers(db, scope, item)
        reader.clock = lambda: datetime.now(UTC)
        sessions = DeadlineSessionFactory(sessionmaker(engine))
        reader.factory, reader.phase = sessions, sessions.phase
        worker = CanonicalReadWorker(sessions, reader)
        class Axis:
            def __init__(self, name): self.name = name
            async def search(self, *_args, **_kwargs):
                return HybridAxisResult((candidate,), RecallAxisReceipt(self.name, RecallAxisStatus.READY, True, 1, 0))
        class Hybrid(HybridRecallService):
            async def execute(self, request, **kwargs):
                result = await super().execute(request, **kwargs)
                assert result.records, (request.kinds, request.episode_source_kinds,
                    request.occurred_from, request.occurred_to, result.excluded_count, item.valid_from, item.status)
                return result
        hybrid = Hybrid(fts=Axis("fts"), vector=Axis("vector"), canonical=worker)
        calls, delivered = [], []
        async def provider(**kwargs):
            assert not db.in_transaction()
            calls.append(kwargs)
            kwargs["tracker"].next_call_order()
            kwargs["tracker"].next_provider_call_order()
            if kwargs.get("tools"):
                args = {**core("CANONICAL"), "time_scope": {"kind": "current_day", "expression": "오늘"}}
                return SimpleNamespace(text="", usage={}, finish_reason="STOP", tool_calls=(ProviderToolCall("CANONICAL", args, "guard-call"),))
            payload = json.loads(kwargs["user_prompt"].split("\n", 1)[-1])
            delivered.extend(payload["frozen_evidence"]["items"])
            assert any(row["kind"] == "episode_memory" for row in delivered)
            with Session(engine) as writer:
                if change == "deleted":
                    row = writer.get(MemoryItem, item.id)
                    row.status, row.deleted_at = "deleted", now
                elif change == "hidden": writer.get(f.models.Post, post.id).report_hidden_at = now
                elif change == "body": writer.get(f.models.Post, post.id).body = "다른 내용"
                writer.commit()
            answer = {"text": "오늘 연습한 기억이 있어요.", "thought": "기록을 확인한다.",
                "situation_description": "사용자가 오늘 일을 물었고 기억한 연습 기록으로 답했다."}
            return direct_llm.DirectLlmResponse(text=json.dumps(answer), parsed=answer, usage={}, finish_reason="STOP")
        monkeypatch.setattr(direct_llm, "generate_text", provider)
        async def run():
            try:
                return await f._collect(generation_service.stream_world_response(db, owner, "p-world", "p-thread",
                    accepted.response_request.request_id, memory_recall_service=SimpleNamespace(hybrid_service=hybrid),
                    runtime_settings=Settings(_env_file=None, CHAT_RECALL_MODE="social_hybrid", MEMORY_RECALL_REPRESENTATION="episode_v1")))
            finally:
                await worker.stop()
        events = asyncio.run(run())
        saved = f.SqlAlchemyResponseLifecycleRepository(db).get_request(accepted.response_request.request_id)
        assert len(calls) == 2, failures
        if change in {"none", "hidden", "body"}:
            assert saved.state.value == "committed", failures
            stored = saved.response_metadata["_evidence_inspector_v1"]["items"]
            memory_items = [row for row in stored if row["kind"] == "episode_memory"]
            # The legacy fixture has no captured original timestamp. Do not
            # infer one from a current post read merely because it still exists.
            assert len(memory_items) == 1 and memory_items[0]["time_provenance"]["kind"] == "unknown"
            assert db.scalar(select(func.count()).select_from(MemorySituationReceipt).where(MemorySituationReceipt.lane == "chat")) == 1
            from app.domains.memory.repository.situation_runs import request_run, claim_run
            from app.domains.memory.repository.situation_apply import apply_page
            from app.runtime.memory.situation_application_sources import PreparedSituationSources
            current_time = datetime.now(UTC)
            pending = request_run(db, memory_repository(db).get_scope_setting(scope), trigger="manual",
                request_key="save-chat-result-0001", expected_version=1, now=current_time)
            token = claim_run(db, pending.run_id, now=current_time)
            db.commit()
            apply_page(db, memory_repository(db), PreparedSituationSources(db), run_id=pending.run_id, token=token, now=current_time)
            db.commit()
            chat_receipt = db.scalar(select(MemorySituationReceipt).where(MemorySituationReceipt.lane == "chat"))
            assert chat_receipt.state == "applied", chat_receipt.error_code
            material = db.get(MemorySituationManifest, chat_receipt.manifest_id).payload
            prior, = [source for source in material["sources"] if source["source_type"] == "MEMORY_ITEM"]
            assert prior["thread_id"] is None and material["private_thread_id"] == "p-thread"
            stored_memory = db.get(MemoryItem, chat_receipt.applied_item_id)
            assert stored_memory is not None and stored_memory.thread_id == "p-thread"
            from app.runtime.memory.situation_sources import SituationSources
            sources = SituationSources(db)
            private_prior = sources.describe(scope, kind="MEMORY_ITEM", identifier=stored_memory.id,
                delivered=stored_memory.summary, path="/prior", role="prior", ordinal=0, private_thread="other-thread")
            assert private_prior.thread_id == "p-thread"
            assert sources.validate(SimpleNamespace(snapshot=SimpleNamespace(scope=scope), private_thread_id="other-thread"),
                private_prior, now=current_time).state != "available"
        else:
            assert saved.state.value == "failed" and events[-1].payload["failure_class"] == "source_context_changed"
            assert saved.committed_assistant_message_id is None
            assert not any(e.event_type.value == "delta" for e in events)
            assert db.scalar(select(func.count()).select_from(MemorySituationReceipt).where(MemorySituationReceipt.lane == "chat")) == 0
    engine.dispose()
