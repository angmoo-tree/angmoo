import asyncio
import json
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app import models as registered_models
from app.core import unit_of_work
from app.core.db import Base
from app.domains.routines import models
from app.domains.routines.service import perception_diagnostics
from app.runtime.resident import decision_lanes
from routine_posts.test_runtime import _seed


def test_feed_perception_skips_without_call_and_preserves_read_only_call_contract():
    calls = []
    response = {
        "status": "ok",
        "result": {
            "meta": {"finalAssistantVisibleText": '{"interesting_posts":[{"post_id":"p1","character_thought":"rain"}],"character_thoughts":"warm tea"}'},
            "payloads": [{"isReasoning": True, "text": "must not become output"}],
        },
    }

    class Client:
        async def run_agent(self, **kwargs):
            calls.append(kwargs)
            return response

    common = dict(
        client=Client(), agent_id="agent", session_key="session", run_id="run",
        character=SimpleNamespace(id="char", name="Parrot", persona_summary="quiet", speech_style="brief"),
        state=None, credential=SimpleNamespace(provider="provider", model="model", auth_profile_id="profile"),
        activity_policy=None, recent_activity_summary="- none",
    )
    skipped, detail = asyncio.run(decision_lanes._run_feed_perception(
        **common, feed_cue=object(), recent_feed_roots="p1",
    ))
    assert detail["status"] == "skipped"
    assert json.loads(skipped)["interesting_posts"] == []
    assert calls == []
    _, detail = asyncio.run(decision_lanes._run_feed_perception(
        **common, feed_cue=None, recent_feed_roots="- none",
    ))
    assert detail["status"] == "skipped"
    assert calls == []
    normalized, detail = asyncio.run(decision_lanes._run_feed_perception(
        **common, feed_cue=None, recent_feed_roots="p1: rain",
    ))
    assert len(calls) == 1
    request = calls[0]
    assert {k: request[k] for k in (
        "agent_id", "session_key", "idempotency_key", "provider", "model",
        "auth_profile_id", "tool_choice", "tools_allow", "prompt_mode",
        "bootstrap_context_mode", "bootstrap_context_run_kind",
    )} == {
        "agent_id": "agent", "session_key": "session:feed-perception",
        "idempotency_key": "run-feed-perception", "provider": "provider", "model": "model",
        "auth_profile_id": "profile", "tool_choice": "none", "tools_allow": ["angmoo_list_feed"],
        "prompt_mode": "minimal", "bootstrap_context_mode": "lightweight",
        "bootstrap_context_run_kind": "default",
    }
    assert "p1: rain" in request["extra_system_prompt"]
    assert json.loads(normalized)["interesting_posts"] == [{"post_id": "p1", "character_thought": "rain"}]
    assert detail["raw_text"] == response["result"]["meta"]["finalAssistantVisibleText"]
    assert "must not become output" not in normalized


def test_action_decision_preserves_policy_fallback_one_call_and_failure_identity():
    calls = []
    failure = RuntimeError("provider failed")

    class Client:
        fail = False

        async def run_agent(self, **kwargs):
            calls.append(kwargs)
            if self.fail:
                raise failure
            return {"status": "ok", "text": '{"decision_type":"create_post","needs_thread":true,"reason":"listen"}'}

    client = Client()
    policy = SimpleNamespace(allowed_actions=("observe",), to_prompt=lambda: "only observe")
    kwargs = dict(
        client=client, agent_id="agent", session_key="session", run_id="run",
        character=SimpleNamespace(id="char", name="Parrot", persona_summary="quiet", speech_style="brief"),
        state=None, credential=None, activity_policy=policy, feed_cue=None,
        inbox_threads="- none", recent_feed_roots="- none", feed_perception="{}",
        actionable_feed_candidates="- none", strong_social_connection_candidate="- none",
        social_connection_candidate="- none", relationship_review_candidate="- none",
        recent_activity_summary="- none", allow_thread_tool=False, has_inbox=False,
    )
    decision, detail = asyncio.run(decision_lanes._run_action_decision(**kwargs))
    assert decision == {
        "decision_type": "observe", "needs_thread": False, "thread_candidate_id": "",
        "focus_post_ids": [], "reason": "listen",
    }
    assert detail["decision"] is decision
    assert len(calls) == 1
    assert calls[0]["idempotency_key"] == "run-action-decision"
    assert calls[0]["session_key"] == "session:action-decision"
    assert calls[0]["provider"] is None
    assert calls[0]["tool_choice"] == "none"
    assert calls[0]["tools_allow"] == ["angmoo_list_feed"]
    client.fail = True
    with pytest.raises(RuntimeError) as caught:
        asyncio.run(decision_lanes._run_action_decision(**kwargs))
    assert caught.value is failure
    assert len(calls) == 2


def test_perception_debug_log_keeps_same_session_deferred_rollback_and_default_commit(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'debug.sqlite3'}")
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as db:
        fixture = _seed(db)
        kwargs = dict(user_id=fixture.user.id, character_id=fixture.character.id, run_id="run")
        before = list(db.scalars(select(models.AgentActivityLog)))
        perception_diagnostics._log_feed_perception_debug(db, **kwargs, feed_perception_result={"status": "skipped"})
        assert list(db.scalars(select(models.AgentActivityLog))) == before
        result = {"status": "ok", "perception": {"interesting_posts": [], "character_thoughts": "tea", "post_seed": "", "no_relevant_signal": True}}
        with unit_of_work.deferred_commits():
            perception_diagnostics._log_feed_perception_debug(db, **kwargs, feed_perception_result=result)
            log = db.scalar(select(models.AgentActivityLog).where(models.AgentActivityLog.action_type == "feed_perception_debug"))
            log_id = log.id
            assert log in db
            assert log.reason == "feed_perception_debug run_id=run"
            assert log.target_post_id is None
            assert json.loads(log.result)["run_id"] == "run"
            assert ": " not in log.result
            with Session(engine) as observer:
                assert observer.get(models.AgentActivityLog, log_id) is None
        db.rollback()
        assert db.get(models.AgentActivityLog, log_id) is None
        perception_diagnostics._log_feed_perception_debug(db, **kwargs, feed_perception_result=result)
        with Session(engine) as observer:
            persisted = observer.scalar(select(models.AgentActivityLog).where(models.AgentActivityLog.action_type == "feed_perception_debug"))
            assert persisted.character_id == fixture.character.id
            assert json.loads(persisted.result)["character_thoughts"] == "tea"
    engine.dispose()
