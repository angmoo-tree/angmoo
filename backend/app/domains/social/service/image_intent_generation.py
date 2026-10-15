"""Post-owned intents and durable generation execution, independent of HTTP routes."""
import asyncio
import base64
import hashlib
import json
import logging
import os
from dataclasses import asdict, dataclass
from threading import Lock
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

from sqlalchemy import select, update
from sqlalchemy.exc import SQLAlchemyError

from app.domains.media.contracts import ImagePreparationError, ImageSubmissionError, InvalidProfileMediaError
from app.domains.social.models.posts import Post, PostMedia, PostImageGenerationJob
from app.domains.social.models.image_intents import ImageIntent, ImageGenerationAttempt
from app.domains.social.service.generation_usage import reserve_attempt
from app.domains.media.service.comfy_workflows import freeze_comfy_request
from app.domains.media.schemas import diagnostic_projection
from app.domains.media.contracts import GENERATED_ASSET_MAX_BYTES
from app.core.sqlite_concurrency import is_sqlite_contention, sqlite_error_identity


@dataclass(frozen=True)
class ResultBinding:
    job_id: int
    attempt_id: str
    owner_id: str
    world_id: str
    intent_id: str
    source_revision: str
    settings_revision: int
    request_hash: str


@dataclass
class ReceivedSlot:
    binding: ResultBinding
    token: str
    result: object = None


def source_revision(post):
    # The existing text guard is deliberately independent of the media guard.
    return hashlib.sha256(f"{post.title}\n{post.body}".encode()).hexdigest()


def admit(db, *, post, owner_id, character_id, scene, scene_error, prepare, quota_day, reserve=reserve_attempt):
    """Called inside publication's transaction. No Provider call or implicit commit."""
    prepared = prepare(db, owner_id, character_id, scene, scene_error)
    if prepared is None:
        return None
    request, credential, revision, limit, error = prepared
    identity = hashlib.sha256(f"{post.id}|{source_revision(post)}|{revision}".encode()).hexdigest()
    if existing := db.get(ImageIntent, identity):
        return existing
    if request is not None and not error:
        try:
            request = freeze_comfy_request(request)
        except ImagePreparationError as exc:
            request, error = None, str(exc)
    intent = ImageIntent(id=identity, post_id=post.id, source_revision=source_revision(post),
        settings_revision=revision, scene=scene if isinstance(scene, str) else "", request_json=json.dumps(asdict(request) if request else {}),
        credential_id=credential.id if credential else None, credential_revision=credential.revision if credential else None,
        state="blocked" if error else "queued", reason=error)
    db.add(intent)
    db.flush()
    if error:
        return intent
    job = PostImageGenerationJob(post_id=post.id, intent_id=intent.id, character_id=character_id,
        user_id=owner_id, source="routine_v2", status="queued", image_model=request.model,
        image_prompt=request.positive, prompt_hash=hashlib.sha256(request.positive.encode()).hexdigest(),
        reference_source=request.reference.source, key_source="user", attempt_count=0)
    db.add(job)
    db.flush()
    try:
        reserve(db, job_id=job.id, owner_id=owner_id, character_id=character_id,
            character_limit=limit, quota_day=quota_day)
    except ImagePreparationError as exc:
        # A cap never turns today's blocked posts into tomorrow's backlog.
        intent.state, intent.reason = "blocked", str(exc)
        job.status, job.skip_reason = "skipped", str(exc)
    return intent


class GenerationWorker:
    def __init__(self, sessions, assets, execution, *, spool: Path, clock=lambda: datetime.now(timezone.utc), local_work=None):
        self.sessions, self.assets, self.execution = sessions, assets, execution
        self.spool, self.clock = spool, clock
        self._local_work = local_work
        self.task = None
        self.stopping = False
        # Reserve before submission; never evict the only received copy.
        self.received_results = {}
        self._buffer_lock = Lock()
        self._active_jobs = set()

    def owned_job(self, db, owner_id, post_id):
        job = db.scalar(select(PostImageGenerationJob).where(PostImageGenerationJob.post_id == post_id,
            PostImageGenerationJob.user_id == owner_id, PostImageGenerationJob.intent_id.is_not(None))
            .order_by(PostImageGenerationJob.id.desc()))
        if job is None:
            raise ImagePreparationError("image_job_not_found")
        self.execution.authorize_job(db, job)
        return job

    def view_for_post(self, db, owner_id, post_id):
        post = db.get(Post, post_id)
        if post is None or post.deleted_at or not self.execution.owns_post(db, owner_id, post):
            return None
        job = db.scalar(select(PostImageGenerationJob).where(PostImageGenerationJob.post_id == post_id,
            PostImageGenerationJob.user_id == owner_id, PostImageGenerationJob.intent_id.is_not(None))
            .order_by(PostImageGenerationJob.id.desc()))
        if job:
            self.execution.authorize_job(db, job)
            value = self.view(job)
            if job.status == "failed" and (job.result_asset_id or db.scalar(select(ImageGenerationAttempt.id).where(
                    ImageGenerationAttempt.job_id == job.id, ImageGenerationAttempt.status.in_(("result_received", "succeeded"))).limit(1))):
                value["retryable"] = False
            return value
        intent = db.scalar(select(ImageIntent).where(ImageIntent.post_id == post_id).order_by(ImageIntent.created_at.desc()))
        if intent is None:
            return None
        return {"job_id": None, "post_id": post_id, "status": intent.state, "reason": intent.reason,
            "attempt_count": 0, "reference_source": None, "model": None, "cancellable": False, "retryable": False}

    @staticmethod
    def view(job):
        return {"job_id": job.id, "post_id": job.post_id, "status": job.status,
            "reason": job.failure_class or job.skip_reason, "attempt_count": job.attempt_count,
            "provider_diagnostic": diagnostic_projection(job.provider_diagnostic_json),
            "reference_source": job.reference_source, "model": job.image_model,
            "cancellable": job.status in {"queued", "running", "result_pending", "result_ready"},
            "retryable": job.status in {"failed", "result_pending", "result_ready"} or (job.status == "outcome_unknown" and bool(job.provider_receipt))}

    def _transition_attempt(self, db, attempt):
        transition = getattr(self.execution, "transition_attempt", None)
        if transition is not None:
            transition(db, attempt.id, attempt.status)

    def cancel(self, db, owner_id, post_id):
        job = self.owned_job(db, owner_id, post_id)
        if job.status == "cancelled":
            return self.view(job)
        if job.status not in {"queued", "running", "result_pending", "result_ready"}:
            raise ImagePreparationError("image_job_not_cancellable")
        changed = db.execute(update(PostImageGenerationJob).where(PostImageGenerationJob.id == job.id,
            PostImageGenerationJob.status == job.status, PostImageGenerationJob.lease_token == job.lease_token)
            .values(status="cancelled", lease_token=None, lease_until=None, finished_at=self.clock()))
        if changed.rowcount != 1:
            raise ImagePreparationError("image_job_changed")
        intent = db.get(ImageIntent, job.intent_id)
        intent.state, intent.reason = "cancelled", "user_cancelled"
        for attempt in db.scalars(select(ImageGenerationAttempt).where(ImageGenerationAttempt.job_id == job.id,
            ImageGenerationAttempt.status == "reserved")):
            attempt.status = "released"
            self._transition_attempt(db, attempt)
        db.refresh(job)
        return self.view(job)

    def retry(self, db, owner_id, post_id, quota_day):
        job = self.owned_job(db, owner_id, post_id)
        # Duplicate clicks see the same queued/running job; no second reservation.
        if job.status in {"queued", "running", "result_pending", "result_ready"}:
            return self.view(job)
        if (slot := self._slot(job.id)) is not None and slot.result is not None:
            raise ImagePreparationError("image_received_result_no_resubmit")
        if job.status not in {"failed", "outcome_unknown"}:
            raise ImagePreparationError("image_job_not_retryable")
        self.execution.prepare(db, job, db.get(ImageIntent, job.intent_id))
        if job.status == "outcome_unknown":
            if not job.provider_receipt:
                raise ImagePreparationError("image_outcome_unknown_no_resubmit")
            changed = db.execute(update(PostImageGenerationJob).where(PostImageGenerationJob.id == job.id,
                PostImageGenerationJob.status == "outcome_unknown").values(status="running", lease_until=self.clock()))
        else:
            if job.result_asset_id or db.scalar(select(ImageGenerationAttempt.id).where(
                ImageGenerationAttempt.job_id == job.id, ImageGenerationAttempt.status == "result_received")):
                raise ImagePreparationError("image_received_result_no_resubmit")
            changed = db.execute(update(PostImageGenerationJob).where(PostImageGenerationJob.id == job.id,
                PostImageGenerationJob.status == "failed").values(status="queued", lease_token=None,
                lease_until=None, provider_receipt=None))
        if changed.rowcount != 1:
            raise ImagePreparationError("image_job_changed")
        if job.status == "queued":
            self.execution.reserve_attempt(db, job_id=job.id, owner_id=owner_id, character_id=job.character_id,
                character_limit=self.execution.character_limit(db, job.character_id), quota_day=quota_day)
        job.failure_class = None
        job.provider_diagnostic_json = None
        intent = db.get(ImageIntent, job.intent_id)
        intent.state, intent.reason = "queued", None
        db.refresh(job)
        return self.view(job)

    async def start(self):
        if self.task is not None and not self.task.done():
            return
        self.stopping = False
        self.task = asyncio.create_task(self.run())

    async def stop(self):
        self.stopping = True
        if self.task:
            try:
                await asyncio.wait_for(asyncio.shield(self.task), 15)
            except asyncio.TimeoutError:
                self.task.cancel()
                await asyncio.gather(self.task, return_exceptions=True)
            self.task = None

    async def run(self):
        while not self.stopping:
            try:
                await self.tick()
            except Exception as exc:
                code, name = sqlite_error_identity(exc)
                logging.getLogger(__name__).warning("image_worker_local_failure type=%s stage=%s retryable_busy=%s sqlite_code=%s sqlite_name=%s",
                    type(exc).__name__, getattr(exc, "image_local_stage", "tick"), is_sqlite_contention(exc), code, name)
            await asyncio.sleep(1)

    async def _local(self, operation, *args):
        # Runtime supplies an owned bounded worker; synchronous domain fixtures
        # may execute the same operation directly without transporting Sessions.
        try:
            if self._local_work is None:
                return operation(*args)
            return await self._local_work(operation, *args)
        except Exception as exc:
            exc.image_local_stage = operation.__name__
            raise

    async def tick(self):
        for job_id in await self._local(self._pending_jobs):
            await self.process(job_id)

    def _pending_jobs(self):
        with self.sessions() as db:
            with self._buffer_lock:
                slots = tuple(self.received_results.values())
            for slot in slots:
                row = db.get(PostImageGenerationJob, slot.binding.job_id)
                with self._buffer_lock:
                    active = slot.binding.job_id in self._active_jobs
                attempt = db.get(ImageGenerationAttempt, slot.binding.attempt_id)
                if (not active and slot.result is None and row is not None and attempt is not None
                        and attempt.status == "reserved" and row.status == "running" and row.lease_token == slot.token):
                    # A cancelled prepare waiter can leave an owned worker
                    # finishing its reservation. The canonical queue orders this
                    # reconciliation after that future; reserved proves no submit.
                    changed = db.execute(update(PostImageGenerationJob).where(PostImageGenerationJob.id == row.id,
                        PostImageGenerationJob.status == "running", PostImageGenerationJob.lease_token == slot.token)
                        .values(status="queued", lease_token=None, lease_until=None))
                    db.commit()
                    if changed.rowcount == 1:
                        self._release(slot.binding)
                    continue
                if row is None or row.status in {"cancelled", "succeeded", "failed", "skipped"}:
                    self._remove_journal(slot.binding)
                    self._release(slot.binding)
            for manifest in self.spool.glob("*.json"):
                if not manifest.stem.isdecimal():
                    continue
                row = db.get(PostImageGenerationJob, int(manifest.stem))
                if row is None or row.status in {"cancelled", "succeeded", "failed", "skipped"}:
                    # Acquire the writer before a fresh terminal check. A retry
                    # cannot install a new attempt while its files are removed.
                    db.execute(update(PostImageGenerationJob).where(PostImageGenerationJob.id == int(manifest.stem))
                        .values(id=PostImageGenerationJob.id))
                    row = db.get(PostImageGenerationJob, int(manifest.stem), populate_existing=True)
                    if row is not None and row.status not in {"cancelled", "succeeded", "failed", "skipped"}:
                        db.rollback()
                        continue
                    if row is not None:
                        stored = json.loads(manifest.read_text("utf-8"))
                        if stored.get("binding") not in (None, asdict(self._binding(db, row))):
                            db.rollback()
                            continue
                    for path in self._spool_paths(manifest.stem):
                        path.unlink(missing_ok=True)
                    db.commit()
            jobs = list(db.scalars(select(PostImageGenerationJob.id).where(
                PostImageGenerationJob.intent_id.is_not(None),
                PostImageGenerationJob.status.in_(("queued", "running", "result_pending", "result_ready"))).order_by(PostImageGenerationJob.id).limit(8)))
        return tuple(jobs)

    def _spool_paths(self, job_id):
        return self.spool / f"{job_id}.pixels", self.spool / f"{job_id}.json"

    def _write_received(self, job_id, result, binding):
        pixels_path, manifest_path = self._spool_paths(job_id)
        metadata = {"content_type": result.content_type, "receipt": result.receipt, "usage": result.usage,
            "diagnostic": diagnostic_projection(result.diagnostic),
            "content_base64": base64.b64encode(result.content).decode("ascii"),
            "journal_version": 1, "binding": asdict(binding),
            "byte_size": len(result.content), "content_hash": hashlib.sha256(result.content).hexdigest()}
        # Serialization/hash are prepared before acquiring the writer fence.
        stamp = None
        if manifest_path.is_file():
            before = manifest_path.stat()
            previous = json.loads(manifest_path.read_text("utf-8"))
            after = manifest_path.stat()
            stamp = (before.st_ino, before.st_size, before.st_mtime_ns)
            if stamp != (after.st_ino, after.st_size, after.st_mtime_ns) or previous.get("binding") not in (None, asdict(binding)):
                raise RuntimeError("image_journal_attempt_conflict")
        return metadata, json.dumps(metadata).encode("utf-8"), stamp

    def _store_journal(self, job_id, content, encoded, stamp):
        pixels_path, manifest_path = self._spool_paths(job_id)
        current = manifest_path.stat() if manifest_path.is_file() else None
        if stamp != (None if current is None else (current.st_ino, current.st_size, current.st_mtime_ns)):
            raise RuntimeError("image_journal_changed_before_fence")
        self.spool.mkdir(parents=True, exist_ok=True)
        # One atomic journal contains both pixels and metadata. The separate
        # pixel file remains readable by existing recovery/backup consumers.
        for path, value in ((manifest_path, encoded), (pixels_path, content)):
            temporary = path.with_suffix(path.suffix + ".tmp")
            with temporary.open("wb") as output:
                output.write(value)
                output.flush()
                os.fsync(output.fileno())
            temporary.replace(path)

    def _read_received(self, job_id, binding, *, legacy_proven=False):
        pixels_path, manifest_path = self._spool_paths(job_id)
        if manifest_path.is_file():
            if manifest_path.stat().st_size > GENERATED_ASSET_MAX_BYTES * 2:
                raise ValueError("image_journal_too_large")
            metadata = json.loads(manifest_path.read_text("utf-8"))
            if "journal_version" not in metadata and not legacy_proven:
                raise ValueError("image_legacy_journal_attempt_unproven")
            content = base64.b64decode(metadata["content_base64"], validate=True) if "content_base64" in metadata else pixels_path.read_bytes()
            if len(content) > GENERATED_ASSET_MAX_BYTES:
                raise ValueError("image_journal_too_large")
            if "journal_version" in metadata and (metadata["journal_version"] != 1
                    or metadata.get("binding") != asdict(binding)
                    or metadata.get("byte_size") != len(content)
                    or metadata.get("content_hash") != hashlib.sha256(content).hexdigest()):
                raise ValueError("image_journal_binding_invalid")
            return content, metadata
        return None

    def _slot(self, job_id):
        with self._buffer_lock:
            return next((slot for key, slot in self.received_results.items() if key[0] == job_id), None)

    def _release(self, binding):
        with self._buffer_lock:
            self.received_results.pop((binding.job_id, binding.attempt_id), None)

    def _remove_journal(self, binding):
        _, manifest = self._spool_paths(binding.job_id)
        if manifest.is_file():
            metadata = json.loads(manifest.read_text("utf-8"))
            if metadata.get("binding") not in (None, asdict(binding)):
                return  # A stale worker cannot delete another attempt's journal.
        for path in self._spool_paths(binding.job_id):
            path.unlink(missing_ok=True)

    def _binding(self, db, job):
        intent = db.get(ImageIntent, job.intent_id)
        attempts = list(db.scalars(select(ImageGenerationAttempt).where(ImageGenerationAttempt.job_id == job.id)))
        active = [value for value in attempts if value.status in {"reserved", "submitted", "outcome_unknown", "result_received"}]
        candidates = active or [value for value in attempts if value.status == "succeeded"] or attempts
        if len(candidates) != 1:
            raise ImagePreparationError("image_result_attempt_ambiguous")
        attempt = candidates[0]
        post = db.get(Post, job.post_id)
        if intent is None or attempt is None or post is None:
            raise ImagePreparationError("image_result_scope_missing")
        return ResultBinding(job.id, attempt.id, job.user_id, post.world_id, intent.id,
            intent.source_revision, intent.settings_revision, hashlib.sha256(intent.request_json.encode()).hexdigest())

    async def process(self, job_id):
        with self._buffer_lock:
            if job_id in self._active_jobs:
                return
            self._active_jobs.add(job_id)
        try:
            await self._process(job_id)
        finally:
            with self._buffer_lock:
                self._active_jobs.discard(job_id)

    async def _process(self, job_id):
        token = uuid4().hex
        try:
            prepared = await self._local(self._prepare_job, job_id, token)
        except BaseException as exc:
            slot = self._slot(job_id)
            if slot and slot.result is None and not isinstance(exc, asyncio.CancelledError):
                self._release(slot.binding)
            raise
        if prepared is None:
            return
        execution, binding = prepared
        async def submission_started():
            await self._local(self._submission_started, job_id, token)
        async def receipt_received(receipt):
            nonlocal received_receipt
            received_receipt = receipt
            await self._local(self._receipt_received, job_id, token, receipt)
        async def diagnostic_received(value):
            await self._local(self._diagnostic_received, job_id, token, value)
        result = None
        received_receipt = None
        cancelled = False
        try:
            result = await self.execution.submit(execution, on_receipt=receipt_received,
                on_submit=submission_started, on_diagnostic=diagnostic_received)
            if len(result.content) > GENERATED_ASSET_MAX_BYTES:
                raise ImagePreparationError("generation_result_pixels_invalid")
            # Synchronous handoff: no DB operation or await can lose this result.
            with self._buffer_lock:
                self.received_results[(job_id, binding.attempt_id)].result = result
            await self._local(self._receive_result, job_id, token, result)
        except asyncio.CancelledError:
            cancelled = True
            raise  # Submitted work remains recoverable; no cancellation refund.
        except Exception as exc:
            await self._local(self._failed_result, job_id, token, exc, result, received_receipt)
        finally:
            slot = self._slot(job_id)
            if slot and slot.result is None and not cancelled:
                self._release(slot.binding)

    def _prepare_job(self, job_id, token):
        with self.sessions() as db:
            job = db.get(PostImageGenerationJob, job_id)
            if job is None or job.intent_id is None:
                return
            if job.status not in {"queued", "running", "result_pending", "result_ready"}:
                return
            if job.status == "result_ready":
                self._attach(db, job)
                if (slot := self._slot(job_id)) is not None and job.status == "succeeded":
                    self._remove_journal(slot.binding)
                    self._release(slot.binding)
                return
            pixels_path, manifest_path = self._spool_paths(job_id)
            slot = self._slot(job_id)
            if manifest_path.is_file() or (slot and slot.result is not None):
                now = self.clock()
                if job.lease_until and job.lease_until.replace(tzinfo=timezone.utc) > now and (slot is None or slot.token != job.lease_token):
                    return
                binding = self._binding(db, job)
                legacy_proven = db.get(ImageGenerationAttempt, binding.attempt_id).status in {"submitted", "outcome_unknown", "result_received", "succeeded"}
                if slot and slot.binding != binding:
                    self._release(slot.binding)
                    return
                claim = db.execute(update(PostImageGenerationJob).where(PostImageGenerationJob.id == job.id,
                    PostImageGenerationJob.status == job.status, PostImageGenerationJob.lease_token == job.lease_token)
                    .values(status="running", lease_token=token, lease_until=now + timedelta(minutes=5)))
                if claim.rowcount != 1:
                    db.rollback()
                    return
                db.commit()
                db.refresh(job)
                try:
                    db.close()
                    if slot and slot.result is not None:
                        slot.token = token
                        self._receive_result(job_id, token, slot.result)
                        return
                    content, metadata = self._read_received(job_id, binding, legacy_proven=legacy_proven)
                    job = db.get(PostImageGenerationJob, job_id)
                    self._persist_result(db, job, content, metadata)
                    self._release(binding)
                except (OSError, ValueError, RuntimeError, SQLAlchemyError) as exc:
                    db.rollback()
                    current = db.get(PostImageGenerationJob, job_id)
                    if current and current.lease_token == token:
                        current.status, current.lease_until = "running", self.clock()
                        try:
                            durable = self._read_received(job_id, binding, legacy_proven=legacy_proven) is not None
                        except (OSError, ValueError, KeyError):
                            durable = False
                        if durable:
                            current.status = "result_pending"
                        elif slot is None or slot.result is None:
                            self._fail(db, current, "generation_result_journal_invalid", unknown=True)
                            return
                        if isinstance(exc, SQLAlchemyError) and not is_sqlite_contention(exc):
                            current.status, current.failure_class = "outcome_unknown", "generation_local_storage_error"
                        else:
                            current.failure_class = "local_result_persistence_pending"
                        db.commit()
                return
            now = self.clock()
            if job.status in {"running", "result_pending"}:
                if job.lease_until and job.lease_until.replace(tzinfo=timezone.utc) > now:
                    return
                if not job.provider_receipt:
                    self._fail(db, job, "generation_outcome_unknown", unknown=True)
                    return
            elif job.status != "queued":
                return
            previous_status = job.status
            claim = db.execute(update(PostImageGenerationJob).where(
                PostImageGenerationJob.id == job.id, PostImageGenerationJob.status == previous_status,
                PostImageGenerationJob.lease_token == job.lease_token).values(
                status="running", lease_token=token, lease_until=now + timedelta(minutes=5), started_at=now))
            if claim.rowcount != 1:
                db.rollback()
                return
            db.refresh(job)
            intent = db.get(ImageIntent, job.intent_id)
            try:
                execution = self.execution.prepare(db, job, intent)
                # Enrich only a never-submitted legacy job in its leased write transition.
                if previous_status == "queued" and not job.provider_receipt and execution.request.provider == "comfyui" and execution.request.comfy_execution is None:
                    frozen = freeze_comfy_request(execution.request)
                    intent.request_json = json.dumps(asdict(frozen))
                    execution.request = frozen
            except Exception as exc:
                self._fail(db, job, str(exc) if isinstance(exc, ImagePreparationError) else "generation_preparation_failed", release=True)
                return
            attempt = db.scalar(select(ImageGenerationAttempt).where(ImageGenerationAttempt.job_id == job.id,
                ImageGenerationAttempt.status.in_(("reserved", "submitted", "outcome_unknown", "result_received")))
                .order_by(ImageGenerationAttempt.created_at.desc()))
            if attempt is None:
                self._fail(db, job, "generation_reservation_missing", release=True)
                return
            binding = self._binding(db, job)
            with self._buffer_lock:
                if len(self.received_results) >= 4:
                    db.rollback()
                    return
                self.received_results[(job_id, binding.attempt_id)] = ReceivedSlot(binding, token)
            db.commit()
        return execution, binding

    def _submission_started(self, job_id, token):
        with self.sessions() as submit_db:
            current = submit_db.get(PostImageGenerationJob, job_id)
            if current is None or current.status != "running" or current.lease_token != token:
                raise ImagePreparationError("image_job_changed_before_submission")
            # Recheck current ownership/settings immediately before external submission.
            self.execution.prepare(submit_db, current, submit_db.get(ImageIntent, current.intent_id))
            reserved = submit_db.scalar(select(ImageGenerationAttempt).where(ImageGenerationAttempt.job_id == job_id,
                ImageGenerationAttempt.status == "reserved"))
            if reserved is None:
                raise ImagePreparationError("generation_reservation_missing")
            reserved.status = "submitted"
            self._transition_attempt(submit_db, reserved)
            current.attempt_count += 1
            submit_db.commit()

    def _receipt_received(self, job_id, token, receipt):
        with self.sessions() as receipt_db:
            current = receipt_db.get(PostImageGenerationJob, job_id)
            if current and current.lease_token == token:
                current.provider_receipt = receipt
                for attempt in receipt_db.scalars(select(ImageGenerationAttempt).where(ImageGenerationAttempt.job_id == job_id,
                    ImageGenerationAttempt.status == "submitted")):
                    attempt.receipt = receipt
                receipt_db.commit()

    def _diagnostic_received(self, job_id, token, value):
        value = diagnostic_projection(value)
        if value is None:
            return
        with self.sessions() as diagnostic_db:
            diagnostic_db.execute(update(PostImageGenerationJob).where(PostImageGenerationJob.id == job_id,
                PostImageGenerationJob.status == "running", PostImageGenerationJob.lease_token == token)
                .values(provider_diagnostic_json=json.dumps(value)))
            diagnostic_db.commit()

    def _receive_result(self, job_id, token, result):
        slot = self._slot(job_id)
        if slot is None or slot.token != token:
            return
        binding = slot.binding
        metadata, encoded, stamp = self._write_received(job_id, result, binding)
        with self.sessions() as received_db:
            current = received_db.get(PostImageGenerationJob, job_id)
            claimed = received_db.execute(update(PostImageGenerationJob).where(
                PostImageGenerationJob.id == job_id, PostImageGenerationJob.status == "running",
                PostImageGenerationJob.lease_token == token).values(status="result_pending"))
            if current is None or claimed.rowcount != 1:
                self._release(binding)
                return
            # Hold only a local writer transaction while fencing and
            # spooling. A deletion cannot finish and then be followed by
            # a late provider response recreating its private files.
            self.execution.prepare(received_db, current, received_db.get(ImageIntent, current.intent_id))
            if self._binding(received_db, current) != binding:
                raise ImagePreparationError("image_result_binding_changed")
            self._store_journal(job_id, result.content, encoded, stamp)
            current.provider_receipt = result.receipt or current.provider_receipt
            for attempt in received_db.scalars(select(ImageGenerationAttempt).where(
                ImageGenerationAttempt.job_id == job_id, ImageGenerationAttempt.status.in_(("submitted", "outcome_unknown")))):
                attempt.status = "result_received"
                self._transition_attempt(received_db, attempt)
            received_db.commit()
            self._persist_result(received_db, current, result.content, metadata)
        self._release(binding)

    def _failed_result(self, job_id, token, exc, result, received_receipt):
        slot = self._slot(job_id)
        with self.sessions() as db:
            current = db.get(PostImageGenerationJob, job_id)
            if current and current.lease_token == token:
                if isinstance(exc, ImagePreparationError):
                    if slot:
                        self._remove_journal(slot.binding)
                        self._release(slot.binding)
                    self._fail(db, current, str(exc))
                elif slot and slot.result is not None:
                    durable = self._read_received(job_id, slot.binding) is not None
                    for attempt in db.scalars(select(ImageGenerationAttempt).where(ImageGenerationAttempt.job_id == job_id,
                        ImageGenerationAttempt.status.in_(("submitted", "outcome_unknown")))):
                        if durable:
                            attempt.status = "result_received"
                            self._transition_attempt(db, attempt)
                    current.status = "result_pending" if durable else "running"
                    current.lease_until = self.clock()
                    current.failure_class = "local_result_persistence_pending"
                    if isinstance(exc, SQLAlchemyError) and not is_sqlite_contention(exc):
                        # A malformed query/schema/LOCKED error is not BUSY.
                        # Preserve the received copy for explicit recovery,
                        # without repeatedly retrying a deterministic defect.
                        current.status, current.failure_class = "outcome_unknown", "generation_local_storage_error"
                    db.commit()
                else:
                    current.provider_receipt = received_receipt or current.provider_receipt
                    code = str(exc) if isinstance(exc, (ImagePreparationError, ImageSubmissionError)) else "generation_submission_failed"
                    if value := diagnostic_projection(getattr(exc, "diagnostic", None)):
                        current.provider_diagnostic_json = json.dumps(value)
                    self._fail(db, current, code, unknown=getattr(exc, "outcome_unknown", False) or (received_receipt is not None and not isinstance(exc, ImageSubmissionError)),
                        release=isinstance(exc, ImagePreparationError) and received_receipt is None)
            elif current is None or current.status in {"cancelled", "failed", "skipped"}:
                if slot:
                    self._remove_journal(slot.binding)
                    self._release(slot.binding)


    def _persist_result(self, db, job, content, metadata):
        job_id, token = job.id, job.lease_token
        binding = self._binding(db, job)
        db.close()
        # Decode/normalize with no read Session, transaction or writer held.
        try:
            prepared = self.assets.prepare_upload(metadata["content_type"], content, draft=False)
        except InvalidProfileMediaError:
            current = db.get(PostImageGenerationJob, job_id)
            if current is not None and current.lease_token == token:
                self._fail(db, current, "generation_result_pixels_invalid")
                self._remove_journal(binding)
            return
        job = db.get(PostImageGenerationJob, job_id)
        if job is None or job.status not in {"running", "result_pending"} or job.lease_token != token:
            return
        claimed = db.execute(update(PostImageGenerationJob).where(PostImageGenerationJob.id == job_id,
            PostImageGenerationJob.lease_token == token, PostImageGenerationJob.status == job.status)
            .values(status="result_pending"))
        if claimed.rowcount != 1 or self._binding(db, job) != binding:
            db.rollback()
            return
        try:
            self.execution.prepare(db, job, db.get(ImageIntent, job.intent_id))
        except (ImagePreparationError, InvalidProfileMediaError) as exc:
            self._fail(db, job, str(exc))
            self._remove_journal(binding)
            return
        if not job.result_asset_id:
            try:
                asset = self.assets.store_prepared(db, owner_id=job.user_id, scope_kind="world",
                    scope_id=db.get(Post, job.post_id).world_id, prepared=prepared, draft=False)
            except InvalidProfileMediaError:
                self._fail(db, job, "generation_result_pixels_invalid")
                for path in self._spool_paths(job.id):
                    path.unlink(missing_ok=True)
                return
            job.result_asset_id = asset.id
        job.provider_receipt = metadata.get("receipt") or job.provider_receipt
        if value := diagnostic_projection(metadata.get("diagnostic")):
            job.provider_diagnostic_json = json.dumps(value)
        job.status, job.lease_token, job.lease_until = "result_ready", None, None
        for attempt in db.scalars(select(ImageGenerationAttempt).where(ImageGenerationAttempt.job_id == job.id,
            ImageGenerationAttempt.status.in_(("submitted", "outcome_unknown", "result_received")))):
            attempt.status, attempt.usage_json = "succeeded", json.dumps(metadata.get("usage"))
            self._transition_attempt(db, attempt)
        asset_id = job.result_asset_id
        try:
            db.commit()
        except Exception:
            db.rollback()
            current = db.get(PostImageGenerationJob, job_id, populate_existing=True)
            if current is None or current.result_asset_id != asset_id:
                if "asset" in locals():
                    self.assets.discard_unregistered(db, asset)
                raise
            job = current
        self._remove_journal(binding)
        self._attach(db, job)

    def _attach(self, db, job):
        intent, post = db.get(ImageIntent, job.intent_id), db.get(Post, job.post_id)
        if post is None or post.deleted_at or source_revision(post) != intent.source_revision:
            self._fail(db, job, "post_source_changed")
            return
        try:
            self.execution.prepare(db, job, intent)
            asset, _ = self.assets.read(db, owner_id=job.user_id, asset_id=job.result_asset_id)
            existing = db.scalar(select(PostMedia).where(PostMedia.post_id == post.id))
            if existing is not None and existing.asset_id != asset.id:
                self._fail(db, job, "post_already_has_image")
                return
            if existing is None:
                db.add(PostMedia(post_id=post.id, asset_id=asset.id, source_kind="generated",
                    generation_intent_id=intent.id, url=f"/api/v1/media/assets/{asset.id}/content",
                    alt_text="AI가 생성한 게시글 이미지", model=job.image_model, prompt_hash=job.prompt_hash,
                    byte_size=asset.byte_size, width=asset.width, height=asset.height, key_source="user"))
            intent.state, job.status, job.finished_at = "attached", "succeeded", self.clock()
            job.failure_class = None
            db.commit()
        except (ImagePreparationError, InvalidProfileMediaError) as exc:
            db.rollback()
            self._fail(db, db.get(PostImageGenerationJob, job.id), str(exc))
        except Exception:
            db.rollback()
            current = db.get(PostImageGenerationJob, job.id)
            current.status, current.failure_class = "result_ready", "local_attachment_pending"
            db.commit()

    def _fail(self, db, job, code, *, unknown=False, release=False):
        job.status, job.failure_class = "outcome_unknown" if unknown else "failed", code[:120]
        job.lease_token, job.lease_until, job.finished_at = None, None, self.clock()
        intent = db.get(ImageIntent, job.intent_id)
        intent.state, intent.reason = job.status, code[:80]
        for attempt in db.scalars(select(ImageGenerationAttempt).where(ImageGenerationAttempt.job_id == job.id)):
            if attempt.status in {"reserved", "submitted", "outcome_unknown"}:
                attempt.status = "released" if attempt.status == "reserved" else "outcome_unknown" if unknown else "failed"
                self._transition_attempt(db, attempt)
        db.commit()
