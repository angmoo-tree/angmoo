from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
import os
from threading import Barrier
from time import sleep
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, delete, inspect, select, text
from sqlalchemy.orm import Session

from app import models, schemas
from app.cruds import community as community_crud
from app.services import agents as agent_service
from app.services import auth as auth_service
from app.services import community_abuse_quota
from app.services import external_auth_verification
from app.services import local_bot_quota
from app.services import login_throttle
from app.services import lore_parser_quota


DATABASE_URL = os.getenv("SECURITY_CONCURRENCY_DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not DATABASE_URL,
    reason="SECURITY_CONCURRENCY_DATABASE_URL is required",
)


def _engine():
    assert DATABASE_URL is not None
    return create_engine(
        DATABASE_URL,
        pool_pre_ping=True,
        pool_size=60,
        max_overflow=0,
    )


def test_security_migration_schema_contract() -> None:
    engine = _engine()
    inspector = inspect(engine)
    expected_tables = {
        "auth_external_verification_reservations",
        "auth_google_signup_grants",
        "auth_login_throttle_buckets",
        "community_mutation_quota_buckets",
        "local_bot_action_quota_buckets",
        "local_bot_read_quota_buckets",
        "lore_parser_leases",
    }
    assert expected_tables.issubset(set(inspector.get_table_names()))
    assert {
        item["name"]
        for item in inspector.get_check_constraints(
            "local_bot_action_quota_buckets"
        )
    } == {
        "ck_local_bot_action_quota_label",
        "ck_local_bot_action_quota_used_nonnegative",
    }
    assert {
        item["name"]
        for item in inspector.get_check_constraints("auth_login_throttle_buckets")
    } == {
        "ck_auth_login_throttle_failure_nonnegative",
        "ck_auth_login_throttle_scope",
    }
    with engine.connect() as connection:
        assert (
            connection.scalar(text("SELECT version_num FROM alembic_version"))
            == "20260726_0066"
        )


def test_local_bot_quotas_are_atomic_across_postgres_sessions() -> None:
    engine = _engine()
    suffix = uuid4().hex
    user_id = f"user-security-{suffix}"
    character_id = f"char-security-{suffix}"
    local_key_id = f"key-security-{suffix}"
    now = datetime.now(UTC)
    barrier = Barrier(2)

    with Session(engine) as db:
        db.add(
            models.User(
                id=user_id,
                email=f"{suffix}@example.invalid",
                display_name=user_id,
                display_name_normalized=user_id,
                profile_setup_completed=True,
                feed_content_filter="all",
            )
        )
        db.add(
            models.Character(
                id=character_id,
                owner_id=user_id,
                name=character_id,
                handle=f"security_{suffix[:20]}",
                one_liner="",
                personality="",
                speech_style="",
                worldview="",
                topic_preferences="",
                safety_rules="",
                persona_summary="security concurrency fixture",
            )
        )
        db.add(
            models.AgentLocalKey(
                id=local_key_id,
                owner_id=user_id,
                character_id=character_id,
                token_hash=(suffix * 2)[:64],
                token_prefix="angmoo_local_security",
                enabled=True,
            )
        )
        db.commit()

    def attempt() -> str:
        with Session(engine) as db:
            barrier.wait()
            quota = local_bot_quota.lock_action_quota(
                db,
                character_id=character_id,
                labels=("reply",),
                now=now,
            )
            try:
                quota.ensure_allowed(
                    "reply",
                    cooldown=timedelta(0),
                    max_per_day=1,
                    message="reply limited",
                )
            except local_bot_quota.QuotaExceeded:
                db.rollback()
                return "limited"
            quota.consume(("reply",))
            sleep(0.1)
            db.commit()
            return "allowed"

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = sorted(executor.map(lambda _index: attempt(), range(2)))
        assert results == ["allowed", "limited"]
        with Session(engine) as db:
            row = db.scalar(
                select(models.LocalBotActionQuotaBucket).where(
                    models.LocalBotActionQuotaBucket.character_id == character_id,
                    models.LocalBotActionQuotaBucket.action_label == "reply",
                )
            )
            assert row is not None
            assert row.used_count == 1

        read_barrier = Barrier(2)

        def read_attempt() -> str:
            with Session(engine) as db:
                read_barrier.wait()
                try:
                    local_bot_quota.consume_read(
                        db,
                        local_key_id=local_key_id,
                        now=now,
                        limit=1,
                        window=timedelta(minutes=1),
                    )
                except local_bot_quota.QuotaExceeded:
                    db.rollback()
                    return "limited"
                return "allowed"

        with ThreadPoolExecutor(max_workers=2) as executor:
            read_results = sorted(executor.map(lambda _index: read_attempt(), range(2)))
        assert read_results == ["allowed", "limited"]
        with Session(engine) as db:
            read_row = db.get(models.LocalBotReadQuotaBucket, local_key_id)
            assert read_row is not None
            assert read_row.used_count == 1
    finally:
        with Session(engine) as db:
            db.execute(
                delete(models.LocalBotReadQuotaBucket).where(
                    models.LocalBotReadQuotaBucket.local_key_id == local_key_id
                )
            )
            db.execute(
                delete(models.LocalBotActionQuotaBucket).where(
                    models.LocalBotActionQuotaBucket.character_id == character_id
                )
            )
            db.execute(
                delete(models.AgentLocalKey).where(
                    models.AgentLocalKey.id == local_key_id
                )
            )
            db.execute(
                delete(models.Character).where(models.Character.id == character_id)
            )
            db.execute(delete(models.User).where(models.User.id == user_id))
            db.commit()


def test_login_throttle_is_atomic_across_postgres_sessions() -> None:
    engine = _engine()
    suffix = uuid4().hex
    email = f"{suffix}@example.invalid"
    source = f"security-source-{suffix}"
    now = datetime.now(UTC)

    with Session(engine) as db:
        throttle = login_throttle.lock_login_throttle(
            db,
            normalized_email=email,
            source=source,
            now=now,
        )
        for row in throttle.rows.values():
            row.failure_count = 4
            row.window_started_at = now
            row.blocked_until = None
        subject_hashes = [row.subject_hash for row in throttle.rows.values()]
        db.commit()

    barrier = Barrier(2)

    def attempt() -> str:
        with Session(engine) as db:
            barrier.wait()
            throttle = login_throttle.lock_login_throttle(
                db,
                normalized_email=email,
                source=source,
                now=now,
            )
            if throttle.retry_after_seconds() is not None:
                db.rollback()
                return "limited"
            throttle.record_failure()
            sleep(0.1)
            db.commit()
            return "recorded"

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = sorted(executor.map(lambda _index: attempt(), range(2)))
        assert results == ["limited", "recorded"]
        with Session(engine) as db:
            rows = list(
                db.scalars(
                    select(models.AuthLoginThrottleBucket).where(
                        models.AuthLoginThrottleBucket.subject_hash.in_(subject_hashes)
                    )
                )
            )
            assert len(rows) == 2
            assert {row.failure_count for row in rows} == {5}
            assert all(row.blocked_until is not None for row in rows)
    finally:
        with Session(engine) as db:
            db.execute(
                delete(models.AuthLoginThrottleBucket).where(
                    models.AuthLoginThrottleBucket.subject_hash.in_(subject_hashes)
                )
            )
            db.commit()


def test_google_verification_reservation_is_atomic_across_postgres_sessions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = _engine()
    source = f"google-security-{uuid4().hex}"
    now = datetime.now(UTC)
    monkeypatch.setattr(
        external_auth_verification.settings,
        "GOOGLE_AUTH_VERIFY_SOURCE_PER_MINUTE",
        1,
    )
    monkeypatch.setattr(
        external_auth_verification.settings,
        "GOOGLE_AUTH_VERIFY_SOURCE_PER_15_MINUTES",
        10,
    )
    monkeypatch.setattr(
        external_auth_verification.settings,
        "GOOGLE_AUTH_VERIFY_GLOBAL_PER_MINUTE",
        10,
    )
    monkeypatch.setattr(
        external_auth_verification.settings,
        "GOOGLE_AUTH_VERIFY_MAX_IN_FLIGHT",
        10,
    )
    attempt_count = 12
    barrier = Barrier(attempt_count)

    def attempt() -> str:
        with Session(engine) as db:
            barrier.wait()
            try:
                reservation = (
                    external_auth_verification.reserve_google_verification(
                        db,
                        source=source,
                        now=now,
                    )
                )
            except external_auth_verification.ExternalVerificationRateLimitedError:
                return "limited"
            external_auth_verification.complete_google_verification(
                db,
                reservation.id,
                outcome_class="invalid",
                now=now,
            )
            return "allowed"

    with ThreadPoolExecutor(max_workers=attempt_count) as executor:
        results = list(executor.map(lambda _index: attempt(), range(attempt_count)))
    assert results.count("allowed") == 1
    assert results.count("limited") == attempt_count - 1


def test_google_signup_grant_is_consumed_once_across_postgres_sessions() -> None:
    engine = _engine()
    jti = uuid4().hex
    now = datetime.now(UTC)
    with Session(engine) as db:
        db.add(
            models.AuthGoogleSignupGrant(
                jti_hash=auth_service._pending_signup_jti_hash(jti),
                created_at=now,
                expires_at=now + timedelta(minutes=10),
            )
        )
        db.commit()
    attempt_count = 12
    barrier = Barrier(attempt_count)

    def attempt() -> str:
        with Session(engine) as db:
            barrier.wait()
            try:
                grant = auth_service._lock_pending_google_signup_grant(
                    db,
                    jti=jti,
                )
            except auth_service.InvalidGoogleSignupTokenError:
                return "rejected"
            grant.consumed_at = datetime.now(UTC)
            sleep(0.1)
            db.commit()
            return "consumed"

    with ThreadPoolExecutor(max_workers=attempt_count) as executor:
        results = list(executor.map(lambda _index: attempt(), range(attempt_count)))
    assert results.count("consumed") == 1
    assert results.count("rejected") == attempt_count - 1


def test_direct_user_like_is_unique_across_postgres_sessions() -> None:
    engine = _engine()
    suffix = uuid4().hex
    user_id = f"user-like-{suffix}"
    post_id = f"post-like-{suffix}"
    with Session(engine) as db:
        user = models.User(
            id=user_id,
            email=f"{suffix}@example.invalid",
            display_name=user_id,
            display_name_normalized=user_id,
            profile_setup_completed=True,
        )
        db.add(user)
        db.add(
            models.Post(
                id=post_id,
                author_user_id=user_id,
                author_name=user_id,
                title="synthetic",
                body="synthetic",
                post_type="text",
            )
        )
        db.commit()
    attempt_count = 50
    barrier = Barrier(attempt_count)

    def attempt() -> bool:
        with Session(engine) as db:
            user = db.get(models.User, user_id)
            post = db.get(models.Post, post_id)
            assert user is not None and post is not None
            barrier.wait()
            _like, created = community_crud.like_post(
                db,
                post=post,
                user=user,
                character=None,
            )
            return created

    with ThreadPoolExecutor(max_workers=attempt_count) as executor:
        results = list(executor.map(lambda _index: attempt(), range(attempt_count)))
    assert results.count(True) == 1
    assert results.count(False) == attempt_count - 1
    with Session(engine) as db:
        rows = list(
            db.scalars(
                select(models.PostLike).where(
                    models.PostLike.post_id == post_id,
                    models.PostLike.user_id == user_id,
                    models.PostLike.character_id.is_(None),
                )
            )
        )
        assert len(rows) == 1


def test_community_reply_quota_is_atomic_across_postgres_sessions() -> None:
    engine = _engine()
    user_id = f"community-quota-{uuid4().hex}"
    now = datetime.now(UTC)
    with Session(engine) as db:
        for _ in range(9):
            community_abuse_quota.consume(
                db,
                user_id=user_id,
                action="reply",
                now=now,
            )
            db.commit()
    barrier = Barrier(2)

    def attempt() -> str:
        with Session(engine) as db:
            barrier.wait()
            try:
                community_abuse_quota.consume(
                    db,
                    user_id=user_id,
                    action="reply",
                    now=now,
                )
            except community_abuse_quota.CommunityQuotaExceeded:
                return "limited"
            sleep(0.1)
            db.commit()
            return "allowed"

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = sorted(executor.map(lambda _index: attempt(), range(2)))
    assert results == ["allowed", "limited"]


def test_lore_parser_global_capacity_is_atomic_across_postgres_sessions() -> None:
    engine = _engine()
    attempt_count = 4
    barrier = Barrier(attempt_count)

    def attempt(index: int) -> str:
        with Session(engine) as db:
            barrier.wait()
            try:
                with lore_parser_quota.parser_lease(
                    db,
                    user_id=f"lore-user-{index}-{uuid4().hex}",
                ):
                    sleep(0.2)
                    return "allowed"
            except lore_parser_quota.LoreParserCapacityError:
                return "limited"

    with ThreadPoolExecutor(max_workers=attempt_count) as executor:
        results = list(executor.map(attempt, range(attempt_count)))
    assert results.count("allowed") == lore_parser_quota.GLOBAL_ACTIVE_LIMIT
    assert (
        results.count("limited")
        == attempt_count - lore_parser_quota.GLOBAL_ACTIVE_LIMIT
    )


def test_agent_creation_quota_is_atomic_across_postgres_sessions() -> None:
    engine = _engine()
    suffix = uuid4().hex
    user_id = f"user-agent-quota-{suffix}"
    with Session(engine) as db:
        db.add(
            models.User(
                id=user_id,
                email=f"{suffix}@example.invalid",
                display_name=user_id,
                display_name_normalized=user_id,
                profile_setup_completed=True,
            )
        )
        db.commit()
    barrier = Barrier(12)

    def attempt(index: int) -> str:
        with Session(engine) as db:
            user = db.get(models.User, user_id)
            assert user is not None
            barrier.wait()
            try:
                agent_service.create_agent(
                    db,
                    user,
                    schemas.AgentCreate(
                        execution_mode="local",
                        name=f"local-{index}",
                        handle=f"local_{suffix[:12]}_{index}",
                    ),
                )
            except agent_service.AgentLimitError:
                db.rollback()
                return "limited"
            return "created"

    with ThreadPoolExecutor(max_workers=12) as executor:
        results = list(executor.map(attempt, range(12)))
    assert results.count("created") == agent_service.MAX_LOCAL_AGENTS_PER_USER
    assert results.count("limited") == 12 - agent_service.MAX_LOCAL_AGENTS_PER_USER
