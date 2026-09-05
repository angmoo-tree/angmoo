from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

from app import models as _registered_models
from app.domains.routines import models
from app.domains.routines.service import run_backoff as agent_runs
from routine_posts.test_runtime import _seed
from routines.test_activity_persistence import _file_engine


def test_runtime_backoff_model_overloaded_first_occurrence() -> None:
    now = datetime(2026, 6, 14, 12, 0, tzinfo=UTC)

    backoff = agent_runs._runtime_error_backoff(
        RuntimeError("503 UNAVAILABLE high demand"), now=now
    )

    assert backoff is not None
    assert backoff.kind == "model_overloaded"
    assert backoff.retry_at == now + timedelta(minutes=10)
    assert backoff.repeated_overload is False


def test_runtime_backoff_model_overloaded_bad_gateway() -> None:
    now = datetime(2026, 6, 14, 12, 0, tzinfo=UTC)

    backoff = agent_runs._runtime_error_backoff(
        RuntimeError("502 Bad Gateway"), now=now
    )

    assert backoff is not None
    assert backoff.kind == "model_overloaded"
    assert backoff.retry_at == now + timedelta(minutes=10)
    assert backoff.repeated_overload is False


def test_runtime_backoff_model_overloaded_repeated_occurrence(monkeypatch) -> None:
    now = datetime(2026, 6, 14, 12, 0, tzinfo=UTC)
    monkeypatch.setattr(
        agent_runs,
        "_has_recent_model_overloaded_run",
        lambda *_args, **_kwargs: True,
    )

    backoff = agent_runs._runtime_error_backoff(
        RuntimeError("503 UNAVAILABLE high demand"),
        now=now,
        db=object(),
        character_id="char-1",
        credential_id="cred-1",
    )

    assert backoff is not None
    assert backoff.kind == "model_overloaded"
    assert backoff.retry_at == now + timedelta(minutes=30)
    assert backoff.repeated_overload is True


def test_runtime_backoff_keeps_rate_limit_and_timeout_separate() -> None:
    now = datetime(2026, 6, 14, 12, 0, tzinfo=UTC)

    rate_limit = agent_runs._runtime_error_backoff(
        RuntimeError("429 RESOURCE_EXHAUSTED quota exceeded"), now=now
    )
    timeout = agent_runs._runtime_error_backoff(RuntimeError("request timed out"), now=now)

    assert rate_limit is not None
    assert rate_limit.kind == "model_rate_limit"
    assert rate_limit.retry_at == now + timedelta(minutes=45)
    assert timeout is not None
    assert timeout.kind == "provider_timeout"
    assert timeout.retry_at == now + timedelta(minutes=10)


def test_gateway_result_indicates_model_overloaded() -> None:
    assert agent_runs._gateway_result_indicates_model_overloaded(
        {"failure_class": "model_overloaded"}
    )
    assert agent_runs._gateway_result_indicates_model_overloaded(
        {
            "reason": "모델 일시 과부하로 재시도 예정",
            "error": "503 UNAVAILABLE high demand",
        }
    )
    assert agent_runs._gateway_result_indicates_model_overloaded(
        {
            "reason": "model temporarily overloaded",
            "error": "502 Bad Gateway",
        }
    )
    assert not agent_runs._gateway_result_indicates_model_overloaded(
        {"failure_class": "provider_timeout", "error": "request timed out"}
    )


def _agent_run_for_overload_test(
    *,
    run_id: str,
    character_id: str,
    credential_id: str | None,
    created_at: datetime,
    failure_class: str = "model_overloaded",
) -> models.AgentRun:
    return models.AgentRun(
        id=run_id,
        user_id="user-1",
        character_id=character_id,
        credential_id=credential_id,
        agent_id="angmoo-1",
        session_key=f"session:{run_id}",
        status="deferred",
        created_at=created_at,
        gateway_result={"failure_class": failure_class},
    )


def test_recent_model_overload_detects_same_character_or_credential() -> None:
    engine = create_engine("sqlite:///:memory:")
    models.AgentRun.__table__.create(engine)
    now = datetime(2026, 6, 14, 12, 0, tzinfo=UTC)
    with Session(engine) as db:
        db.add_all(
            [
                _agent_run_for_overload_test(
                    run_id="run-character",
                    character_id="char-1",
                    credential_id="cred-other",
                    created_at=now - timedelta(minutes=30),
                ),
                _agent_run_for_overload_test(
                    run_id="run-credential",
                    character_id="char-other",
                    credential_id="cred-1",
                    created_at=now - timedelta(minutes=45),
                ),
            ]
        )
        db.commit()

        assert agent_runs._has_recent_model_overloaded_run(
            db,
            now=now,
            character_id="char-1",
            credential_id=None,
        )
        assert agent_runs._has_recent_model_overloaded_run(
            db,
            now=now,
            character_id=None,
            credential_id="cred-1",
        )


def test_recent_model_overload_ignores_old_or_non_overload_runs() -> None:
    engine = create_engine("sqlite:///:memory:")
    models.AgentRun.__table__.create(engine)
    now = datetime(2026, 6, 14, 12, 0, tzinfo=UTC)
    with Session(engine) as db:
        db.add_all(
            [
                _agent_run_for_overload_test(
                    run_id="run-old",
                    character_id="char-1",
                    credential_id="cred-1",
                    created_at=now - timedelta(hours=2, seconds=1),
                ),
                _agent_run_for_overload_test(
                    run_id="run-timeout",
                    character_id="char-1",
                    credential_id="cred-1",
                    created_at=now - timedelta(minutes=30),
                    failure_class="provider_timeout",
                ),
            ]
        )
        db.commit()

        assert not agent_runs._has_recent_model_overloaded_run(
            db,
            now=now,
            character_id="char-1",
            credential_id="cred-1",
        )


def test_overload_query_reads_pending_caller_result_without_committing(tmp_path):
    engine = _file_engine(tmp_path)
    now = datetime(2026, 9, 6, tzinfo=UTC)
    with Session(engine, expire_on_commit=False) as db:
        fixture = _seed(db)
        run = models.AgentRun(
            id="pending-overload-run",
            user_id=fixture.user.id,
            character_id=fixture.character.id,
            credential_id=fixture.credential.id,
            agent_id="overload-agent",
            session_key="overload-session",
            status="deferred",
            created_at=now - timedelta(minutes=5),
            gateway_result={"failure_class": "provider_timeout"},
        )
        db.add(run)
        db.commit()
        commits = []

        @event.listens_for(db, "after_commit")
        def committed(_session):
            commits.append(True)

        run.gateway_result = {"failure_class": "model_overloaded"}
        backoff = agent_runs._runtime_error_backoff(
            RuntimeError("503 UNAVAILABLE high demand"),
            now=now,
            db=db,
            character_id=fixture.character.id,
            credential_id=fixture.credential.id,
        )
        assert backoff.repeated_overload is True
        assert backoff.retry_at == now + timedelta(minutes=30)
        assert commits == []
        with Session(engine) as observer:
            saved = observer.get(models.AgentRun, run.id)
            assert saved.gateway_result == {"failure_class": "provider_timeout"}
        db.rollback()
        assert run.gateway_result == {"failure_class": "provider_timeout"}
        backoff = agent_runs._runtime_error_backoff(
            RuntimeError("503 UNAVAILABLE high demand"),
            now=now,
            db=db,
            character_id=fixture.character.id,
            credential_id=fixture.credential.id,
        )
        assert backoff.repeated_overload is False
        assert backoff.retry_at == now + timedelta(minutes=10)
        assert commits == []
    engine.dispose()
