"""Durable per-counterpart review. No model call holds a database transaction."""

from datetime import UTC, datetime, timedelta
from time import perf_counter
from typing import Protocol

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.ids import uuid7_string
from app.domains.relationships.contracts.daily_review import manifest_digest, validate_review_result, ReviewNeedsSplit
from app.domains.relationships.models.personalization import RelationshipReviewWork, RelationshipReviewMemoryReceipt
from app.domains.relationships.policies.daily_review import partition_review_inputs, prompt_base, prompt_memory, REVIEW_INPUT_POLICY
from app.domains.relationships.service.review_payloads import (review_children, new_work, verified_result, build_payload, root_work)
from app.domains.relationships.service.state import _relationship_state
from app.domains.relationships.service.personalized_metrics import enqueue_snapshot


class ReviewProvider(Protocol):
    async def review(self, payload: dict, *, partial: bool, timeout: float) -> object: ...


class ReviewReferences(Protocol):
    def revalidate(self, work: RelationshipReviewWork) -> None: ...


def plan_review(db: Session, *, world_id: str, actor_id: str, target_id: str,
                period_key: str, base: dict, memories: list[dict], previous_work_id=None) -> RelationshipReviewWork | None:
    """Freeze only admitted saved memories; no history backfill or empty calls."""
    # Serialize automatic/manual planning before testing the active root.
    from app.domains.relationships.models.personalization import RelationshipPolicy
    db.execute(update(RelationshipPolicy).where(RelationshipPolicy.world_id == world_id).values(version=RelationshipPolicy.version))
    existing = db.scalar(select(RelationshipReviewWork).where(
        RelationshipReviewWork.world_id == world_id, RelationshipReviewWork.actor_world_character_id == actor_id,
        RelationshipReviewWork.target_world_character_id == target_id, RelationshipReviewWork.parent_id.is_(None),
        RelationshipReviewWork.status.in_(("pending", "running", "ready"))))
    if existing is not None:
        return existing
    if not memories:
        return None
    state = _relationship_state(db, world_id=world_id, actor_world_character_id=actor_id, target_world_character_id=target_id)
    base = {**base, "world_id": world_id, "actor_id": actor_id, "target_id": target_id,
            "existing_relationship": {"relationship_label": state.relationship_label, "perception": state.perception,
                "familiarity": state.familiarity, "affinity": state.affinity, "trust": state.trust, "tension": state.tension}}
    # Guard metadata is durable but never part of the model input.
    memories = [{**prompt_memory(m), "digest": m["digest"]} for m in memories]
    parts = partition_review_inputs(prompt_base(base), [prompt_memory(m) for m in memories])
    manifest = {"input_policy": REVIEW_INPUT_POLICY, "base": base,
        "memories": memories if len(parts) == 1 else [
            {k: v for k, v in m.items() if k != "summary"} for m in memories]}
    root = new_work(db, world_id=world_id, actor_id=actor_id, target_id=target_id, period_key=period_key,
        part_key="root", phase="direct" if len(parts) == 1 else "final", manifest=manifest, view_version=state.view_version)
    if len(parts) > 1:
        for index, payload in enumerate(parts):
            new_work(db, world_id=world_id, actor_id=actor_id, target_id=target_id, period_key=period_key,
                part_key=f"partial-{index:08d}", phase="partial", manifest={"input_policy": REVIEW_INPUT_POLICY, "payload": payload},
                view_version=state.view_version, parent_id=root.id)
    for memory in memories:
        if previous_work_id is not None:
            receipt = db.scalar(select(RelationshipReviewMemoryReceipt).where(
                RelationshipReviewMemoryReceipt.work_id == previous_work_id,
                RelationshipReviewMemoryReceipt.world_id == world_id,
                RelationshipReviewMemoryReceipt.actor_world_character_id == actor_id,
                RelationshipReviewMemoryReceipt.target_world_character_id == target_id,
                RelationshipReviewMemoryReceipt.memory_id == memory["memory_id"]))
            if receipt is None or receipt.status != "pending":
                raise ValueError("relationship_review_policy_receipt_changed")
            receipt.work_id, receipt.memory_digest = root.id, memory["digest"]
            continue
        db.add(RelationshipReviewMemoryReceipt(id=uuid7_string(), world_id=world_id,
            actor_world_character_id=actor_id, target_world_character_id=target_id,
            memory_id=memory["memory_id"], memory_digest=memory["digest"], work_id=root.id, status="pending"))
    db.flush()
    return root


async def run_review_step(session_factory, *, work_id: str, references_factory,
                          provider_factory, now=None, timeout=120.0,
                          journal=None, received=None, database_work=None):
    """Classify permanent results once and release poison work from admission."""
    from app.domains.relationships.service.review_recovery import stopped, mark_failed, storage_deferred
    from app.core.postgresql_concurrency import retryable
    async def local(function, *args):
        return await database_work(function, *args) if database_work else function(*args)
    async def defer_storage():
        from app.core.sqlite_concurrency import is_sqlite_contention
        try:
            return await local(storage_deferred, session_factory, work_id)
        except Exception as error:
            if not (is_sqlite_contention(error) or retryable(error)):
                raise
            # Even the bookkeeping writer is unavailable. Keep the received
            # response and bounded recovery evidence in the private journal.
            value = (received or {}).get(work_id) or (journal.read(world_id, work_id) if journal else None)
            if value is not None:
                value = dict(value)
                failure = dict(value.get("storage_failure", {}))
                instant = datetime.now(UTC)
                failure.setdefault("first_at", instant.isoformat())
                failure["rounds"] = failure.get("rounds", 0)+1
                value["storage_failure"] = failure
                if journal:
                    journal.write(world_id, work_id, value)
                if received is not None:
                    received[work_id] = value
            return "local_result_pending"
    def identity():
        with session_factory() as db:
            work = db.get(RelationshipReviewWork, work_id)
            return None if work is None else (work.world_id, stopped(work) or stopped(root_work(db, work)), dict(work.maintenance or {}))
    info = await local(identity)
    if info is None or info[1]:
        if received is not None:
            received.pop(work_id, None)
        return "needs_attention"
    world_id = info[0]
    record = None
    try:
        record = (received or {}).get(work_id) or (journal.read(world_id, work_id) if journal else None)
        # A manual storage-resume starts a new bounded storage budget, while
        # retaining this response's submission token and provider attempt.
        if record and record.get("storage_revision", 0) != info[2].get("storage_revision", 0):
            record = {k: v for k, v in record.items() if k != "storage_failure"}
            record["storage_revision"] = info[2].get("storage_revision", 0)
            if journal:
                journal.write(world_id, work_id, record)
            if received is not None:
                received[work_id] = record
        stored_first = info[2].get("storage_first")
        if stored_first and (datetime.now(UTC)-datetime.fromisoformat(stored_first)).total_seconds() >= 120:
            await local(mark_failed, session_factory, work_id, "relationship_storage_retry_exhausted")
            return "needs_attention"
        failure = (record or {}).get("storage_failure", {})
        if failure and (failure.get("rounds", 0) >= 3 or
            (datetime.now(UTC)-datetime.fromisoformat(failure["first_at"])).total_seconds() >= 120):
            await local(mark_failed, session_factory, work_id, "relationship_storage_retry_exhausted")
            return "needs_attention"
        if record is not None and "result" in record:
            validate_review_result(record["result"], partial=record["partial"], allowed_refs=set(record["allowed_refs"]))
        outcome = await _run_review_step(session_factory, work_id=work_id, references_factory=references_factory,
            provider_factory=provider_factory, now=now, timeout=timeout, journal=journal,
            received=received, database_work=database_work)
        if outcome == "local_result_pending":
            outcome = await defer_storage()
        return outcome
    except ValueError as exc:
        from app.core.result_journal import ResultJournalError
        if isinstance(exc, ResultJournalError):
            await local(mark_failed, session_factory, work_id, "result_journal_invalid")
            return "result_journal_invalid"
        code = str(exc) if str(exc).startswith("relationship_") else "relationship_review_result_invalid"
        record = (received or {}).get(work_id) or record
        await local(mark_failed, session_factory, work_id, code)
        if record is not None and journal:
            try:
                journal.quarantine(world_id, work_id, record, reason=code)
            except (OSError, ValueError):
                # Retain the original file on quarantine failure. Its terminal
                # DB state still excludes this poison response from replay.
                pass
        if received is not None:
            received.pop(work_id, None)
        return "needs_attention"
    except Exception as exc:
        if retryable(exc):
            return await defer_storage()
        raise


async def _run_review_step(session_factory, *, work_id: str, references_factory,
                          provider_factory, now=None, timeout: float = 120.0,
                          journal=None, received=None, database_work=None) -> str:
    """One provider submission, followed by independently replayable local storage."""
    import asyncio
    from app.core.sqlite_concurrency import is_sqlite_contention
    from app.core.database_transactions import database_write
    from app.core.result_journal import ResultJournalError
    from app.domains.relationships.service.review_delivery import persist_received, may_publish
    clock = now or (lambda: datetime.now(UTC))
    received = received if received is not None else {}
    async def local_work(function, *args):
        if database_work is not None:
            return await database_work(function, *args)
        return function(*args)

    def read_world():
        with session_factory() as db:
            work = db.get(RelationshipReviewWork, work_id)
            return None if work is None else work.world_id

    world_id = await local_work(read_world)
    if world_id is None:
        received.pop(work_id, None)
        return "lease_lost"
    try:
        record = received.get(work_id) or (journal.read(world_id, work_id) if journal else None)
    except ResultJournalError:
        return "result_journal_invalid"
    if record is not None:
        if "result" not in record:
            def mark_unknown():
                with session_factory() as db:
                    def write():
                        row = db.get(RelationshipReviewWork, work_id, populate_existing=True)
                        if row is not None and row.error_code == "relationship_review_outcome_unknown" and row.attempts == record["attempt"]:
                            return "outcome_unknown"
                        if row is not None and row.lease_token == record["lease"] and row.attempts == record["attempt"]:
                            row.status, row.error_code = "failed", "relationship_review_outcome_unknown"
                            row.lease_token, row.lease_until = None, None
                            return "outcome_unknown"
                        return "lease_lost"
                    return database_write(db, write, require_clean=True)
            outcome = await local_work(mark_unknown)
            if outcome == "lease_lost" and journal:
                journal.remove(world_id, work_id)
            return outcome  # Sent, but no durable response survived.
        try:
            if journal:
                journal.write(world_id, work_id, record)
            outcome = await local_work(persist_received, session_factory, work_id, record, references_factory)
            if journal:
                journal.remove(world_id, work_id)
            received.pop(work_id, None)
            return outcome
        except Exception as exc:
            if is_sqlite_contention(exc) or isinstance(exc, (OSError, ResultJournalError)):
                return "local_result_pending"
            if isinstance(exc, ValueError):
                raise
            raise
    lease = uuid7_string()
    def claim_work():
        with session_factory() as db:
            def claim():
                current = clock()
                work = db.get(RelationshipReviewWork, work_id, populate_existing=True)
                if work is None:
                    return "lease_lost"
                from app.domains.relationships.service.review_recovery import stopped
                if stopped(work) or stopped(root_work(db, work)):
                    return "needs_attention"
                if work.status in {"ready", "applied", "stale"}:
                    return work.status
                if work.error_code == "relationship_review_outcome_unknown":
                    return "outcome_unknown"
                if work.lease_until:
                    until = work.lease_until.replace(tzinfo=UTC) if work.lease_until.tzinfo is None else work.lease_until
                    if until > current:
                        return "leased"
                try:
                    root = root_work(db, work)
                    references_factory(db).revalidate(root)
                    payload = build_payload(db, work)
                except ValueError as exc:
                    work.status, work.error_code = "failed", str(exc) if str(exc).startswith("relationship_") else "relationship_review_validation_failed"
                    from app.domains.relationships.service.review_recovery import fail
                    fail(db, work, work.error_code, now=current)
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
            return database_write(db, claim, require_clean=True)
    try:
        claimed = await local_work(claim_work)
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
    raw = None
    try:
        started = perf_counter()
        provider = provider_factory(material)
        raw = await provider.review(payload, partial=record["partial"], timeout=timeout)
        result = validate_review_result(raw, partial=record["partial"], allowed_refs=set(record["allowed_refs"]))
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        if journal:
            try:
                if raw is not None:
                    journal.quarantine(world_id, work_id, {**record, "invalid_result": raw}, reason="relationship_review_result_invalid")
                else:
                    journal.remove(world_id, work_id)
            except (OSError, ValueError):
                pass  # Failure classification must still release this work.
        def fail_work(error=exc):
            with session_factory() as db:
                def fail():
                    row = db.get(RelationshipReviewWork, work_id, populate_existing=True)
                    if row is None or row.lease_token != lease:
                        return "lease_lost"
                    if isinstance(error, ReviewNeedsSplit) and split_incomplete_work(db, row, payload):
                        return "split_pending"
                    code = getattr(error, "provider_code", None)
                    control = row.maintenance or {}
                    if code in {429, 503} and row.attempts - control.get("provider_base", 0) < 2:
                        row.status, row.lease_token, row.lease_until = "pending", None, None
                        row.error_code = "relationship_provider_retry_wait"
                        row.next_attempt_at = getattr(error, "retry_after", None) or clock() + timedelta(seconds=30)
                        return "retry_pending"
                    from app.domains.relationships.service.review_recovery import fail
                    reason = str(error) if isinstance(error, ValueError) and str(error).startswith("relationship_") else getattr(error, "reason_code", None) or getattr(error, "failure_class", None) or "relationship_review_retry_required"
                    fail(db, row, reason, now=clock())
                    return "needs_attention"
                return database_write(db, fail, require_clean=True)
        try:
            return await local_work(fail_work)
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
        # Persist the received response before the first cancellable DB await.
        # A shutdown can then recover this exact attempt without another AI call.
        if journal:
            journal.write(world_id, work_id, record)
        if not await local_work(may_publish, session_factory, work_id, record, clock()):
            received.pop(work_id, None)
            if journal:
                journal.remove(world_id, work_id)
            return "lease_lost"
        outcome = await local_work(persist_received, session_factory, work_id, record, references_factory)
        if journal:
            journal.remove(world_id, work_id)
        received.pop(work_id, None)
        return outcome
    except Exception as exc:
        if is_sqlite_contention(exc) or isinstance(exc, (OSError, ResultJournalError)):
            return "local_result_pending"
        if isinstance(exc, ValueError):
            raise
        raise


def apply_review(db: Session, *, work_id: str, references: ReviewReferences, now: datetime) -> str:
    root = db.scalar(select(RelationshipReviewWork).where(RelationshipReviewWork.id == work_id).with_for_update())
    if root is None or root.parent_id is not None:
        raise ValueError("relationship_review_root_invalid")
    if root.status == "applied":
        return "applied"
    if root.status != "ready" or root.result is None:
        return "not_ready"
    if root.manifest.get("input_policy") != REVIEW_INPUT_POLICY:
        raise ValueError("relationship_review_input_policy_changed")
    db.execute(update(RelationshipReviewWork).where(RelationshipReviewWork.id == root.id,
        RelationshipReviewWork.status == "ready").values(status="ready"))
    db.refresh(root)
    if root.status != "ready":
        return root.status
    references.revalidate(root)
    if root.phase == "final" and any(part.status != "ready" for part in review_children(db, root.id)):
        return "not_ready"
    state = _relationship_state(db, world_id=root.world_id, actor_world_character_id=root.actor_world_character_id,
                                target_world_character_id=root.target_world_character_id)
    db.refresh(state)
    if state.view_version != root.expected_view_version:
        # Rebase on the new normal view. Old partial interpretations depended on
        # the former view, so only this pair is re-prepared; receipts stay pending.
        rebase_review(db, root, state)
        return "rebased"
    result = validate_review_result(verified_result(root), partial=False,
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
            row.manifest = {"input_policy": REVIEW_INPUT_POLICY,
                "payload": {**row.manifest["payload"], **prompt_base(base)}}
        elif row.parent_id:
            row.manifest = {"input_policy": REVIEW_INPUT_POLICY, "base": base}
        row.manifest_digest = manifest_digest(row.manifest)
        for child in review_children(db, row.id):
            reset(child)
    reset(root)


def split_incomplete_work(db, work, payload):
    key = "memories" if "memories" in payload else "partial_results"
    entries = payload[key]
    if len(entries) < 2:
        return False
    base = {k: v for k, v in payload.items() if k != key}
    groups = [entries[:len(entries)//2], entries[len(entries)//2:]]
    children = review_children(db, work.id)
    if key == "memories":
        if work.parent_id is None:
            work.phase = "final"
            work.manifest = {**work.manifest, "memories": [{k: v for k, v in m.items() if k != "summary"}
                for m in work.manifest["memories"]]}
        else:
            work.phase, work.manifest = "reduce", {"input_policy": REVIEW_INPUT_POLICY, "base": base}
        for group in groups:
            new_work(db, world_id=work.world_id, actor_id=work.actor_world_character_id,
                target_id=work.target_world_character_id, period_key=work.period_key,
                part_key=f"split-{uuid7_string()}", phase="partial",
                manifest={"input_policy": REVIEW_INPUT_POLICY, "payload": {**base, "memories": group}},
                view_version=work.expected_view_version, parent_id=work.id)
    else:
        for group in groups:
            part = new_work(db, world_id=work.world_id, actor_id=work.actor_world_character_id,
                target_id=work.target_world_character_id, period_key=work.period_key,
                part_key=f"reduce-{uuid7_string()}", phase="reduce", manifest={"input_policy": REVIEW_INPUT_POLICY, "base": base},
                view_version=work.expected_view_version, parent_id=work.id)
            ids = {entry["part_id"] for entry in group}
            for child in children:
                if child.id in ids:
                    child.parent_id = part.id
    work.manifest_digest = manifest_digest(work.manifest)
    work.status, work.result, work.error_code = "pending", None, "relationship_review_split_after_incomplete"
    work.lease_token, work.lease_until, work.next_attempt_at = None, None, None
    return True
