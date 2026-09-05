from __future__ import annotations

from copy import deepcopy

from sqlalchemy import event
from sqlalchemy.orm import Session

from app.domains.routines import models
from app.domains.routines.service import run_results as agent_runs
from routines.test_activity_persistence import _file_engine
from routines.test_run_persistence import _run
from routine_posts.test_runtime import _seed


def test_snapshot_commits_same_session_pending_result_and_preserves_input(tmp_path):
    engine = _file_engine(tmp_path)
    with Session(engine, expire_on_commit=False) as db:
        fixture = _seed(db)
        run = _run(db, fixture)
        run.gateway_result = {"status": "running", "reason": "pending local result"}
        payload = {
            "summary": "Stored safely",
            "unsafe_prompt": "raw prompt must be dropped",
            "writing_composition_lanes": [
                {"kind": "post", "status": "completed", "prompt": "raw writing input"}
            ],
        }
        original_payload = deepcopy(payload)
        commits = []

        @event.listens_for(db, "after_commit")
        def committed(_session):
            commits.append(True)

        agent_runs._persist_agent_run_gateway_snapshot(db, run_id=run.id, payload=payload)
        assert payload == original_payload
        assert commits == [True]
        with Session(engine) as observer:
            stored = observer.get(models.AgentRun, run.id).gateway_result
            assert stored["status"] == "running"
            assert stored["reason"] == "pending local result"
            assert stored["summary"] == "Stored safely"
            assert "unsafe_prompt" not in stored
            assert stored["writing_composition_lanes"] == [
                {"kind": "post", "status": "completed"}
            ]
    engine.dispose()


def test_missing_snapshot_does_not_commit_other_pending_session_writes(tmp_path):
    engine = _file_engine(tmp_path)
    with Session(engine, expire_on_commit=False) as db:
        fixture = _seed(db)
        run = _run(db, fixture)
        original = run.gateway_result
        run.gateway_result = {"reason": "other pending change"}
        commits = []

        @event.listens_for(db, "after_commit")
        def committed(_session):
            commits.append(True)

        agent_runs._persist_agent_run_gateway_snapshot(
            db, run_id="missing-run", payload={"status": "failed"},
        )
        assert commits == []
        assert run.gateway_result == {"reason": "other pending change"}
        with Session(engine) as observer:
            assert observer.get(models.AgentRun, run.id).gateway_result == original
        db.rollback()
        assert run.gateway_result == original
    engine.dispose()


def test_pending_writing_results_read_attached_values_without_committing(tmp_path):
    engine = _file_engine(tmp_path)
    with Session(engine, expire_on_commit=False) as db:
        fixture = _seed(db)
        run = _run(db, fixture)
        run.gateway_result = {
            "writing_composition_lanes": [None, {}, {"kind": "reply", "status": "pending"}]
        }
        commits = []

        @event.listens_for(db, "after_commit")
        def committed(_session):
            commits.append(True)

        assert agent_runs._pending_writing_composition_lanes(db, run.id) == [
            {"kind": "reply", "status": "pending"}
        ]
        assert commits == []
        db.rollback()
        assert agent_runs._pending_writing_composition_lanes(db, run.id) == []
        assert agent_runs._pending_writing_composition_lanes(db, "missing-run") == []
        assert commits == []
    engine.dispose()


def test_compact_stored_lane_result_keeps_read_only_attempt_diagnostics():
    compact = agent_runs._compact_stored_lane_result(
        {
            "status": "failed",
            "reason": "read_only_lane_retry_exhausted",
            "attempts": 2,
            "first_error_class": "google_503_high_demand",
            "failure_class": "openclaw_failover_timeout",
            "first_error": "Google 503",
            "error": "UNAVAILABLE: FailoverError: LLM request timed out.",
            "attempt_errors": [
                {
                    "attempt": 1,
                    "lane": "feed_scan",
                    "agent_run_id": "run-1",
                    "openclaw_run_id": "run-1-v6-feed-scan-attempt-1",
                    "provider": "google",
                    "model": "gemini-3.1-flash-lite",
                    "auth_profile_id": "google:char-1",
                    "timeout_seconds": 180,
                    "backend_request_started_at": "2026-06-06T09:00:00+00:00",
                    "backend_request_finished_at": "2026-06-06T09:03:00+00:00",
                    "backend_duration_ms": 180000,
                    "timeout_source": "provider_error",
                    "call_order_in_run": 3,
                    "error_class": "google_503_high_demand",
                    "error": "Google 503",
                    "prompt": "must not be kept",
                }
            ],
        }
    )

    assert compact["first_error_class"] == "google_503_high_demand"
    assert compact["failure_class"] == "openclaw_failover_timeout"
    assert compact["attempt_errors"][0] == {
        "attempt": 1,
        "lane": "feed_scan",
        "agent_run_id": "run-1",
        "openclaw_run_id": "run-1-v6-feed-scan-attempt-1",
        "provider": "google",
        "model": "gemini-3.1-flash-lite",
        "auth_profile_id": "google:char-1",
        "timeout_seconds": 180,
        "backend_request_started_at": "2026-06-06T09:00:00+00:00",
        "backend_request_finished_at": "2026-06-06T09:03:00+00:00",
        "backend_duration_ms": 180000,
        "timeout_source": "provider_error",
        "call_order_in_run": 3,
        "error_class": "google_503_high_demand",
        "error": "Google 503",
    }


def test_compact_stored_lane_result_keeps_inbox_decision_evidence():
    compact = agent_runs._compact_stored_lane_result(
        {
            "status": "observed",
            "outcome": "LLM_DECIDED_NO_ACTION",
            "decision_source": "llm",
            "candidate_count": 1,
            "planner_invoked": True,
            "provider_call_count": 1,
            "public_action_count": 0,
            "handled_notification_count": 1,
            "prompt": "must not be kept",
        }
    )

    assert compact == {
        "status": "observed",
        "outcome": "LLM_DECIDED_NO_ACTION",
        "decision_source": "llm",
        "candidate_count": 1,
        "planner_invoked": True,
        "provider_call_count": 1,
        "public_action_count": 0,
        "handled_notification_count": 1,
    }


def test_stored_gateway_result_keeps_sanitize_fallback_reason():
    stored = agent_runs._stored_gateway_result(
        {
            "status": "completed",
            "feed_history_sanitize_fallback": "metadata_only",
            "feed_history_sanitize_fallback_reason": "retry_exhausted",
            "unsafe_prompt": "must not be kept",
        }
    )

    assert stored["status"] == "completed"
    assert stored["feed_history_sanitize_fallback"] == "metadata_only"
    assert stored["feed_history_sanitize_fallback_reason"] == "retry_exhausted"
    assert "unsafe_prompt" not in stored


def test_stored_gateway_result_keeps_langgraph_v2_observability():
    stored = agent_runs._stored_gateway_result(
        {
            "status": "completed",
            "planner_results": {"feed": {"action_count": 1}},
            "independent_post_decision": {
                "available": True,
                "tick_probability": 0.28,
                "roll": 0.11,
                "roll_passed": True,
                "planner_decision": "write",
                "topic_key": "cosplay_preparation",
            },
            "independent_post_roll": 0.11,
            "independent_post_probability": 0.28,
            "independent_post_roll_passed": True,
            "independent_post_topic_key": "cosplay_preparation",
            "independent_post_topic_pool_size": 30,
            "independent_post_topic_prompt_count": 10,
            "action_budget_trim_summary": {"actions": {"reply": {"trimmed": 1}}},
            "write_task_summary": {"reply_task_count": 2, "reply_written_count": 1},
            "writer_results": {"reply_writer": {"missing_task_ids": ["reply-2"]}},
            "unsafe_prompt": "must not be kept",
        }
    )

    assert stored["planner_results"] == {"feed": {"action_count": 1}}
    assert stored["independent_post_decision"]["roll_passed"] is True
    assert stored["independent_post_roll"] == 0.11
    assert stored["independent_post_probability"] == 0.28
    assert stored["independent_post_roll_passed"] is True
    assert stored["independent_post_topic_key"] == "cosplay_preparation"
    assert stored["independent_post_topic_pool_size"] == 30
    assert stored["independent_post_topic_prompt_count"] == 10
    assert stored["action_budget_trim_summary"]["actions"]["reply"]["trimmed"] == 1
    assert stored["write_task_summary"]["reply_task_count"] == 2
    assert stored["writer_results"]["reply_writer"]["missing_task_ids"] == ["reply-2"]
    assert "unsafe_prompt" not in stored


def test_stored_gateway_result_preserves_llm_failure_metadata() -> None:
    diagnostics = [{"attempt": 2, "shape_hint": "natural_text_only"}]
    stored = agent_runs._stored_gateway_result(
        {
            "status": "failed",
            "failure_class": "DirectLlmJsonError",
            "failure_node": "PostWriter",
            "failure_lane": "post_writer",
            "parse_error_type": "JSONDecodeError",
            "attempt_count": 2,
            "validation_summary": [{"path": "post_body", "type": "missing"}],
            "json_error_diagnostics": diagnostics,
        }
    )

    assert stored["failure_node"] == "PostWriter"
    assert stored["failure_lane"] == "post_writer"
    assert stored["parse_error_type"] == "JSONDecodeError"
    assert stored["attempt_count"] == 2
    assert stored["validation_summary"] == [{"path": "post_body", "type": "missing"}]
    assert stored["json_error_diagnostics"] == diagnostics


def test_stored_gateway_result_preserves_provider_error_details() -> None:
    provider_error = {
        "provider_http_status": 429,
        "provider_status": "RESOURCE_EXHAUSTED",
        "provider_message": "Resource has been exhausted.",
        "details_present": False,
    }

    stored = agent_runs._stored_gateway_result(
        {
            "status": "failed",
            "failure_class": "DirectLlmError",
            "provider_error_hint": "provider_rate_limit",
            "provider_error": provider_error,
        }
    )

    assert stored["provider_error_hint"] == "provider_rate_limit"
    assert stored["provider_error"] == provider_error


def test_stored_gateway_result_preserves_relationship_review() -> None:
    stored = agent_runs._stored_gateway_result(
        {
            "status": "completed",
            "relationship_review": {
                "decision": "unfollow_watch",
                "target_character_id": "char-target",
                "reason_tag": "boundary",
            },
            "unrelated_debug_blob": {"drop": True},
        }
    )

    assert stored["relationship_review"] == {
        "decision": "unfollow_watch",
        "target_character_id": "char-target",
        "reason_tag": "boundary",
    }
    assert "unrelated_debug_blob" not in stored
