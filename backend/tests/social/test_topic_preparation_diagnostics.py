"""Exercise the real JSON/schema/apply boundary with an offline provider response."""
import asyncio
import json

import pytest
from sqlalchemy import event

from social.test_recommendation_topics import scope
from social.test_topic_preparation import connected
from app.core import security
from app.domains.identity.schemas import WorldCredentialWrite
from app.domains.identity.service import world_credentials
from app.domains.social.schemas.recommendation import RecommendationTopicsRead, TopicGenerationResult
from app.domains.social.service.recommendation_topics import replace_source_topics
from app.integrations import direct_llm
from app.providers.gemini import build_gemini_developer_response_schema
from app.runtime.social import topic_preparation as service
from app.runtime.social import topic_preparation_diagnostics as diagnostics


def fake_response(monkeypatch, payload, *, text=None, finish_reason="STOP"):
    calls = []

    async def generate_text(**kwargs):
        calls.append(kwargs)
        assert kwargs["sdk_attempts"] == 1
        tracker = kwargs["tracker"]
        logical, physical = tracker.next_call_order(), tracker.next_provider_call_order()
        tracker.record_call(context=kwargs["context"], call_order=logical, provider_call_order=physical,
            status="ok", duration_ms=12, finish_reason=finish_reason)
        return direct_llm.DirectLlmResponse(text=json.dumps(payload) if text is None else text,
            parsed=payload, usage={}, finish_reason=finish_reason, call_order=logical, provider_call_order=physical)

    monkeypatch.setattr(direct_llm, "generate_text", generate_text)
    return calls


def run(db, world, character, wc, **kwargs):
    return asyncio.run(service.regenerate(db, world_id=world.id, owner_id=character.owner_id,
        world_character_id=wc.id, request_id="offline-request", **kwargs))


def records(caplog):
    return [json.loads(record.getMessage().split("topic_preparation_failed ", 1)[1])
            for record in caplog.records if record.name == diagnostics.__name__]


@pytest.mark.parametrize("count", [1, 24])
def test_allowed_boundaries_pass_real_json_validation_and_persist(scope, monkeypatch, caplog, count):
    db, world, character, wc = connected(scope, monkeypatch)
    payload = {"topics": [{"name": f"Topic {i}", "scope": "world"} for i in range(count)]}
    calls = fake_response(monkeypatch, payload)
    reply = run(db, world, character, wc)
    assert reply["state"] == "ready" and len(reply["topics"]) == count
    assert len(calls) == 1 and not records(caplog)
    schema = build_gemini_developer_response_schema(TopicGenerationResult)
    assert schema["properties"]["topics"]["minItems"] == 1
    assert schema["properties"]["topics"]["maxItems"] == 24
    assert "1 to 24 topics" in calls[0]["system_prompt"]


@pytest.mark.parametrize("payload,expected_type,expected_path,count", [
    ({"topics": []}, "too_short", "topics", 0),
    ({"topics": [{"name": f"PRIVATE Topic {i}", "scope": "world"} for i in range(25)]}, "too_long", "topics", 25),
    ({"topics": [{"name": "한", "scope": "world"}]}, "string_too_short", "topics.0.name", 1),
    ({"topics": [{"name": "PRIVATE Topic", "scope": "PRIVATE_INVALID"}]}, "literal_error", "topics.0.scope", 1),
    ({"topics": [{"name": "PRIVATE Topic", "scope": "world", "PRIVATE_SECRET": "PRIVATE_VALUE"}]}, "extra_forbidden", "unknown_field", 1),
])
def test_schema_failures_are_distinct_and_preserve_topics(scope, monkeypatch, caplog, payload, expected_type, expected_path, count):
    db, world, character, wc = connected(scope, monkeypatch)
    old_ids = replace_source_topics(db, world_id=world.id, world_character_id=wc.id, topics=[("Old topic", "world")])
    db.commit()
    calls = fake_response(monkeypatch, payload)
    reply = run(db, world, character, wc)
    assert reply["state"] == "failed" and reply["last_code"] == "generation_failed"
    assert [t["id"] for t in reply["topics"]] == old_ids
    assert len(calls) == 1  # No extra AI attempt for invalid output.
    diagnostic, = records(caplog)
    assert diagnostic["stage"] == "output_validation" and diagnostic["code"] == "response_schema_invalid"
    assert diagnostic["validation"] == [{"path": expected_path, "type": expected_type}]
    assert diagnostic["topic_count"] == count
    assert diagnostic["call_counts_observed"] and diagnostic["logical_calls"] == diagnostic["sdk_attempts"] == 1
    assert diagnostic["provider_calls"] == [{"status": "ok", "duration_ms": 12, "finish_reason": "STOP", "failure_class": None, "http_status": None}]
    assert diagnostic["request_id"] == "offline-request" and diagnostic["world_character_id"] == wc.id
    assert "PRIVATE" not in caplog.text and "synthetic-topic-sns-key" not in caplog.text
    assert "fingerprint" not in caplog.text and "preview" not in caplog.text


def test_truncated_json_records_shape_without_body_and_preserves_old_topics(scope, monkeypatch, caplog):
    db, world, character, wc = connected(scope, monkeypatch)
    replace_source_topics(db, world_id=world.id, world_character_id=wc.id, topics=[("Old topic", "world")])
    db.commit()
    fake_response(monkeypatch, None, text='{"topics": [{"name": "PRIVATE unfinished', finish_reason="MAX_TOKENS")
    reply = run(db, world, character, wc)
    assert reply["state"] == "failed" and reply["topics"][0]["name"] == "Old topic"
    diagnostic, = records(caplog)
    assert diagnostic["code"] == "response_json_invalid" and diagnostic["topic_count"] is None
    assert diagnostic["response"]["shape"] == "truncated_or_unclosed"
    assert diagnostic["response"]["finish_reason"] == "MAX_TOKENS"
    assert "PRIVATE" not in caplog.text


def test_apply_validation_keeps_old_links_and_logs_its_stage(scope, monkeypatch, caplog):
    db, world, character, wc = connected(scope, monkeypatch)
    old_ids = replace_source_topics(db, world_id=world.id, world_character_id=wc.id, topics=[("Old topic", "world")])
    db.commit()
    fake_response(monkeypatch, {"topics": [{"name": " 한 ", "scope": "world"}]})
    reply = run(db, world, character, wc)
    assert reply["state"] == "failed" and [t["id"] for t in reply["topics"]] == old_ids
    diagnostic, = records(caplog)
    assert diagnostic["stage"] == "apply" and diagnostic["code"] == "invalid_topic_definition"


def test_unavailable_logger_does_not_strand_failed_request(scope, monkeypatch):
    db, world, character, wc = connected(scope, monkeypatch)
    replace_source_topics(db, world_id=world.id, world_character_id=wc.id, topics=[("Old topic", "world")])
    db.commit()
    fake_response(monkeypatch, {"topics": []})
    def broken_logger(*args, **kwargs):
        raise OSError("unavailable log sink")
    monkeypatch.setattr(diagnostics.logger, "warning", broken_logger)
    reply = run(db, world, character, wc)
    assert reply["state"] == "failed" and reply["topics"][0]["name"] == "Old topic"


def test_write_failure_rolls_back_new_topics_before_recording_failure(scope, monkeypatch, caplog):
    db, world, character, wc = connected(scope, monkeypatch)
    old_ids = replace_source_topics(db, world_id=world.id, world_character_id=wc.id, topics=[("Old topic", "world")])
    db.commit()
    fake_response(monkeypatch, {"topics": [{"name": "New topic", "scope": "world"}]})
    def failed_apply(*args, **kwargs):
        replace_source_topics(*args, **kwargs)
        raise RuntimeError("PRIVATE storage error")
    monkeypatch.setattr(service, "replace_source_topics", failed_apply)
    reply = run(db, world, character, wc)
    assert reply["state"] == "failed" and [t["id"] for t in reply["topics"]] == old_ids
    diagnostic, = records(caplog)
    assert diagnostic["stage"] == "apply" and diagnostic["exception_type"] == "RuntimeError"
    assert "PRIVATE" not in caplog.text


def test_generation_error_is_distinct_from_received_invalid_json(scope, monkeypatch, caplog):
    db, world, character, wc = connected(scope, monkeypatch)
    async def timeout(*args):
        raise TimeoutError("PRIVATE provider detail")
    reply = run(db, world, character, wc, generator=timeout)
    assert reply["state"] == "failed"
    diagnostic, = records(caplog)
    assert diagnostic["stage"] == "generation" and diagnostic["exception_type"] == "TimeoutError"
    assert diagnostic["response"] is None
    assert diagnostic["sdk_attempts"] is None and not diagnostic["call_counts_observed"]
    assert "PRIVATE" not in caplog.text


def test_provider_error_records_http_status_without_exception_message(scope, monkeypatch, caplog):
    db, world, character, wc = connected(scope, monkeypatch)
    async def unavailable(**kwargs):
        tracker = kwargs["tracker"]
        tracker.record_call(context=kwargs["context"], call_order=tracker.next_call_order(),
            provider_call_order=tracker.next_provider_call_order(), status="error", duration_ms=30,
            failure_class="ServerError", provider_error={"provider_http_status": 503, "provider_message": "PRIVATE server detail"})
        raise direct_llm.DirectLlmError("PRIVATE server detail")
    monkeypatch.setattr(direct_llm, "generate_text", unavailable)
    assert run(db, world, character, wc)["state"] == "failed"
    diagnostic, = records(caplog)
    assert diagnostic["stage"] == "generation"
    assert diagnostic["sdk_attempts"] == 1 and diagnostic["provider_calls"][0]["http_status"] == 503
    assert diagnostic["provider_calls"][0]["failure_class"] == "ServerError"
    assert "PRIVATE" not in caplog.text


def test_saved_sns_metadata_is_read_only_current_and_never_decrypted(scope, monkeypatch):
    db, world, character, wc = connected(scope, monkeypatch)
    world_credentials.save(db, owner_id=character.owner_id, world_id=world.id, world_character_id=wc.id,
        purpose="sns", data=WorldCredentialWrite(expected_revision=1, provider="google",
            model="gemini-3.5-flash-lite", thinking_level="medium"))
    db.commit()
    def forbidden(*args, **kwargs):
        raise AssertionError("read must not decrypt or call AI")
    monkeypatch.setattr(security, "decrypt_secret", forbidden)
    monkeypatch.setattr(direct_llm, "generate_json", forbidden)
    statements = []
    def sql(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement.strip().split()[0])
    event.listen(db.get_bind(), "before_cursor_execute", sql)
    try:
        reply = service.read_topics(db, world_id=world.id, owner_id=character.owner_id, world_character_id=wc.id)
        RecommendationTopicsRead.model_validate(reply)
        assert reply["model"] == "gemini-3.5-flash-lite" and reply["thinking_level"] == "medium" and reply["has_key"]
        assert set(statements) == {"SELECT"}
        assert not any(key in reply for key in ("fingerprint", "api_key", "encrypted_secret"))
    finally:
        event.remove(db.get_bind(), "before_cursor_execute", sql)
    row = world_credentials.find(db, owner_id=character.owner_id, world_id=world.id, world_character_id=wc.id, purpose="sns")
    row.encrypted_secret = None
    db.commit()
    reply = service.read_topics(db, world_id=world.id, owner_id=character.owner_id, world_character_id=wc.id)
    assert not reply["has_key"] and reply["model"] == "gemini-3.5-flash-lite"


def test_missing_sns_settings_are_not_presented_as_a_saved_default(scope, monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "DAILY_PREPARATION_ENABLED", True)
    db, world, character, wc = scope
    world.owner_user_id = character.owner_id
    db.commit()
    reply = service.read_topics(db, world_id=world.id, owner_id=character.owner_id, world_character_id=wc.id)
    assert reply["model"] is reply["thinking_level"] is None and not reply["has_key"]
