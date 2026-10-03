"""Real SQLite admission races, transition unions and original file settlement."""
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
import json
from threading import Barrier

import pytest
from sqlalchemy.orm import Session

from identity.test_local_environment import database, report, NOW
from app.core.calendar_ledger import CalendarLedgerInvalid
from app.domains.identity.service.environment import accounting_period, report_environment
from app.domains.social.service import image_quota
from app.domains.social.repository.media import count_service_image_quota_used
from app.domains.social.exceptions import ServiceImageQuotaError
from app.integrations import azure_translation

pytestmark = pytest.mark.usefixtures("deny_external_network")


def change(db, zone, *, at, revision, sequence, token=None):
    return report_environment(db, "owner", report(timezone=zone, expected_revision=revision,
        sequence=sequence, lease_token=token), session_hash="calendar-session", now=at)


def configure_images(monkeypatch, limit):
    monkeypatch.setattr(image_quota.settings, "POLLINATIONS_SERVICE_FREE_IMAGES_PER_USER_DAY", limit)
    monkeypatch.setattr(image_quota.settings, "POLLINATIONS_SERVICE_MAX_IMAGES_PER_DAY", 0)


def reserve(db, at):
    return image_quota._reserve_service_image_quota(db, user_id="owner", character_id="synthetic-character",
        source="resident", at=at)


def test_last_remaining_reservation_has_one_winner_across_two_sqlite_sessions(database, monkeypatch):
    configure_images(monkeypatch, 1)
    engine = database.get_bind()
    gate = Barrier(2)
    def admission():
        with Session(engine) as db:
            gate.wait(timeout=5)
            try:
                return ("reserved", reserve(db, NOW).id)
            except ServiceImageQuotaError:
                db.rollback()
                return ("rejected", None)
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: admission(), range(2)))
    assert sorted(row[0] for row in results) == ["rejected", "reserved"]
    period = accounting_period(database, "owner", "day", now=NOW)
    assert count_service_image_quota_used(database, user_id="owner", quota_date=NOW.date(), period=period) == 1


def test_charge_and_original_reservation_are_not_reset_by_zone_round_trip(database, monkeypatch):
    configure_images(monkeypatch, 3)
    at = NOW + timedelta(hours=3)
    current = change(database, "Asia/Seoul", at=at, revision=0, sequence=1)
    rows = [reserve(database, at) for _ in range(3)]
    for row in rows[:2]:
        image_quota._finalize_service_image_quota(database, row, status="attached")
    current = change(database, "America/New_York", at=at+timedelta(seconds=1), revision=1, sequence=2, token=current.lease_token)
    current = change(database, "Asia/Seoul", at=at+timedelta(seconds=2), revision=2, sequence=3, token=current.lease_token)
    period = accounting_period(database, "owner", "day", now=at+timedelta(seconds=3))
    # The initial UTC -> Seoul activation also protects the original UTC day.
    assert period.protected and period.allowance_available_at == datetime(2026, 10, 4, 0, tzinfo=UTC)
    assert count_service_image_quota_used(database, user_id="owner", quota_date=at.date(), period=period) == 3
    with pytest.raises(ServiceImageQuotaError):
        reserve(database, at+timedelta(seconds=4))
    database.rollback()
    image_quota._finalize_service_image_quota(database, rows[2], status="outcome_unknown")
    with pytest.raises(ServiceImageQuotaError):
        reserve(database, at+timedelta(seconds=5))
    database.rollback()
    image_quota._finalize_service_image_quota(database, rows[2], status="released")
    last = reserve(database, at+timedelta(seconds=6))
    assert last.id not in {row.id for row in rows}
    later = period.allowance_available_at
    expired = accounting_period(database, "owner", "day", now=later)
    assert not expired.protected
    assert count_service_image_quota_used(database, user_id="owner", quota_date=later.date(), period=expired) == 0


def test_zone_update_competes_with_last_remaining_admission_without_extra_budget(database, monkeypatch):
    configure_images(monkeypatch, 2)
    owned = change(database, "Asia/Seoul", at=NOW, revision=0, sequence=1)
    reserve(database, NOW)
    engine, gate = database.get_bind(), Barrier(3)
    def operation(kind):
        with Session(engine) as db:
            gate.wait(timeout=5)
            if kind == "zone":
                change(db, "America/New_York", at=NOW+timedelta(seconds=1), revision=1, sequence=2, token=owned.lease_token)
                return "changed"
            try:
                reserve(db, NOW+timedelta(seconds=1))
                return "reserved"
            except ServiceImageQuotaError:
                db.rollback()
                return "rejected"
    with ThreadPoolExecutor(max_workers=3) as executor:
        result = list(executor.map(operation, ("zone", "quota-one", "quota-two")))
    assert sorted(result) == ["changed", "rejected", "reserved"]
    period = accounting_period(database, "owner", "day", now=NOW+timedelta(seconds=2))
    assert count_service_image_quota_used(database, user_id="owner", quota_date=NOW.date(), period=period) == 2


def test_translation_original_month_settlement_guard_expiry_and_unknown_are_durable(database, monkeypatch, tmp_path):
    monkeypatch.setattr(azure_translation.settings, "MEDIA_ROOT", str(tmp_path))
    monkeypatch.setattr(azure_translation.settings, "TRANSLATION_MONTHLY_CHAR_LIMIT", 3)
    at = datetime(2026, 3, 31, 14, tzinfo=UTC)
    current = change(database, "Asia/Seoul", at=at, revision=0, sequence=1)
    old = accounting_period(database, "owner", "month", now=at)
    first = azure_translation._reserve_translation_chars(2, period=old)
    second = azure_translation._reserve_translation_chars(1, period=old)
    azure_translation._settle_translation_chars(first, "consumed")
    current = change(database, "America/New_York", at=at+timedelta(seconds=1), revision=1, sequence=2, token=current.lease_token)
    new = accounting_period(database, "owner", "month", now=at+timedelta(hours=2))
    assert new.protected and new.allowance_available_at == datetime(2026, 4, 1, 4, tzinfo=UTC)
    assert azure_translation._reserve_translation_chars(1, period=new) is None
    azure_translation._release_translation_chars(second)
    third = azure_translation._reserve_translation_chars(1, period=new)
    assert third and third != second
    azure_translation._settle_translation_chars(third, "unknown")
    azure_translation._release_translation_chars(third)
    assert azure_translation._reserve_translation_chars(1, period=new) is None
    expired = accounting_period(database, "owner", "month", now=new.allowance_available_at)
    assert not expired.protected
    fourth = azure_translation._reserve_translation_chars(3, period=expired)
    assert fourth
    # A delayed old-month settlement cannot decrement the current month's bucket.
    azure_translation._release_translation_chars(second)
    usage = json.loads((tmp_path / "translation-usage.json").read_text())
    assert usage["ledger"]["buckets"][usage["reservations"][fourth]["bucket"]]["count"] == 3
    assert usage["reservations"][first]["status"] == "consumed"
    assert usage["reservations"][third]["status"] == "unknown"


@pytest.mark.parametrize("failure", ["corrupt", "known_missing"])
def test_translation_unavailable_history_never_authorizes_zero_reset(monkeypatch, tmp_path, failure):
    monkeypatch.setattr(azure_translation.settings, "MEDIA_ROOT", str(tmp_path))
    monkeypatch.setattr(azure_translation.settings, "TRANSLATION_MONTHLY_CHAR_LIMIT", 5)
    path = tmp_path / "translation-usage.json"
    if failure == "corrupt":
        path.write_text("invalid history", encoding="utf-8")
    else:
        path.with_suffix(path.suffix+".initialized").touch()
    assert azure_translation._reserve_translation_chars(1) is None
    with pytest.raises(CalendarLedgerInvalid):
        azure_translation._translation_ledger(path)
