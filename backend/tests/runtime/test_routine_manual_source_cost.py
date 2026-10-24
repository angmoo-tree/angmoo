"""Bounded canonical reads; no history fanout, diagnostic writes or new commits."""
from dataclasses import replace
from datetime import timedelta

import pytest
from sqlalchemy import event

from model_fixture_support import models
from app.domains.social.contracts.writes import OwnerReplyCommand
from app.runtime.social.sqlalchemy_unit_of_work import SqlAlchemySocialWriteUnitOfWork
from app.runtime.social.manual_inbox import claim, source_id
from app.runtime.autonomous_activity.routine_sources import input_source_bindings
from runtime.routine_manual_fixture import manual_routine, rebuild_input, freeze


@pytest.mark.parametrize("count", [1, 8])
def test_one_and_eight_sources_use_bounded_selects_and_never_flush_or_commit(manual_routine, count, record_property):
    case = manual_routine
    sources = list(case.prepared.context.source_events)
    for number in range(1, count):
        result = SqlAlchemySocialWriteUnitOfWork(case.db).create_owner_reply(OwnerReplyCommand(
            world_id=case.seeded.world.id, current_user_id=case.ctx.user_id, target_post_id=case.root.id,
            idempotency_key=f"bounded-source-{number}", body=f"Another measured suggestion {number}."))
        candidate = case.db.get(models.OwnerManualInboxCandidate, result.delivery.inbox_candidate_id)
        reply = case.db.get(models.Post, candidate.source_reply_post_id)
        candidate.created_at = reply.created_at = case.now-timedelta(minutes=1)
        case.db.commit()
        identifier = source_id(candidate.id)
        claim(case.db, source_event_id=identifier, world_id=case.seeded.world.id,
            consumer_world_character_id=case.seeded.world_character.id,
            target_activity_beat_id=case.prepared.beat.id, claim_run_id=case.ctx.run_id,
            claim_expires_at=case.now+timedelta(minutes=5), now=case.now)
        sources.append(replace(sources[0], source_event_id=identifier, excerpt=reply.body, occurred_at=candidate.created_at))
        case.prepared.claimed_manual_source_ids.append(identifier)
    case.prepared.context = replace(case.prepared.context, source_events=tuple(sources))
    rebuild_input(case)
    case.db.commit()
    statements, commits, flushes = [], [], []
    def statement(_conn, _cursor, sql, _params, _context, _many): statements.append(sql)
    def commit(*_): commits.append(1)
    def flush(*_): flushes.append(1)
    event.listen(case.db.bind, "before_cursor_execute", statement)
    event.listen(case.db, "after_commit", commit)
    event.listen(case.db, "before_flush", flush)
    try:
        records = case.payload["context"]["routine"]["source_events"]
        bindings = input_source_bindings(case.ctx, scope=case.provider.situation_snapshot.scope,
            records=records, state=case.state)
        binding_count = len(statements)
        # Claim, 2 posts, 2 actors, 2 memberships, block, at most 1 reply reload.
        assert len(bindings) == count and binding_count <= 9 * count
        assert not any("FROM comments" in sql for sql in statements)
        assert all(sql.lstrip().upper().startswith("SELECT") for sql in statements)
        statements.clear()
        manifest = freeze(case)
        capture_count = len(statements)
        assert len([s for s in manifest.sources if "/routine/source_events/" in s.payload_path]) == count
        assert capture_count <= 30 * count + 20
        assert all(sql.lstrip().upper().startswith("SELECT") for sql in statements)
        assert not flushes and not commits
        record_property("manual_sources", count)
        record_property("binding_selects", binding_count)
        record_property("capture_selects", capture_count)
        record_property("new_writes_or_commits", 0)
    finally:
        event.remove(case.db.bind, "before_cursor_execute", statement)
        event.remove(case.db, "after_commit", commit)
        event.remove(case.db, "before_flush", flush)


def test_resolving_a_source_does_not_flush_unrelated_pending_writes(manual_routine):
    from app.runtime.autonomous_activity.routine_sources import source_post_id
    case = manual_routine
    case.db.autoflush = True
    pending = models.Post(id="unrelated-pending", author_name="fixture", title="Pending", body="Caller owns this write.")
    case.db.add(pending)
    flushes = []
    def record(*_): flushes.append(1)
    event.listen(case.db, "before_flush", record)
    try:
        assert source_post_id(case.ctx, source_id=source_id(case.candidate.id), world_id=case.seeded.world.id,
            actor_id=case.seeded.world_character.id, beat_id=case.prepared.beat.id) == case.reply.id
        assert input_source_bindings(case.ctx, scope=case.provider.situation_snapshot.scope,
            records=case.payload["context"]["routine"]["source_events"], state=case.state) == [("REPLY", case.reply.id)]
        assert flushes == [] and pending in case.db.new
    finally:
        event.remove(case.db, "before_flush", record)
        case.db.rollback()
