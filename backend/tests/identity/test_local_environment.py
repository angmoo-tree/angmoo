"""Real persistence/CAS leases and additive-upgrade preservation."""
from datetime import UTC, date, datetime, timedelta

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.core.calendar import day_bounds, local_period, wall_time
from app.domains.identity.models import InstallationIdentity, User
from app.domains.identity.models_environment import EnvironmentTimezoneChange, LocalEnvironment
from app.domains.identity.schemas import UserPreferencesUpdate
from app.domains.identity.schemas_environment import EnvironmentReport
from app.domains.identity.service.auth import update_user_preferences
from app.domains.identity.service.environment import EnvironmentConflict, read_environment, report_environment, snapshot
from app.runtime.persistence.model_registration import register_models

pytestmark = pytest.mark.usefixtures("deny_external_network")
NOW = datetime(2026, 10, 3, 0, 0, tzinfo=UTC)


@pytest.fixture
def database(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'environment.sqlite3'}")
    register_models().create_all(engine)
    with Session(engine, expire_on_commit=False) as db:
        db.add(User(id="owner", display_name="Synthetic owner"))
        db.flush()
        db.add(InstallationIdentity(singleton_key="local-installation", installation_id="synthetic-installation",
            owner_user_id="owner", bootstrap_state="claimed", claimed_at=NOW))
        db.commit()
        yield db
    engine.dispose()


def report(**changes):
    return EnvironmentReport(**{"client_id": "screen-one-000000", "expected_revision": 0, "sequence": 1,
        "preferred_language": "ja-JP", "timezone": "America/New_York", **changes})


def test_initial_defaults_failed_detector_and_last_valid(database):
    db = database
    first = read_environment(db, "owner", now=NOW)
    assert (first.memory_search_locale, first.timezone, first.environment_revision) == ("en", "UTC", 0)
    empty = report_environment(db, "owner", report(preferred_language=None, timezone=None), session_hash="session", now=NOW)
    assert empty.environment_revision == 0 and db.get(LocalEnvironment, "owner") is None
    good = report_environment(db, "owner", report(), session_hash="session", now=NOW)
    assert good.memory_search_locale == "ja-JP" and good.timezone == "America/New_York"
    assert snapshot(db, "owner").memory_search_locale == "ja-JP"
    repeat = report_environment(db, "owner", report(expected_revision=1, sequence=2, lease_token=good.lease_token), session_hash="session", now=NOW+timedelta(seconds=60))
    assert repeat.environment_revision == 1 and repeat.timezone_revision == 1
    assert read_environment(db, "owner", now=NOW+timedelta(minutes=5)).timezone == good.timezone


def test_first_active_screen_lease_sequence_revision_and_handover(database):
    db = database
    owned = report_environment(db, "owner", report(), session_hash="session-one", now=NOW)
    with pytest.raises(EnvironmentConflict, match="owned"):
        report_environment(db, "owner", report(client_id="screen-two-000000", expected_revision=1), session_hash="session-two", now=NOW+timedelta(seconds=119))
    with pytest.raises(EnvironmentConflict, match="sequence_stale"):
        report_environment(db, "owner", report(expected_revision=1, lease_token=owned.lease_token), session_hash="session-one", now=NOW)
    with pytest.raises(EnvironmentConflict, match="revision_conflict"):
        report_environment(db, "owner", report(sequence=2, lease_token=owned.lease_token), session_hash="session-one", now=NOW)
    handed = report_environment(db, "owner", report(client_id="screen-two-000000", expected_revision=1,
        preferred_language="ar-AE", timezone="Asia/Tokyo"), session_hash="session-two", now=NOW+timedelta(seconds=120))
    assert handed.memory_search_locale == "ar-AE" and handed.environment_revision == 2
    assert owned.lease_token != handed.lease_token
    frozen = snapshot(db, "owner").to_dict()
    assert frozen["memory_search_locale"] == "ar-AE"


@pytest.mark.parametrize("language", ["und", "x-private", "en_US", "zzzz-ZZ", "", "z"*81])
def test_invalid_detector_language_is_not_a_success(language):
    with pytest.raises(ValidationError):
        report(preferred_language=language)


@pytest.mark.parametrize("zone", ["Asia/Unknown", "../../UTC", "", "Mars/Colony"])
def test_invalid_zone(zone):
    with pytest.raises(ValidationError):
        report(timezone=zone)


def test_non_owner_cannot_read_or_mutate_environment(database):
    with pytest.raises(PermissionError, match="owner_required"):
        read_environment(database, "stranger")
    assert snapshot(database, "stranger").timezone == "UTC"


def test_ui_preference_partial_patch_is_separate_from_detected_language(database):
    db = database
    owner = db.get(User, "owner")
    update_user_preferences(db, owner, UserPreferencesUpdate(feed_content_filter="posts"))
    update_user_preferences(db, owner, UserPreferencesUpdate(ui_language="ko"))
    assert owner.feed_content_filter == "posts" and owner.ui_preference_revision == 1
    assert snapshot(db, "owner").memory_search_locale == "en"
    update_user_preferences(db, owner, UserPreferencesUpdate(ui_language="ko"))
    assert owner.ui_preference_revision == 1


def test_zone_transition_collaborator_is_atomic_and_failure_rolls_back(database):
    db = database
    observed = []
    def protect(session, owner_id, previous, target, instant, revision):
        observed.append((previous, target, revision, snapshot(session, owner_id).timezone))
        raise ValueError("synthetic_protection_failed")
    with pytest.raises(ValueError, match="protection_failed"):
        report_environment(db, "owner", report(), session_hash="session", now=NOW, on_timezone_change=protect)
    db.rollback()
    assert observed == [("UTC", "America/New_York", 1, "UTC")]
    assert snapshot(db, "owner").environment_revision == 0
    assert db.query(EnvironmentTimezoneChange).count() == 0


@pytest.mark.parametrize("day,hours", [(date(2026, 3, 8), 23), (date(2026, 11, 1), 25)])
def test_local_day_uses_two_boundaries_not_24_hours(day, hours):
    start, end = day_bounds(day, "America/New_York")
    assert (end-start).total_seconds() == hours*3600


def test_dst_gap_overlap_and_month_utc_bounds():
    assert wall_time(date(2026, 3, 8), 2, 30, "America/New_York") == datetime(2026, 3, 8, 7, tzinfo=UTC)
    assert wall_time(date(2026, 11, 1), 1, 30, "America/New_York") == datetime(2026, 11, 1, 5, 30, tzinfo=UTC)
    start, end = local_period(NOW, "Asia/Tokyo", "month")
    assert start == datetime(2026, 9, 30, 15, tzinfo=UTC)
    assert end == datetime(2026, 10, 31, 15, tzinfo=UTC)


def test_v26_to_v27_preserves_all_original_user_columns():
    from app.runtime.persistence.sqlite_schema import build_sqlite_v26_metadata, sqlite_schema_contract_digest, create_schema_version_table
    from app.runtime.migrations.sqlite_versions.registry import load_sqlite_manifest
    from app.runtime.migrations.sqlite_versions import environment_v27
    engine = create_engine("sqlite://")
    register_models()
    build_sqlite_v26_metadata().create_all(engine)
    with engine.begin() as connection:
        create_schema_version_table(connection)
        assert sqlite_schema_contract_digest(connection) == load_sqlite_manifest(26).schema_digest
        connection.exec_driver_sql("INSERT INTO users(id,display_name) VALUES('original','Keep original')")
        before = environment_v27.capture_delta(connection)
        environment_v27.upgrade(connection)
        environment_v27.verify_delta(connection, before)
        assert sqlite_schema_contract_digest(connection) == load_sqlite_manifest(27).schema_digest
    engine.dispose()


def test_typed_environment_context_keeps_canonical_demo_mutation_guard():
    from fastapi import HTTPException
    from starlette.requests import Request
    from app.domains.identity.dependencies import (
        AuthenticatedSessionContext, get_authenticated_user_context_allow_incomplete,
    )
    user = User(id="synthetic-demo", display_name="Original demo name")
    context = AuthenticatedSessionContext(user, None, False, "demo")
    read = Request({"type": "http", "method": "GET", "path": "/api/v1/auth/local/environment", "headers": []})
    assert get_authenticated_user_context_allow_incomplete(read, context) is context
    write = Request({"type": "http", "method": "POST", "path": "/api/v1/auth/local/environment", "headers": []})
    with pytest.raises(HTTPException) as failure:
        get_authenticated_user_context_allow_incomplete(write, context)
    assert failure.value.status_code == 403
