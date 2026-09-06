import asyncio
import hashlib
from types import SimpleNamespace

import pytest
from pydantic import SecretStr
from app.domains.routines import models
from app.domains.routines.exceptions import (
    WritingCompositionError,
    WritingCompositionInvalidError,
)
from app.domains.routines.service import writing_results
from app.runtime.resident import writing


def _gateway_inputs():
    return {
        "run": SimpleNamespace(
            id="run-1",
            agent_id="resident-1",
            character_id="character-1",
            tool_auth_key="tool-auth-test",
            session_key="run-session",
            gateway_result={
                "session_context": {"memory_session_key": "daypart-memory"}
            },
        ),
        "credential": SimpleNamespace(
            provider="google", model="test-model", auth_profile_id="profile-1"
        ),
        "session_key": "fallback-session",
        "kind": "create_post",
        "brief": "source: owner_feed_cue\nwrite a greeting",
        "target_post_id": None,
        "prompt": "original prompt",
        "stream_params": {},
    }


def test_gateway_writer_keeps_single_call_scratch_identity_and_no_tool_contract(
    monkeypatch,
):
    calls = []

    class Gateway:
        def __init__(self, **kwargs):
            calls.append(("client", kwargs))

        async def run_agent(self, **kwargs):
            calls.append(("run", kwargs))
            return {"status": "completed", "text": '{"body":"hello"}'}

    monkeypatch.setattr(writing, "OpenClawGatewayClient", Gateway)
    monkeypatch.setattr(
        writing.settings, "OPENCLAW_GATEWAY_TOKEN", SecretStr("gateway-test-token")
    )
    inputs = _gateway_inputs()
    result = writing._run_composition_gateway(**inputs)
    assert result == {"status": "completed", "text": '{"body":"hello"}'}
    assert [name for name, _ in calls] == ["client", "run"]
    request = calls[1][1]
    brief_hash = hashlib.sha256(
        f"create_post:-:{inputs['brief']}".encode()
    ).hexdigest()[:16]
    assert (
        request["session_key"]
        == f"daypart-memory:scratch:writing-composition-create_post:run-1:{brief_hash}"
    )
    assert (
        request["idempotency_key"]
        == f"run-1-writing-composition-create_post-{brief_hash}"
    )
    assert request["tool_auth_key"] == "tool-auth-test"
    assert request["tool_choice"] == "none"
    assert request["tools_allow"] == ["angmoo_list_feed"]
    assert request["auth_profile_id"] == "profile-1"
    assert request["extra_system_prompt"] == "original prompt"
    assert request["stream_params"] == {}


def test_gateway_writer_rejects_active_event_loop_before_provider_call(monkeypatch):
    provider_calls = []

    class Gateway:
        def __init__(self, **kwargs):
            pass

        async def run_agent(self, **kwargs):
            provider_calls.append(kwargs)
            return {}

    monkeypatch.setattr(writing, "OpenClawGatewayClient", Gateway)
    monkeypatch.setattr(
        writing.settings, "OPENCLAW_GATEWAY_TOKEN", SecretStr("gateway-test-token")
    )

    async def invoke():
        with pytest.raises(WritingCompositionError, match="active event loop"):
            writing._run_composition_gateway(**_gateway_inputs())

    asyncio.run(invoke())
    assert provider_calls == []


def test_writing_lane_preserves_other_run_state_and_commits_same_session_once():
    run = SimpleNamespace(
        gateway_result={
            "session_context": {"memory_session_key": "memory-1"},
            "writing_composition_lanes": [{"status": "completed", "kind": "reply"}],
        }
    )
    calls = []

    class Session:
        def get(self, model, key):
            calls.append(("get", model, key))
            return run

        def commit(self):
            calls.append(("commit",))

    writing_results._append_writing_composition_lane(
        Session(),
        run_id="run-1",
        kind="create_post",
        gateway_result={
            "status": "completed",
            "runId": "gateway-run",
            "result": {
                "meta": {
                    "agentMeta": {
                        "llmUsage": {
                            "providerCallCount": 1,
                            "successfulProviderCallCount": 1,
                            "failedProviderCallCount": False,
                            "totalTokens": 42,
                            "perCall": [
                                {"index": 0, "status": "completed", "totalTokens": 42}
                            ],
                        }
                    }
                }
            },
        },
    )
    assert calls == [("get", models.AgentRun, "run-1"), ("commit",)]
    assert run.gateway_result["session_context"] == {"memory_session_key": "memory-1"}
    assert run.gateway_result["writing_composition_lanes"][0] == {
        "status": "completed",
        "kind": "reply",
    }
    lane = run.gateway_result["writing_composition_lanes"][1]
    assert lane["kind"] == "create_post"
    assert lane["runId"] == "gateway-run"
    assert lane["llmUsage"]["providerCallCount"] == 1
    assert lane["llmUsage"]["failedProviderCallCount"] == 0
    assert lane["llmUsage"]["totalTokens"] == 42


@pytest.mark.parametrize("reply_text", ['{"reply":{"body":"hello"}}', "not JSON"])
def test_composition_records_provider_usage_before_response_validation(
    monkeypatch, reply_text
):
    db = object()
    run = SimpleNamespace(id="run-1")
    events = []

    def read_character(session, character_id):
        assert session is db
        events.append("character")
        return SimpleNamespace(deleted_at=None)

    def read_credential(session, actual_run):
        assert session is db and actual_run is run
        events.append("credential")
        return object()

    def read_setting(session, character_id):
        assert session is db
        events.append("setting")
        return object()

    def read_state(session, character_id):
        assert session is db
        events.append("state")
        return None

    def build_prompt(session, **kwargs):
        assert session is db
        events.append("prompt")
        return "prompt"

    def provider(**kwargs):
        events.append("provider")
        return {
            "text": reply_text,
            "result": {"meta": {"agentMeta": {"llmUsage": {"providerCallCount": 1}}}},
        }

    def record_lane(session, **kwargs):
        assert session is db
        events.append("record")

    monkeypatch.setattr(writing.character_profile, "get_character", read_character)
    monkeypatch.setattr(writing, "_run_credential", read_credential)
    monkeypatch.setattr(writing.activity_settings, "ensure_setting", read_setting)
    monkeypatch.setattr(writing.character_state, "get_character_state", read_state)
    monkeypatch.setattr(writing, "_build_composition_prompt", build_prompt)
    monkeypatch.setattr(writing, "_run_composition_gateway", provider)
    monkeypatch.setattr(writing, "_append_writing_composition_lane", record_lane)
    kwargs = dict(
        session_key="session",
        run=run,
        character_id="character-1",
        kind="reply",
        brief="reply brief",
        target_post_id="post-1",
    )
    if reply_text == "not JSON":
        with pytest.raises(
            WritingCompositionInvalidError, match="composition did not return JSON"
        ):
            writing._compose_writing_from_brief(db, **kwargs)
    else:
        payload, usage, lore = writing._compose_writing_from_brief(db, **kwargs)
        assert payload == {"body": "hello"}
        assert usage == {"providerCallCount": 1}
        assert lore is None
    assert events == [
        "character",
        "credential",
        "setting",
        "state",
        "prompt",
        "provider",
        "record",
    ]


@pytest.mark.parametrize("kind", ["create_post", "reply"])
def test_writer_admits_before_composition_and_records_memory_after_social_write(
    monkeypatch, kind
):
    db = object()
    run = SimpleNamespace(id="run", gateway_result={})
    post = SimpleNamespace(id="created-post", title="A public greeting")
    events = []

    def step(name, result=None):
        def invoke(session, *args, **kwargs):
            assert session is db
            events.append(name)
            return result

        return invoke

    monkeypatch.setattr(writing.social_agent_tool_authorization, "_session_fingerprint", lambda _: "redacted")
    monkeypatch.setattr(writing.runtime_agent_tool_authorization, "_get_agent_tool_run", step("run", run))
    monkeypatch.setattr(
        writing.social_agent_tool_authorization, "_agent_tool_character_id", lambda *args, **kwargs: "character"
    )
    monkeypatch.setattr(writing.runtime_agent_tool_authorization, "_agent_tool_user", step("user"))
    monkeypatch.setattr(writing.runtime_agent_tool_authorization, "_ensure_tick_action_allowed", step("gate"))
    monkeypatch.setattr(
        writing.community_crud,
        "get_post",
        step("target", SimpleNamespace(author_character_id="other")),
    )
    monkeypatch.setattr(writing.social_resident_affordances, "_ensure_agent_can_reply_to_thread", step("thread"))
    monkeypatch.setattr(
        writing,
        "_compose_writing_from_brief",
        step(
            "compose",
            (
                {"title": "A public greeting", "body": "Hello from the shared world."},
                None,
                None,
            ),
        ),
    )
    monkeypatch.setattr(writing.agent_tool_actions, "create_agent_tool_post", step("social", post))
    monkeypatch.setattr(writing.agent_tool_actions, "reply_agent_tool_post", step("social", post))
    monkeypatch.setattr(
        writing.character_lore_service, "mark_lore_chunks_used", step("lore")
    )

    def memory(session, *, run, action_memory):
        assert session is db
        assert action_memory["post_id"] == "created-post"
        events.append("memory")

    monkeypatch.setattr(writing, "_record_daypart_action_memory", memory)
    monkeypatch.setattr(
        writing.schemas, "AgentBriefWriteResult", lambda **kwargs: kwargs
    )
    data = SimpleNamespace(
        author_character_id="character", brief="source: owner_feed_cue\nSay hello."
    )
    if kind == "create_post":
        result = writing.create_agent_tool_post_from_brief(db, "session", data)
        assert events == ["run", "user", "gate", "compose", "social", "lore", "memory"]
    else:
        result = writing.reply_agent_tool_post_from_brief(
            db, "session", "target-post", data
        )
        assert events == [
            "run",
            "user",
            "gate",
            "target",
            "thread",
            "compose",
            "social",
            "memory",
        ]
    assert result["status"] == "ok"
    assert result["kind"] == kind
    assert result["post"] is post
    assert result["action_memory"]["source_post"] == (
        "target-post" if kind == "reply" else None
    )


def test_existing_daypart_writer_keeps_event_identity_and_single_commit():
    from app.services.agent_writing import _record_daypart_action_memory

    events = []

    class Session:
        def add(self, event):
            events.append(event)

        def commit(self):
            events.append("commit")

    run = SimpleNamespace(
        id="run-1",
        character_id="character-1",
        gateway_result={
            "session_context": {
                "daypart_persistent": True,
                "memory_session_key": "memory-1",
                "daypart_start_date": "2026-09-04",
                "activity_daypart": "evening",
            }
        },
    )
    payload = {
        "action_type": "reply",
        "post_id": "reply-1",
        "source_post": "target-1",
        "public_result_summary": "Saved result",
        "topic": "Greeting",
    }
    _record_daypart_action_memory(Session(), run=run, action_memory=payload)
    event, committed = events
    assert event.character_id == "character-1"
    assert event.run_id == "run-1"
    assert event.source_post_id == "target-1"
    assert event.event_type == "action_reply"
    assert event.memory_session_key == "memory-1"
    assert event.daypart_start_date.isoformat() == "2026-09-04"
    assert event.activity_daypart == "evening"
    assert event.payload is payload
    assert event.summary == "Saved result"
    assert committed == "commit"
