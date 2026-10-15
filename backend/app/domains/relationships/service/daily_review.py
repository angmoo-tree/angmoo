"""Durable per-counterpart review. No model call holds a database transaction."""

from datetime import UTC, datetime, timedelta
from time import perf_counter
from typing import Protocol

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.ids import uuid7_string
from app.domains.relationships.contracts.daily_review import manifest_digest, validate_review_result, ReviewNeedsSplit
from app.domains.relationships.models.personalization import RelationshipReviewWork, RelationshipReviewMemoryReceipt
from app.domains.relationships.policies.daily_review import partition_review_inputs
from app.domains.relationships.service.state import _relationship_state
from app.domains.relationships.service.personalized_metrics import enqueue_snapshot


class ReviewProvider(Protocol):
    async def review(self, payload: dict, *, partial: bool, timeout: float) -> object: ...


class ReviewReferences(Protocol):
    def revalidate(self, work: RelationshipReviewWork) -> None: ...


def _children(db, work_id):
    return list(db.scalars(select(RelationshipReviewWork).where(
        RelationshipReviewWork.parent_id == work_id).order_by(RelationshipReviewWork.part_key)))


def _new_work(db, *, world_id, actor_id, target_id, period_key, part_key, phase,
              manifest, view_version, parent_id=None):
    row = RelationshipReviewWork(id=uuid7_string(), world_id=world_id,
        actor_world_character_id=actor_id, target_world_character_id=target_id,
        period_key=period_key, part_key=part_key, phase=phase, manifest=manifest,
        manifest_digest=manifest_digest(manifest), expected_view_version=view_version,
        parent_id=parent_id, status="pending", attempts=0)
    db.add(row)
    db.flush()
    return row


def plan_review(db: Session, *, world_id: str, actor_id: str, target_id: str,
                period_key: str, base: dict, memories: list[dict]) -> RelationshipReviewWork | None:
    """Freeze only admitted saved memories; no history backfill or empty calls."""
    # Serialize automatic/manual planning before testing the active root.
    from app.domains.relationships.models.personalization import RelationshipPolicy
    db.execute(update(RelationshipPolicy).where(RelationshipPolicy.world_id == world_id).values(version=RelationshipPolicy.version))
    existing = db.scalar(select(RelationshipReviewWork).where(
        RelationshipReviewWork.world_id == world_id, RelationshipReviewWork.actor_world_character_id == actor_id,
        RelationshipReviewWork.target_world_character_id == target_id, RelationshipReviewWork.parent_id.is_(None),
        RelationshipReviewWork.status.in_(("pending", "running", "ready", "failed"))))
    if existing is not None:
        return existing
    if not memories:
        return None
    state = _relationship_state(db, world_id=world_id, actor_world_character_id=actor_id, target_world_character_id=target_id)
    base = {**base, "world_id": world_id, "actor_id": actor_id, "target_id": target_id,
            "existing_relationship": {"relationship_label": state.relationship_label, "perception": state.perception,
                "familiarity": state.familiarity, "affinity": state.affinity, "trust": state.trust, "tension": state.tension}}
    parts = partition_review_inputs(base, memories)
    manifest = {"base": base, "memories": memories if len(parts) == 1 else [{k: v for k, v in m.items() if k != "summary"} for m in memories]}
    root = _new_work(db, world_id=world_id, actor_id=actor_id, target_id=target_id, period_key=period_key,
        part_key="root", phase="direct" if len(parts) == 1 else "final", manifest=manifest, view_version=state.view_version)
    if len(parts) > 1:
        for index, payload in enumerate(parts):
            _new_work(db, world_id=world_id, actor_id=actor_id, target_id=target_id, period_key=period_key,
                part_key=f"partial-{index:08d}", phase="partial", manifest={"payload": payload},
                view_version=state.view_version, parent_id=root.id)
    for memory in memories:
        db.add(RelationshipReviewMemoryReceipt(id=uuid7_string(), world_id=world_id,
            actor_world_character_id=actor_id, target_world_character_id=target_id,
            memory_id=memory["memory_id"], memory_digest=memory["digest"], work_id=root.id, status="pending"))
    db.flush()
    return root


def _verified_result(work):
    result = {key: value for key, value in (work.result or {}).items() if key != "_execution"}
    expected = (work.result or {}).get("_execution", {}).get("result_digest")
    if expected != manifest_digest(result):
        raise ValueError("relationship_review_result_changed")
    return result


def _payload(db, work):
    if manifest_digest(work.manifest) != work.manifest_digest:
        raise ValueError("relationship_review_manifest_changed")
    if work.phase == "direct":
        return {**work.manifest["base"], "memories": work.manifest["memories"]}
    if work.phase == "partial":
        return work.manifest["payload"]
    children = _children(db, work.id)
    if not children or any(child.status != "ready" for child in children):
        return None
    base = work.manifest["base"]
    source_map = {memory["memory_id"]: memory["source_refs"] for memory in _root(db, work).manifest["memories"]}
    entries = []
    for child in children:
        result = _verified_result(child)
        entries.append({"part_id": child.id, **result, "source_refs": sorted({
            source for ref in result["memory_refs"] for source in source_map.get(ref, [])})})
    parts = partition_review_inputs(base, entries, key="partial_results")
    if len(parts) == 1:
        return parts[0]
    # Replace an oversized fan-in with bounded intermediate reductions. The
    # completed children keep their saved results and are never re-requested.
    if len(parts) >= len(children):
        raise ValueError("relationship_review_reduction_not_shrinking")
    for index, payload in enumerate(parts):
        group_ids = {entry["part_id"] for entry in payload["partial_results"]}
        reducer = _new_work(db, world_id=work.world_id, actor_id=work.actor_world_character_id,
            target_id=work.target_world_character_id, period_key=work.period_key,
            part_key=f"reduce-{uuid7_string()}", phase="reduce", manifest={"base": base},
            view_version=work.expected_view_version, parent_id=work.id)
        for child in children:
            if child.id in group_ids:
                child.parent_id = reducer.id
    db.flush()
    return None


def _root(db, work):
    seen = set()
    while work.parent_id is not None:
        if work.id in seen:
            raise ValueError("relationship_review_work_cycle")
        seen.add(work.id)
        work = db.get(RelationshipReviewWork, work.parent_id)
        if work is None:
            raise ValueError("relationship_review_parent_missing")
    return work


async def run_review_step(session_factory, *, work_id: str, references_factory,
                          provider_factory, now=None, timeout: float = 120.0,
                          journal=None, received=None) -> str:
    """One provider submission, followed by independently replayable local storage."""
    import asyncio
    from app.core.sqlite_concurrency import is_sqlite_contention, run_sqlite_session_immediate
    from app.core.result_journal import ResultJournalError
    from app.domains.relationships.service.review_delivery import persist_received, may_publish
    clock = now or (lambda: datetime.now(UTC))
    received = received if received is not None else {}
    with session_factory() as db:
        work = db.get(RelationshipReviewWork, work_id)
        if work is None:
            received.pop(work_id, None)
            return "lease_lost"
        world_id = work.world_id
    try:
        record = received.get(work_id) or (journal.read(world_id, work_id) if journal else None)
    except ResultJournalError:
        return "result_journal_invalid"
    if record is not None:
        if "result" not in record:
            with session_factory() as db:
                def mark_unknown():
                    row = db.get(RelationshipReviewWork, work_id, populate_existing=True)
                    if row is not None and row.error_code == "relationship_review_outcome_unknown" and row.attempts == record["attempt"]:
                        return "outcome_unknown"
                    if row is not None and row.lease_token == record["lease"] and row.attempts == record["attempt"]:
                        row.status, row.error_code = "failed", "relationship_review_outcome_unknown"
                        row.lease_token, row.lease_until = None, None
                        return "outcome_unknown"
                    return "lease_lost"
                outcome = run_sqlite_session_immediate(db, mark_unknown, require_clean=True)
            if outcome == "lease_lost" and journal:
                journal.remove(world_id, work_id)
            return outcome  # Sent, but no durable response survived.
        try:
            if journal:
                journal.write(world_id, work_id, record)
            outcome = persist_received(session_factory, work_id, record, references_factory)
            if journal:
                journal.remove(world_id, work_id)
            received.pop(work_id, None)
            return outcome
        except Exception as exc:
            if is_sqlite_contention(exc) or isinstance(exc, (OSError, ResultJournalError)):
                return "local_result_pending"
            if isinstance(exc, ValueError):
                if journal:
                    journal.remove(world_id, work_id)
                received.pop(work_id, None)
                return "validation_deferred"
            raise
    lease = uuid7_string()
    try:
        with session_factory() as db:
            def claim():
                current = clock()
                work = db.get(RelationshipReviewWork, work_id, populate_existing=True)
                if work is None:
                    return "lease_lost"
                if work.status in {"ready", "applied", "stale"}:
                    return work.status
                if work.error_code == "relationship_review_outcome_unknown":
                    return "outcome_unknown"
                if work.lease_until:
                    until = work.lease_until.replace(tzinfo=UTC) if work.lease_until.tzinfo is None else work.lease_until
                    if until > current:
                        return "leased"
                try:
                    root = _root(db, work)
                    references_factory(db).revalidate(root)
                    payload = _payload(db, work)
                except ValueError as exc:
                    work.status, work.error_code = "failed", str(exc) if str(exc).startswith("relationship_") else "relationship_review_validation_failed"
                    work.next_attempt_at = current + timedelta(minutes=5)
                    return "validation_deferred"
                if payload is None:
                    return "waiting_for_parts"
                refs = ({m["memory_id"] for m in payload["memories"]} if "memories" in payload
                    else {ref for part in payload["partial_results"] for ref in part["memory_refs"]})
                work.status, work.lease_token = "running", lease
                work.lease_until, work.attempts = current + timedelta(seconds=timeout+60), work.attempts + 1
                record = dict(lease=lease, attempt=work.attempts, manifest_digest=work.manifest_digest,
                    root_digest=root.manifest_digest, partial=work.phase in {"partial", "reduce"}, allowed_refs=sorted(refs))
                return payload, dict(root.manifest["base"]), record
            claimed = run_sqlite_session_immediate(db, claim, require_clean=True)
    except Exception as exc:
        if is_sqlite_contention(exc):
            return "storage_busy"
        raise
    if isinstance(claimed, str):
        return claimed
    payload, material, record = claimed
    # A content-free submission marker makes the pre-journal crash boundary
    # explicit. A restart cannot silently turn it into another paid request.
    if journal:
        try:
            journal.write(world_id, work_id, record)
        except (OSError, ResultJournalError):
            return "result_journal_unavailable"
    try:
        started = perf_counter()
        provider = provider_factory(material)
        raw = await provider.review(payload, partial=record["partial"], timeout=timeout)
        result = validate_review_result(raw, partial=record["partial"], allowed_refs=set(record["allowed_refs"]))
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        if journal:
            journal.remove(world_id, work_id)
        with session_factory() as db:
            def fail():
                row = db.get(RelationshipReviewWork, work_id, populate_existing=True)
                if row is None or row.lease_token != lease:
                    return "lease_lost"
                if isinstance(exc, ReviewNeedsSplit) and split_incomplete_work(db, row, payload):
                    return "split_pending"
                row.status, row.lease_token, row.lease_until = "failed", None, None
                row.error_code = getattr(exc, "reason_code", None) or getattr(exc, "failure_class", None) or "relationship_review_retry_required"
                row.next_attempt_at = clock() + timedelta(seconds=min(3600, 30 * 2 ** min(row.attempts, 7)))
                return "retry_pending"
            try:
                return run_sqlite_session_immediate(db, fail, require_clean=True)
            except Exception as failure:
                if is_sqlite_contention(failure):
                    return "storage_busy"
                raise
    usage = getattr(provider, "usage", None)
    record = {**record, "result": result, "result_digest": manifest_digest(result),
        "duration_ms": round((perf_counter()-started)*1000, 2),
        "usage": usage.as_direct_llm_usage() if hasattr(usage, "as_direct_llm_usage") else None}
    received[work_id] = record
    try:
        if not may_publish(session_factory, work_id, record, clock()):
            received.pop(work_id, None)
            if journal:
                journal.remove(world_id, work_id)
            return "lease_lost"
        if journal:
            journal.write(world_id, work_id, record)
        outcome = persist_received(session_factory, work_id, record, references_factory)
        if journal:
            journal.remove(world_id, work_id)
        received.pop(work_id, None)
        return outcome
    except Exception as exc:
        if is_sqlite_contention(exc) or isinstance(exc, (OSError, ResultJournalError)):
            return "local_result_pending"
        if isinstance(exc, ValueError):
            if journal:
                journal.remove(world_id, work_id)
            received.pop(work_id, None)
            return "validation_deferred"
        raise


def apply_review(db: Session, *, work_id: str, references: ReviewReferences, now: datetime) -> str:
    root = db.scalar(select(RelationshipReviewWork).where(RelationshipReviewWork.id == work_id).with_for_update())
    if root is None or root.parent_id is not None:
        raise ValueError("relationship_review_root_invalid")
    if root.status == "applied":
        return "applied"
    if root.status != "ready" or root.result is None:
        return "not_ready"
    db.execute(update(RelationshipReviewWork).where(RelationshipReviewWork.id == root.id,
        RelationshipReviewWork.status == "ready").values(status="ready"))
    db.refresh(root)
    if root.status != "ready":
        return root.status
    references.revalidate(root)
    if root.phase == "final" and any(part.status != "ready" for part in _children(db, root.id)):
        return "not_ready"
    state = _relationship_state(db, world_id=root.world_id, actor_world_character_id=root.actor_world_character_id,
                                target_world_character_id=root.target_world_character_id)
    db.refresh(state)
    if state.view_version != root.expected_view_version:
        # Rebase on the new normal view. Old partial interpretations depended on
        # the former view, so only this pair is re-prepared; receipts stay pending.
        rebase_review(db, root, state)
        return "rebased"
    result = validate_review_result(_verified_result(root), partial=False,
        allowed_refs={m["memory_id"] for m in root.manifest["memories"]})
    if result["decision"] == "update" and (state.relationship_label, state.perception) != (result["relationship_label"], result["perception"]):
        state.relationship_label = result["relationship_label"]
        state.perception = result["perception"]
        state.view_version += 1
        state.view_updated_at = now
    state.reviewed_at = now
    state.version += 1
    state.updated_at = now
    root.status = "applied"
    root.completed_at = now
    db.execute(update(RelationshipReviewMemoryReceipt).where(RelationshipReviewMemoryReceipt.work_id == root.id, RelationshipReviewMemoryReceipt.status == "pending").values(status="applied"))
    db.flush()
    enqueue_snapshot(db, state)
    return "applied"


def rebase_review(db, root, state):
    base = dict(root.manifest["base"])
    base["existing_relationship"] = {key: getattr(state, key) for key in
        ("relationship_label", "perception", "familiarity", "affinity", "trust", "tension")}
    root.manifest = {**root.manifest, "base": base}
    root.manifest_digest = manifest_digest(root.manifest)
    root.expected_view_version = state.view_version
    def reset(row):
        row.status, row.result, row.error_code = "pending", None, None
        row.lease_token, row.lease_until, row.next_attempt_at = None, None, None
        row.expected_view_version = state.view_version
        if row.phase == "partial":
            row.manifest = {"payload": {**row.manifest["payload"], **base}}
        elif row.parent_id:
            row.manifest = {"base": base}
        row.manifest_digest = manifest_digest(row.manifest)
        for child in _children(db, row.id):
            reset(child)
    reset(root)


def split_incomplete_work(db, work, payload):
    key = "memories" if "memories" in payload else "partial_results"
    entries = payload[key]
    if len(entries) < 2:
        return False
    base = {k: v for k, v in payload.items() if k != key}
    groups = [entries[:len(entries)//2], entries[len(entries)//2:]]
    children = _children(db, work.id)
    if key == "memories":
        if work.parent_id is None:
            work.phase = "final"
            work.manifest = {**work.manifest, "memories": [{k: v for k, v in m.items() if k != "summary"} for m in entries]}
        else:
            work.phase, work.manifest = "reduce", {"base": base}
        for group in groups:
            _new_work(db, world_id=work.world_id, actor_id=work.actor_world_character_id,
                target_id=work.target_world_character_id, period_key=work.period_key,
                part_key=f"split-{uuid7_string()}", phase="partial", manifest={"payload": {**base, "memories": group}},
                view_version=work.expected_view_version, parent_id=work.id)
    else:
        for group in groups:
            part = _new_work(db, world_id=work.world_id, actor_id=work.actor_world_character_id,
                target_id=work.target_world_character_id, period_key=work.period_key,
                part_key=f"reduce-{uuid7_string()}", phase="reduce", manifest={"base": base},
                view_version=work.expected_view_version, parent_id=work.id)
            ids = {entry["part_id"] for entry in group}
            for child in children:
                if child.id in ids:
                    child.parent_id = part.id
    work.manifest_digest = manifest_digest(work.manifest)
    work.status, work.result, work.error_code = "pending", None, "relationship_review_split_after_incomplete"
    work.lease_token, work.lease_until, work.next_attempt_at = None, None, None
    return True
