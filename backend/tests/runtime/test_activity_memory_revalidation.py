"""SNS keeps acquired packets and checks memory rights, not current originals."""
from copy import deepcopy
from dataclasses import asdict
from datetime import datetime, timedelta
import json
import pytest
from sqlalchemy import event
from app.domains.memory.models.items import MemoryItem, MemoryScopeSettingModel
from app.domains.memory.models.episode import MemoryEpisodeLink
from app.domains.memory.repository.experience import tombstone
from app.domains.memory.repository.situation_admission import admit
from app.runtime.autonomous_activity import revalidation, recall
from memory.test_experience_snapshots import captured, real_source, apply, stack, NOW
from memory.test_activity_situation_recall import readers


def acquired(stack, monkeypatch):
    db, scope, setting, memory = stack
    post = real_source(db, scope)
    manifest, draft, result = captured(db, scope, post)
    receipt = admit(db, manifest=manifest, draft=draft, result=result, now=NOW)
    apply(db, setting, memory)
    item = db.get(MemoryItem, receipt.applied_item_id)
    reader, request, candidate, _ = readers(db, scope, item)
    hydration = reader.hydrate(request, reader.revalidate(request, (candidate,)))
    assert hydration.records
    result = {**recall.bounded_records(hydration.records),
        "ranked_memory_ids": [row.memory_item_id for row in hydration.records],
        "validation_snapshot": json.loads(json.dumps(asdict(hydration.validation_snapshot), default=str))}
    split = recall.split_validation({"target": result})
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None): return NOW
    monkeypatch.setattr(revalidation, "datetime", Clock)
    args = dict(owner_id=scope.owner_id, world_id=scope.world_id, actor_id=scope.subject_world_character_id,
        memories=split["memories"], validations=split["memory_validations"])
    return item, post, args, hydration


@pytest.mark.parametrize("change", ["none", "body", "source_deleted", "summary", "followup", "superseded",
    "deleted", "disabled", "expired", "tombstone"])
def test_current_rights_are_separate_from_reference_content(stack, monkeypatch, change):
    db, _, setting, _ = stack
    item, post, args, _ = acquired(stack, monkeypatch)
    first = deepcopy(args["memories"])
    revalidation.assert_memories_current(db, **args)
    if change == "body": post.body = "Later original text"
    elif change == "source_deleted": post.deleted_at = NOW
    elif change == "summary": item.summary, item.version = "Later summary", item.version + 1
    elif change in {"followup", "superseded"}:
        values = {column.key: getattr(item, column.key) for column in MemoryItem.__table__.columns}
        values["id"] = "later-memory"
        db.add(MemoryItem(**values)); db.flush()
        if change == "followup":
            db.add(MemoryEpisodeLink(prior_item_id=item.id, following_item_id="later-memory", created_at=NOW))
        else: item.status, item.superseded_by_id = "superseded", "later-memory"
    elif change == "deleted": item.status, item.deleted_at = "deleted", NOW
    elif change == "disabled": db.get(MemoryScopeSettingModel, setting.id).enabled = False
    elif change == "expired": item.valid_from, item.valid_until = NOW-timedelta(days=2), NOW-timedelta(seconds=1)
    elif change == "tombstone": tombstone(db, item, setting.id, now=NOW)
    db.commit(); db.expunge_all()
    queries = []
    def observe(_conn, _cursor, sql, *_): queries.append(sql.lower())
    event.listen(db.bind, "before_cursor_execute", observe)
    try:
        if change in {"deleted", "disabled", "expired", "tombstone"}:
            with pytest.raises(ValueError, match="activity_memory_changed"):
                revalidation.assert_memories_current(db, **args)
        else: revalidation.assert_memories_current(db, **args)
    finally: event.remove(db.bind, "before_cursor_execute", observe)
    assert args["memories"] == first
    assert not any("from posts" in query or "from messages" in query or "memory_items.summary" in query for query in queries)


@pytest.mark.parametrize("field,value", [("reference", "foreign"), ("role", "foreign"), ("text", "changed"),
    ("status", "missing"), ("start_offset", 1), ("end_offset", 1), ("author_id", "injected")])
def test_delivered_packet_mutation_is_rejected(stack, monkeypatch, field, value):
    db = stack[0]
    _, _, args, _ = acquired(stack, monkeypatch)
    revalidation.assert_memories_current(db, **args)
    args["memories"]["target"]["packets"][0]["units"][0]["sources"][0][field] = value
    with pytest.raises(ValueError, match="activity_memory_input_integrity_invalid"):
        revalidation.assert_memories_current(db, **args)


@pytest.mark.parametrize("change", ["missing", "scope", "policy", "revisions", "digest"])
def test_invalid_or_missing_proof_is_not_rebuilt_from_current_data(stack, monkeypatch, change):
    db = stack[0]
    _, _, args, _ = acquired(stack, monkeypatch)
    proof = args["validations"]["target"]
    if change == "missing": args.pop("validations")
    elif change == "scope": proof["scope"]["world_id"] = "foreign"
    elif change == "policy": proof["policy_version"] = "future"
    elif change == "revisions": proof["item_revisions"] = [["malformed"]]
    else: proof["memory_snapshot_digests"][0][1] = "f" * 64
    with pytest.raises(ValueError, match="activity_memory_"):
        revalidation.assert_memories_current(db, **args)


def test_each_packet_budget_has_its_own_bound_delivery_digest(stack, monkeypatch):
    db = stack[0]
    _, _, args, hydration = acquired(stack, monkeypatch)
    full = recall.bounded_records(hydration.records)
    first = full["packets"][0]
    minimum = {**first, "units": [], "partial": True,
        "omitted_units": len(first["units"]) + first.get("omitted_units", 0)}
    monkeypatch.setattr(recall, "MEMORY_CHARS", len(json.dumps([minimum], ensure_ascii=False)) + 20)
    compact = recall.bounded_records(hydration.records)
    assert compact["packets"] and compact != full
    for group in (full, compact):
        split = recall.split_validation({"target": {**group,
            "ranked_memory_ids": args["memories"]["target"]["ranked_memory_ids"],
            "validation_snapshot": args["validations"]["target"]}})
        revalidation.assert_memories_current(db, **{**args, "memories": split["memories"],
            "validations": split["memory_validations"]})
