"""Owner-authenticated detector lease/CAS in the caller's short transaction."""
from datetime import UTC, datetime, timedelta
import secrets

from sqlalchemy import delete, select, update
from sqlalchemy.exc import IntegrityError
from app.core.sqlite_concurrency import is_sqlite_contention, run_sqlite_session_immediate, SqliteConcurrencyError

from app.contracts.environment import EnvironmentSnapshot, AccountingPeriod
from app.core.calendar import utc_instant, local_period
from zoneinfo import ZoneInfo
from app.core.ids import uuid7_string
from app.core.security import hash_token
from app.domains.identity.models import InstallationIdentity
from app.domains.identity.models_environment import EnvironmentTimezoneChange, LocalEnvironment
from app.domains.identity.schemas_environment import EnvironmentRead, EnvironmentReport

LEASE_SECONDS = 120


def delete_private_environment(db, owner_id: str) -> None:
    """Remove only this owner's detector data during canonical account deletion."""
    db.execute(delete(EnvironmentTimezoneChange).where(EnvironmentTimezoneChange.owner_id == owner_id))
    db.execute(delete(LocalEnvironment).where(LocalEnvironment.owner_id == owner_id))


class EnvironmentConflict(ValueError):
    pass


def lock_environment_admission(db, owner_id: str | None = None, *, exclusive: bool = False) -> None:
    """Fence environment activation without serializing independent PG jobs.

    Admissions share a row lock; configuration mutation keeps the no-op UPDATE.
    The writer's new MVCC version forces a stale admission snapshot to retry
    after waiting for activation, without changing any business revisions.
    Quota owners still enforce limits in the same serializable transaction.
    """
    postgres = db.get_bind().dialect.name == "postgresql"
    shared = postgres and not exclusive
    statement = (select(InstallationIdentity.singleton_key) if shared else update(InstallationIdentity))
    statement = statement.where(InstallationIdentity.bootstrap_state == "claimed")
    if owner_id is not None:
        statement = statement.where(InstallationIdentity.owner_user_id == owner_id)
    if shared:
        db.execute(statement.with_for_update(read=True)).all()
        return
    db.execute(statement.values(
        bootstrap_state=InstallationIdentity.bootstrap_state,
        updated_at=InstallationIdentity.updated_at,
    ))


def snapshot(db, owner_id: str) -> EnvironmentSnapshot:
    if owner_id is None:
        return EnvironmentSnapshot()
    row = db.get(LocalEnvironment, owner_id, populate_existing=True)
    return EnvironmentSnapshot(row.preferred_language or "en", row.timezone or "UTC",
        row.environment_revision, row.timezone_revision) if row else EnvironmentSnapshot()


def environment_confirmed(db, owner_id: str) -> bool:
    """Readiness for creating new locale-dependent defaults, not old data reads."""
    row = db.get(LocalEnvironment, owner_id, populate_existing=True)
    return bool(row and row.confirmed_at is not None)


def installation_snapshot(db) -> EnvironmentSnapshot:
    """Supported read for installation-wide limits and background work."""
    owner = db.scalar(select(InstallationIdentity.owner_user_id).where(
        InstallationIdentity.bootstrap_state == "claimed"))
    return snapshot(db, owner) if owner else EnvironmentSnapshot()


def accounting_period(db, owner_id: str | None, kind: str, *, now=None) -> AccountingPeriod:
    """Conservative union, with no writes and no quota-owned row access.

    Transition history and original UTC charge IDs make the protection restart
    safe. Each charge is counted once by its owner using an OR of these ranges.
    Rolling rate limits and provider billing never use this calendar contract.
    """
    now = utc_instant(now or datetime.now(UTC))
    env = snapshot(db, owner_id) if owner_id else installation_snapshot(db)
    current = local_period(now, env.timezone, kind)
    ranges = {current}
    available_at = current[1]
    if owner_id is None:
        owner_id = db.scalar(select(InstallationIdentity.owner_user_id).where(
            InstallationIdentity.bootstrap_state == "claimed"))
    if owner_id:
        events = db.scalars(select(EnvironmentTimezoneChange).where(
            EnvironmentTimezoneChange.owner_id == owner_id,
            EnvironmentTimezoneChange.effective_at >= now - timedelta(days=40),
            EnvironmentTimezoneChange.effective_at <= now).order_by(EnvironmentTimezoneChange.revision))
        for event in events:
            instant = utc_instant(event.effective_at)
            old = local_period(instant, event.previous_timezone, kind)
            new = local_period(instant, event.timezone, kind)
            expires = max(old[1], new[1])
            if now < expires:
                ranges.update((old, new))
                available_at = max(available_at, expires)
    # Merge overlapping intervals so owners that sum repository window counts
    # also cannot count the same physical charge twice.
    merged = []
    for start, end in sorted(ranges):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
        else:
            merged.append((start, end))
    local = now.astimezone(ZoneInfo(env.timezone))
    key = local.strftime("%Y-%m-%d" if kind == "day" else "%Y-%m")
    return AccountingPeriod(key, env.timezone, tuple(merged), available_at, ranges != {current}, current)


def read_environment(db, owner_id: str, *, now=None) -> EnvironmentRead:
    now = utc_instant(now or datetime.now(UTC))
    installation = db.scalar(select(InstallationIdentity).where(InstallationIdentity.owner_user_id == owner_id,
        InstallationIdentity.bootstrap_state == "claimed"))
    if installation is None:
        raise PermissionError("local_owner_required")
    row = db.get(LocalEnvironment, owner_id, populate_existing=True)
    current = snapshot(db, owner_id)
    live = bool(row and row.lease_expires_at and utc_instant(row.lease_expires_at) > now)
    return EnvironmentRead(installation_id=installation.installation_id,
        preferred_language=current.memory_search_locale, memory_search_locale=current.memory_search_locale,
        timezone=current.timezone, environment_revision=current.environment_revision,
        timezone_revision=current.timezone_revision, confirmed_at=row.confirmed_at if row else None,
        synchronization="active_owner" if live else "awaiting_detector", lease_expires_at=row.lease_expires_at if row else None)


class EnvironmentTemporarilyBusy(RuntimeError):
    pass


def report_environment(db, owner_id: str, data: EnvironmentReport, *, session_hash: str | None,
                       now=None, on_timezone_change=None) -> EnvironmentRead:
    """Own this request's UoW; caller may have only authenticated read state."""
    if db.new or db.dirty or db.deleted:
        raise SqliteConcurrencyError("environment_writer_requires_clean_session")
    db.rollback()
    try:
        return run_sqlite_session_immediate(db, lambda: apply_environment_report(db, owner_id, data,
            session_hash=session_hash, now=now, on_timezone_change=on_timezone_change), require_clean=True)
    except Exception as exc:
        if is_sqlite_contention(exc):
            raise EnvironmentTemporarilyBusy("environment_temporarily_busy") from exc
        raise


def apply_environment_report(db, owner_id: str, data: EnvironmentReport, *, session_hash: str | None,
                             now=None, on_timezone_change=None) -> EnvironmentRead:
    """Caller-owned canonical mutation and DTO; no nested commit or postcommit read."""
    now = utc_instant(now or datetime.now(UTC))
    lock_environment_admission(db, owner_id, exclusive=True)
    existing = read_environment(db, owner_id, now=now)
    if data.preferred_language is None and data.timezone is None:
        return existing
    row = db.get(LocalEnvironment, owner_id)
    if row is None:
        row = LocalEnvironment(owner_id=owner_id, installation_id=existing.installation_id)
        try:
            with db.begin_nested():
                db.add(row)
                db.flush()
        except IntegrityError:
            raise EnvironmentConflict("environment_revision_conflict") from None
    if data.expected_revision != row.environment_revision:
        raise EnvironmentConflict("environment_revision_conflict")
    live = bool(row.lease_expires_at and utc_instant(row.lease_expires_at) > now)
    same = (data.lease_token is not None and secrets.compare_digest(hash_token(data.lease_token), row.lease_token_hash or "")
        and row.lease_client_id == data.client_id and row.lease_session_hash == session_hash)
    if live and not same:
        raise EnvironmentConflict("environment_detector_owned")
    if same and data.sequence <= row.lease_sequence:
        raise EnvironmentConflict("environment_sequence_stale")
    token = data.lease_token if same else secrets.token_urlsafe(32)
    preferred = data.preferred_language if data.preferred_language is not None else row.preferred_language
    timezone = data.timezone if data.timezone is not None else row.timezone
    changed = preferred != row.preferred_language or timezone != row.timezone
    zone_changed = timezone is not None and timezone != row.timezone
    revision = row.environment_revision + int(changed)
    zone_revision = row.timezone_revision + int(zone_changed)
    # A transition collaborator protects usage and future schedules in this
    # transaction before the effective environment becomes visible.
    if zone_changed:
        if on_timezone_change is not None:
            on_timezone_change(db, owner_id, row.timezone or "UTC", timezone, now, zone_revision)
        db.add(EnvironmentTimezoneChange(id=uuid7_string(), owner_id=owner_id, revision=zone_revision,
            previous_timezone=row.timezone or "UTC", timezone=timezone, effective_at=now))
    changed_row = db.execute(update(LocalEnvironment).where(
        LocalEnvironment.owner_id == owner_id, LocalEnvironment.environment_revision == row.environment_revision,
        LocalEnvironment.lease_sequence == row.lease_sequence,
        LocalEnvironment.lease_token_hash == row.lease_token_hash,
    ).values(preferred_language=preferred, timezone=timezone, environment_revision=revision,
        timezone_revision=zone_revision, confirmed_at=now if data.preferred_language or data.timezone else row.confirmed_at,
        lease_client_id=data.client_id, lease_token_hash=hash_token(token), lease_session_hash=session_hash,
        lease_sequence=data.sequence, lease_expires_at=now + timedelta(seconds=LEASE_SECONDS)),
        execution_options={"synchronize_session": False})
    if changed_row.rowcount != 1:
        raise EnvironmentConflict("environment_revision_conflict")
    db.flush()
    db.expire_all()
    result = read_environment(db, owner_id, now=now)
    return result.model_copy(update={"lease_token": token})
