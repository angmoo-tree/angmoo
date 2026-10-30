"""Regression of manual candidate identity at the real provider submission boundary."""
import asyncio
from copy import deepcopy
from dataclasses import replace
from datetime import UTC, datetime

import pytest
from sqlalchemy import update

from model_fixture_support import models
from app.runtime.autonomous_activity.routine_sources import RoutineSourceBindingError
from app.runtime.autonomous_activity.routine_resume import restore_prepared
from app.domains.routine_posts.constants import MAX_EVENT_EXCERPT_CHARS
from app.domains.routine_posts.utils.text import _clip
from app.providers.contracts import ProviderError

from runtime.routine_manual_fixture import manual_routine, install_adapter, submit, freeze, rebuild_input


def test_manual_reply_reaches_adapter_with_canonical_delivery(manual_routine, monkeypatch):
    case = manual_routine
    adapter = install_adapter(monkeypatch)
    assert asyncio.run(submit(case)) == {"ok": True}
    assert len(adapter.requests) == 1
    manifest = case.provider.situation_manifest
    entry = next(row for row in manifest.sources if "/routine/source_events/" in row.payload_path)
    assert entry.source_type == "REPLY"
    assert entry.source_id == case.reply.id
    assert entry.delivery_payload_digest == manifest.payload_digest
    assert entry.ranges == entry.delivered_ranges == ((0, len(case.reply.body)),)
    assert case.prepared.context.source_events[0].source_event_id == f"manual-inbox:{case.candidate.id}"


@pytest.mark.parametrize("change", ["missing", "world", "actor", "consumer", "beat", "run", "released",
    "reply_deleted", "reply_hidden", "reply_private", "parent_deleted", "parent_hidden", "parent_private",
    "parent_link", "author", "membership", "block", "excerpt", "time", "frozen_missing", "identity", "owner"])
def test_invalid_manual_input_never_dispatches(manual_routine, monkeypatch, caplog, change):
    case = manual_routine
    adapter = install_adapter(monkeypatch)
    record = case.payload["context"]["routine"]["source_events"][0]
    frozen = case.state["lane_data"]["prepared"]
    if change == "missing":
        original = record["source_event_id"]
        record["source_event_id"] = "manual-inbox:absent"
        frozen["source_events"][0]["source_event_id"] = record["source_event_id"]
        frozen["claimed_manual_source_ids"] = [record["source_event_id"]]
        assert original != record["source_event_id"]
    elif change in {"world", "consumer"}:
        frozen["source_events"][0]["world_id" if change == "world" else "consumer_world_character_id"] = "other"
    elif change == "actor":
        record["actor_world_character_id"] = "other"
    elif change == "beat": frozen["beat_id"] = "other"
    elif change == "run": case.candidate.claim_run_id = "other"
    elif change == "released": case.candidate.status = "released"
    elif change.endswith(("deleted", "hidden", "private")):
        post = case.reply if change.startswith("reply_") else case.root
        field = {"deleted": "deleted_at", "hidden": "report_hidden_at", "private": "visibility"}[change.split("_")[1]]
        setattr(post, field, "private" if field == "visibility" else datetime.now(UTC))
    elif change == "parent_link": case.reply.reply_to_post_id = None
    elif change == "author":
        case.reply.author_world_character_id = case.seeded.world_character.id
        case.reply.author_character_id = case.seeded.character.id
    elif change == "membership": case.db.get(models.WorldMembership, case.owner.membership_id).status = "left"
    elif change == "block":
        case.db.add(models.WorldCharacterBlock(id="routine-source-block", world_id=case.root.world_id,
            blocker_world_character_id=case.owner.id, blocked_world_character_id=case.seeded.world_character.id))
    elif change == "excerpt": record["excerpt"] = "undelivered invention"
    elif change == "time": record["occurred_at"] = "2020-01-01T00:00:00+00:00"
    elif change == "frozen_missing": frozen.pop("source_events")
    elif change == "identity": case.state["identity"]["activity_id"] = "other"
    elif change == "owner":
        case.provider.situation_snapshot = replace(case.provider.situation_snapshot,
            scope=replace(case.provider.situation_snapshot.scope, owner_id="other"))
    case.db.commit()
    historical_only = {"reply_deleted", "reply_hidden", "reply_private", "parent_deleted",
        "parent_hidden", "parent_private", "parent_link", "author"}
    if change in historical_only:
        assert asyncio.run(submit(case)) == {"ok": True}
        assert len(adapter.requests) == 1
    else:
        with pytest.raises(ValueError):
            asyncio.run(submit(case))
        assert adapter.requests == []
    assert case.reply.body not in caplog.text
    assert "undelivered invention" not in caplog.text
    assert "synthetic" not in caplog.text


@pytest.mark.parametrize("changed", ["body", "claim", "membership"])
def test_final_binding_reads_current_rows_even_with_an_existing_identity_map(manual_routine, changed):
    case = manual_routine
    freeze(case)
    table, identifier, values = {
        "body": (models.Post, case.reply.id, {"body": "An edited suggestion."}),
        "claim": (models.OwnerManualInboxCandidate, case.candidate.id, {"status": "released"}),
        "membership": (models.WorldMembership, case.owner.membership_id, {"status": "left"}),
    }[changed]
    case.db.execute(update(table).where(table.id == identifier).values(**values),
        execution_options={"synchronize_session": False})
    case.db.commit()
    if changed == "body":
        assert freeze(case).sources
    else:
        with pytest.raises(ValueError):
            freeze(case)


@pytest.mark.parametrize("mode", ["none", "event", "mixed"])
def test_normal_events_zero_sources_and_manual_sources_remain_distinct(manual_routine, mode):
    case = manual_routine
    from app.runtime.relationships.sqlalchemy_social_event import record_successful_social_event, EvidenceInput
    identifier = record_successful_social_event(case.db, world_id=case.seeded.world.id,
        actor_world_character_id=case.seeded.world_character.id, target_world_character_id=None,
        event_type="post_published", occurred_at=case.now, idempotency_key="routine-canonical-root",
        evidence=EvidenceInput(evidence_kind="post", source_object_type="post", source_object_id=case.root.id,
            source_post_id=case.root.id, root_post_id=case.root.id, source_text=case.root.body,
            source_visibility_at_event="public", source_author_id_at_event=case.seeded.world_character.id)).event.id
    case.db.commit()
    manual = case.prepared.context.source_events[0]
    normal = replace(manual, source_event_id=identifier, actor_world_character_id=case.seeded.world_character.id,
        excerpt=case.root.body)
    events = () if mode == "none" else (normal,) if mode == "event" else (manual, normal)
    case.prepared.context = replace(case.prepared.context, source_events=events)
    rebuild_input(case)
    manifest = freeze(case)
    sources = [row for row in manifest.sources if "/routine/source_events/" in row.payload_path]
    assert [(s.source_type, s.source_id) for s in sources] == ([] if mode == "none" else
        [("SOCIAL_EVENT", identifier)] if mode == "event" else [("REPLY", case.reply.id), ("SOCIAL_EVENT", identifier)])


def test_partial_excerpt_keeps_only_delivered_range_and_distinct_paths(manual_routine):
    case = manual_routine
    case.reply.body = "A" * (MAX_EVENT_EXCERPT_CHARS + 70)
    case.db.commit()
    source = replace(case.prepared.context.source_events[0], excerpt=_clip(case.reply.body, MAX_EVENT_EXCERPT_CHARS))
    case.prepared.context = replace(case.prepared.context, source_events=(source,))
    rebuild_input(case)
    manifest = freeze(case)
    rows = [s for s in manifest.sources if s.source_id == case.reply.id]
    assert len(rows) == 2 and len({s.payload_path for s in rows}) == 2
    entry = next(s for s in rows if "/routine/source_events/" in s.payload_path)
    assert entry.ranges == ((0, MAX_EVENT_EXCERPT_CHARS),)
    assert len({s.ordinal for s in manifest.sources}) == len(manifest.sources)
    case.reply.body = "changed" + case.reply.body
    case.db.commit()
    assert freeze(case) == manifest


def test_transmitted_source_projection_cannot_borrow_an_existing_identifier(manual_routine):
    case = manual_routine
    assert case.payload["context"]["source_manifest"]
    case.payload["context"]["source_manifest"][0]["excerpt"] = "unrelated fabricated input"
    with pytest.raises(ValueError, match="situation_source_not_admitted"):
        freeze(case)


@pytest.mark.parametrize("kind", ["duplicate", "over_limit", "malformed_prefix", "wire"])
def test_bad_source_list_or_transmission_is_not_silently_dropped(manual_routine, kind):
    case = manual_routine
    records = case.payload["context"]["routine"]["source_events"]
    if kind == "duplicate": records.append(deepcopy(records[0]))
    elif kind == "over_limit": records.extend(deepcopy(records[0]) for _ in range(8))
    elif kind == "malformed_prefix": records[0]["source_event_id"] = "manual-inbox:"
    else:
        from app.runtime.autonomous_activity.situation_memory import freeze_social_input
        with pytest.raises(ValueError, match="situation_final_payload_mismatch"):
            freeze_social_input(case.ctx, case.provider.situation_snapshot, node="RoutineDecisionDraft",
                payload=case.payload, transmitted='{}', state=case.state)
        return
    with pytest.raises(ValueError, match="situation_"):
        freeze(case)


def test_old_prepared_checkpoint_and_memory_off_do_not_change_selection_ids(manual_routine, monkeypatch):
    case = manual_routine
    restored = restore_prepared(case.ctx, deepcopy(case.state["lane_data"]["prepared"]), case.provider.tracker)
    assert restored.context.considered_source_event_ids == [f"manual-inbox:{case.candidate.id}"]
    assert restored.execution_signature == case.prepared.execution_signature
    case.provider.situation_output_active = False
    adapter = install_adapter(monkeypatch)
    assert asyncio.run(submit(case)) == {"ok": True}
    assert len(adapter.requests) == 1 and not hasattr(case.provider, "situation_manifest")


@pytest.mark.parametrize("field,value,reason", [
    ("output_contract", "routine-output.future.v99", "routine_output_contract_unsupported"),
    ("state_schema_version", 99, "routine_policy_version_invalid"),
])
def test_unknown_checkpoint_policy_is_not_guessed_or_upgraded(manual_routine, field, value, reason):
    case = manual_routine
    frozen = deepcopy(case.state["lane_data"]["prepared"])
    frozen[field] = value
    with pytest.raises(ValueError, match=reason):
        restore_prepared(case.ctx, frozen, case.provider.tracker)
    assert case.candidate.status == "claimed" and case.candidate.claim_run_id == case.ctx.run_id


def test_provider_503_stays_a_provider_error_after_successful_admission(manual_routine, monkeypatch):
    from app.integrations.direct_llm import DirectLlmError
    waits = []
    async def simulated_wait(seconds):
        waits.append(seconds)
    monkeypatch.setattr("app.integrations.direct_llm.asyncio.sleep", simulated_wait)
    adapter = install_adapter(monkeypatch, ProviderError("synthetic unavailable", failure_class="unavailable",
        provider_code=503, provider_status="UNAVAILABLE", retryable=False))
    with pytest.raises(DirectLlmError) as error:
        asyncio.run(submit(manual_routine))
    assert "situation_source_not_admitted" not in str(error.value)
    assert len(adapter.requests) == 2 and waits == [60.0]  # Existing transport retry, no real delay/API.
    assert any(s.source_id == manual_routine.reply.id for s in manual_routine.provider.situation_manifest.sources)
