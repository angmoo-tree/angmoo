import asyncio
from datetime import UTC, datetime, timedelta
import pytest
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker
from app.core.result_journal import ResultJournal, ResultJournalError
from app.domains.memory.models.items import MemoryItem
from app.domains.relationships.models.personalization import RelationshipReviewWork
from app.domains.relationships.models.social import RelationshipState
from app.domains.relationships.service.daily_review import plan_review, run_review_step, apply_review
from test_relationship_daily_review import Provider, References
from runtime.test_activity_settlement_sqlite import _fixture


def setup(tmp_path):
    engine, _, identities = _fixture(tmp_path)
    factory = sessionmaker(engine, expire_on_commit=False)
    world, actor, target, _ = identities[0]
    with factory() as db:
        from app.domains.worlds.models import World
        owner = db.get(World, world).owner_user_id
        item = MemoryItem(id="review-source", owner_id=owner, world_id=world,
            subject_world_character_id=actor, memory_kind="AUTOBIOGRAPHICAL_EVENT", summary="Saved experience", confidence=1, salience=1)
        db.add(item); db.flush()
        row = plan_review(db, world_id=world, actor_id=actor, target_id=target,
            period_key="2026-10-16", base={}, memories=[dict(memory_id=item.id, summary=item.summary,
                digest="a"*64, source_refs=[], occurred_at=datetime.now(UTC).isoformat())])
        db.commit()
        identifier = row.id
    return engine, factory, world, identifier, ResultJournal(tmp_path/"private", "relationship-review")


@pytest.mark.parametrize("change", ["none", "lease_expired", "new_attempt", "manifest"])
def test_response_survives_real_writer_busy_and_restart_without_api(tmp_path, change):
    engine, factory, world, identifier, journal = setup(tmp_path)
    held = []
    class BusyProvider(Provider):
        async def review(self, *args, **kwargs):
            result = await super().review(*args, **kwargs)
            connection = engine.connect(); connection.exec_driver_sql("BEGIN IMMEDIATE")
            held.append(connection)
            return result
    provider = BusyProvider()
    def run(buffer=None):
        return asyncio.run(run_review_step(factory, work_id=identifier,
            references_factory=lambda db: References(), provider_factory=lambda base: provider,
            journal=journal, received=buffer))
    assert run({}) == "local_result_pending"
    assert len(provider.calls) == 1 and journal.read(world, identifier)["result_digest"]
    held[0].rollback(); held[0].close()
    with factory() as db:
        row = db.get(RelationshipReviewWork, identifier)
        assert row.status == "running" and row.attempts == 1
        if change == "lease_expired":
            row.lease_until = datetime.now(UTC)-timedelta(seconds=1)
        elif change == "new_attempt":
            row.attempts += 1; row.lease_token = "new-owner"
        elif change == "manifest":
            row.manifest_digest = "b"*64
        db.commit()
    assert run({}) == ("lease_lost" if change in {"new_attempt", "manifest"} else "ready")
    assert len(provider.calls) == 1 and journal.read(world, identifier) is None
    if change in {"none", "lease_expired"}:
        with factory() as db:
            assert apply_review(db, work_id=identifier, references=References(), now=datetime.now(UTC)) == "applied"
            db.commit()
            version = db.scalar(select(RelationshipState.version))
            assert apply_review(db, work_id=identifier, references=References(), now=datetime.now(UTC)) == "applied"
            assert db.scalar(select(RelationshipState.version)) == version
    engine.dispose()


def test_erasure_fences_late_result_and_keeps_only_content_free_marker(tmp_path):
    journal = ResultJournal(tmp_path, "relationship-review")
    journal.write("world-a", "work", {"result": "private"})
    journal.write("world-b", "work", {"result": "other"})
    journal.close_world("world-a")
    with pytest.raises(ResultJournalError, match="world_closed"):
        journal.write("world-a", "work", {"result": "late"})
    assert journal.read("world-a", "work") is None
    assert journal.read("world-b", "work") == {"result": "other"}
    assert not any("private" in p.read_text() for p in (journal.root/ journal._key("world-a")).glob("*.json"))


def test_journal_corruption_quota_and_oversize_are_not_retry_admission(tmp_path):
    journal = ResultJournal(tmp_path, "relationship-review")
    journal.MAX_FILES = 1
    journal.write("w", "a", {"result": "one"})
    with pytest.raises(ResultJournalError, match="capacity"):
        journal.write("w", "b", {"result": "two"})
    path = journal.root/journal._key("w")/(journal._key("a")+".json")
    path.write_text("broken")
    with pytest.raises(ResultJournalError, match="corrupt"):
        journal.read("w", "a")
    journal.remove_item("a")
    assert not path.exists()


def test_received_result_capacity_does_not_discard_buffer_or_resubmit(tmp_path, monkeypatch):
    engine, factory, world, identifier, journal = setup(tmp_path)
    provider, received = Provider(), {}
    write = journal.write
    unavailable = [True]
    def full(world, item, payload):
        if unavailable[0] and "result" in payload:
            raise ResultJournalError("result_journal_capacity")
        write(world, item, payload)
    monkeypatch.setattr(journal, "write", full)
    def run():
        return asyncio.run(run_review_step(factory, work_id=identifier,
            references_factory=lambda db: References(), provider_factory=lambda base: provider,
            journal=journal, received=received))
    assert run() == run() == "storage_retry_wait"
    assert identifier in received and len(provider.calls) == 1
    unavailable[0] = False
    assert run() == "ready"
    assert len(provider.calls) == 1 and not received and journal.read(world, identifier) is None
    engine.dispose()


def test_corrupt_received_record_never_becomes_a_new_provider_request(tmp_path):
    engine, factory, world, identifier, journal = setup(tmp_path)
    journal.write(world, identifier, {"result": "synthetic"})
    path = journal.root/journal._key(world)/(journal._key(identifier)+".json")
    path.write_text("corrupt")
    provider = Provider()
    for expected in ("result_journal_invalid", "needs_attention"):
        assert asyncio.run(run_review_step(factory, work_id=identifier,
            references_factory=lambda db: References(), provider_factory=lambda base: provider,
            journal=journal, received={})) == expected
    assert not provider.calls
    engine.dispose()


def test_submission_without_durable_result_stays_unknown_even_if_marker_is_missing(tmp_path):
    engine, factory, world, identifier, journal = setup(tmp_path)
    with factory() as db:
        row = db.get(RelationshipReviewWork, identifier)
        row.status, row.attempts, row.lease_token = "running", 1, "sent-attempt"
        db.commit()
    journal.write(world, identifier, {"lease": "sent-attempt", "attempt": 1})
    provider = Provider()
    def run():
        return asyncio.run(run_review_step(factory, work_id=identifier,
            references_factory=lambda db: References(), provider_factory=lambda base: provider, journal=journal))
    assert run() == run() == "outcome_unknown"
    journal.remove(world, identifier)
    assert run() == "outcome_unknown"
    assert not provider.calls
    engine.dispose()
