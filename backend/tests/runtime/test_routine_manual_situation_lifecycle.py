"""Canonical publication, durable memory and replay for claimed owner replies."""
import asyncio
from dataclasses import replace
from datetime import UTC, datetime
import pytest

from sqlalchemy import select, func, event

from model_fixture_support import models
from app.domains.memory.models.activity_situation import MemorySituationReceipt
from app.domains.memory.models.items import MemoryItem
from app.domains.memory.repository.situation_validation import restore_context
from app.runtime.memory.situation_sources import SituationSources
from runtime.routine_manual_fixture import manual_routine, run_routine, apply_situations


@pytest.mark.parametrize("manual_routine", [False], indirect=True)
def test_real_routine_publishes_applies_and_replays_consumed_comment(manual_routine, monkeypatch):
    case = manual_routine
    lane, state, adapter = asyncio.run(run_routine(case, monkeypatch))
    assert state["result"]["public_action_count"] == 1, state["result"]
    assert len(adapter.requests) == 1
    case.db.refresh(case.candidate)
    assert case.candidate.status == "consumed"
    receipt = case.db.scalars(select(MemorySituationReceipt)).one()
    assert receipt.state == "pending", receipt.error_code
    context = restore_context(case.db, receipt)
    entry = next(s for s in context.sources if "/routine/source_events/" in s.payload_path)
    assert entry.source_type == "REPLY" and entry.source_id == case.reply.id
    assert SituationSources(case.db).validate(context, entry, now=datetime.now(UTC)).state == "available"
    apply_situations(case)
    assert receipt.state == "applied", receipt.error_code
    assert case.db.scalar(select(func.count()).select_from(MemoryItem)) == 1
    item = case.db.get(MemoryItem, receipt.applied_item_id)
    from memory.test_activity_situation_recall import readers
    from app.domains.memory.repository.episode_packets import SqlAlchemyEpisodePackets
    from app.runtime.memory.episode_details import RuntimeEpisodeDetailReader
    reader, request, ranked, _ = readers(case.db, context.snapshot.scope, item)
    reader.clock = lambda: datetime.now(UTC)
    accepted = reader.revalidate(request, (ranked,))
    assert len(accepted) == 1 and reader.hydrate(request, accepted).records
    packets = SqlAlchemyEpisodePackets(case.db, detail_reader=RuntimeEpisodeDetailReader(case.db)).read(
        scope=context.snapshot.scope, item_ids=(item.id,), now=datetime.now(UTC))
    # Routine's published post is the detail core. The owner's input remains
    # a validated background/privacy dependency, not an additional detail core.
    published = case.db.get(models.Post, context.result_sources[0].source_id)
    assert packets and any(source.text == published.body and source.status == "verified"
        for packet in packets for unit in packet.units for source in unit.sources)
    assert not any(source.reference == f"REPLY:{case.reply.id}"
        for packet in packets for unit in packet.units for source in unit.sources)
    assert reader.revalidate(replace(request, scope=replace(request.scope, world_id="another-world")), (ranked,)) == ()
    assert reader.revalidate(request, (replace(ranked, version=999),)) == ()
    before = case.db.scalar(select(func.count()).select_from(models.Post))
    lane.prepared = None  # Reattach saved IDs, as after a process restart.
    asyncio.run(lane.guard({**state, "stage": "Execute"}))
    repeated = asyncio.run(lane.execute(state))
    assert repeated["executions"][0]["routine_outcome"] == "REUSED_SUCCESS"
    assert case.db.scalar(select(func.count()).select_from(models.Post)) == before
    assert case.db.scalar(select(func.count()).select_from(MemorySituationReceipt)) == 1
    assert len(adapter.requests) == 1


@pytest.mark.parametrize("manual_routine", [False], indirect=True)
@pytest.mark.parametrize("change", ["deleted", "hidden", "private", "body", "block"])
def test_consumed_source_is_rechecked_and_summary_is_not_rewritten(manual_routine, monkeypatch, change):
    case = manual_routine
    asyncio.run(run_routine(case, monkeypatch))
    receipt = case.db.scalars(select(MemorySituationReceipt)).one()
    context = restore_context(case.db, receipt)
    source = next(s for s in context.sources if "/routine/source_events/" in s.payload_path)
    apply_situations(case)
    item = case.db.get(MemoryItem, receipt.applied_item_id)
    summary = item.summary
    if change == "deleted": case.reply.deleted_at = datetime.now(UTC)
    elif change == "hidden": case.reply.report_hidden_at = datetime.now(UTC)
    elif change == "private": case.reply.visibility = "private"
    elif change == "body": case.reply.body = "A changed suggestion after delivery."
    else:
        case.db.add(models.WorldCharacterBlock(id="later-block", world_id=case.seeded.world.id,
            blocker_world_character_id=case.owner.id, blocked_world_character_id=case.seeded.world_character.id))
    case.db.commit()
    case.db.expire_all()
    access = SituationSources(case.db).validate(context, source, now=datetime.now(UTC))
    assert access.state != "available"
    from app.domains.memory.repository.episode_packets import SqlAlchemyEpisodePackets
    from app.runtime.memory.episode_details import RuntimeEpisodeDetailReader
    packets = SqlAlchemyEpisodePackets(case.db, detail_reader=RuntimeEpisodeDetailReader(case.db)).read(
        scope=context.snapshot.scope, item_ids=(item.id,), now=datetime.now(UTC))
    assert not any(s.text == "Try a cooler temperature for the next experiment."
        for p in packets for u in p.units for s in u.sources)
    assert case.db.get(MemoryItem, item.id).summary == summary


@pytest.mark.parametrize("manual_routine", [False], indirect=True)
def test_receipt_insert_failure_rolls_back_publication_and_releases_manual_claim(manual_routine, monkeypatch):
    case = manual_routine
    before = case.db.scalar(select(func.count()).select_from(models.Post))
    def fail(_conn, _cursor, sql, _params, _context, _many):
        if sql.startswith("INSERT INTO memory_situation_receipts"):
            raise RuntimeError("synthetic receipt failure")
    event.listen(case.db.bind, "before_cursor_execute", fail)
    try:
        _, result, adapter = asyncio.run(run_routine(case, monkeypatch))
    finally:
        event.remove(case.db.bind, "before_cursor_execute", fail)
    assert result["result"]["public_action_count"] == 0
    assert len(adapter.requests) == 1
    case.db.refresh(case.candidate)
    assert case.candidate.status == "released"
    assert case.db.scalar(select(func.count()).select_from(models.Post)) == before
    assert case.db.scalar(select(func.count()).select_from(MemorySituationReceipt)) == 0
    assert case.db.scalar(select(func.count()).select_from(MemoryItem)) == 0


@pytest.mark.parametrize("manual_routine", [False], indirect=True)
def test_cancelled_generation_keeps_cancellation_and_uses_existing_cleanup(manual_routine, monkeypatch):
    from langgraph.errors import NodeCancelledError
    case = manual_routine
    with pytest.raises(NodeCancelledError) as cancelled:
        asyncio.run(run_routine(case, monkeypatch, response=asyncio.CancelledError()))
    assert isinstance(cancelled.value.__cause__, asyncio.CancelledError)
    case.lane.release_failed("synthetic_cancel")
    case.db.refresh(case.candidate)
    assert case.candidate.status == "released"
    assert case.db.scalar(select(func.count()).select_from(MemorySituationReceipt)) == 0
