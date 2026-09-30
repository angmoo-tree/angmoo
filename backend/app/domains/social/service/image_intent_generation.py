"""Post-owned intents and durable generation execution, independent of HTTP routes."""
import asyncio
import base64
from collections import OrderedDict
import hashlib
import json
import logging
import os
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

from sqlalchemy import select, update
from sqlalchemy.exc import SQLAlchemyError

from app.domains.media.contracts import ImagePreparationError, ImageSubmissionError, InvalidProfileMediaError
from app.domains.social.models.posts import Post, PostMedia, PostImageGenerationJob
from app.domains.social.models.image_intents import ImageIntent, ImageGenerationAttempt
from app.domains.social.service.generation_usage import reserve_attempt


def source_revision(post):
    # The existing text guard is deliberately independent of the media guard.
    return hashlib.sha256(f"{post.title}\n{post.body}".encode()).hexdigest()


def admit(db, *, post, owner_id, character_id, scene, scene_error, prepare, quota_day):
    """Called inside publication's transaction. No Provider call or implicit commit."""
    prepared = prepare(db, owner_id, character_id, scene, scene_error)
    if prepared is None:
        return None
    request, credential, revision, limit, error = prepared
    identity = hashlib.sha256(f"{post.id}|{source_revision(post)}|{revision}".encode()).hexdigest()
    if existing := db.get(ImageIntent, identity):
        return existing
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
        reserve_attempt(db, job_id=job.id, owner_id=owner_id, character_id=character_id,
            character_limit=limit, quota_day=quota_day)
    except ImagePreparationError as exc:
        # A cap never turns today's blocked posts into tomorrow's backlog.
        intent.state, intent.reason = "blocked", str(exc)
        job.status, job.skip_reason = "skipped", str(exc)
    return intent


class GenerationWorker:
    def __init__(self, sessions, assets, execution, *, spool: Path, clock=lambda: datetime.now(timezone.utc)):
        self.sessions, self.assets, self.execution = sessions, assets, execution
        self.spool, self.clock = spool, clock
        self.task = None
        self.stopping = False
        # Bounded recovery buffer for a failed disk write. The durable attempt
        # marker forbids resubmission even if this process subsequently exits.
        self.received_results = OrderedDict()

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
            return self.view(job)
        intent = db.scalar(select(ImageIntent).where(ImageIntent.post_id == post_id).order_by(ImageIntent.created_at.desc()))
        if intent is None:
            return None
        return {"job_id": None, "post_id": post_id, "status": intent.state, "reason": intent.reason,
            "attempt_count": 0, "reference_source": None, "model": None, "cancellable": False, "retryable": False}

    @staticmethod
    def view(job):
        return {"job_id": job.id, "post_id": job.post_id, "status": job.status,
            "reason": job.failure_class or job.skip_reason, "attempt_count": job.attempt_count,
            "reference_source": job.reference_source, "model": job.image_model,
            "cancellable": job.status in {"queued", "running", "result_pending", "result_ready"},
            "retryable": job.status in {"failed", "result_pending", "result_ready"} or (job.status == "outcome_unknown" and bool(job.provider_receipt))}

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
        db.refresh(job)
        return self.view(job)

    def retry(self, db, owner_id, post_id, quota_day):
        job = self.owned_job(db, owner_id, post_id)
        # Duplicate clicks see the same queued/running job; no second reservation.
        if job.status in {"queued", "running", "result_pending", "result_ready"}:
            return self.view(job)
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
            reserve_attempt(db, job_id=job.id, owner_id=owner_id, character_id=job.character_id,
                character_limit=self.execution.character_limit(db, job.character_id), quota_day=quota_day)
        job.failure_class = None
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
                logging.getLogger(__name__).warning("image_worker_local_failure:%s", type(exc).__name__)
            await asyncio.sleep(1)

    async def tick(self):
        with self.sessions() as db:
            for manifest in self.spool.glob("*.json"):
                if not manifest.stem.isdecimal():
                    continue
                row = db.get(PostImageGenerationJob, int(manifest.stem))
                if row is None or row.status in {"cancelled", "succeeded", "failed", "skipped"}:
                    for path in self._spool_paths(manifest.stem):
                        path.unlink(missing_ok=True)
            jobs = list(db.scalars(select(PostImageGenerationJob.id).where(
                PostImageGenerationJob.intent_id.is_not(None),
                PostImageGenerationJob.status.in_(("queued", "running", "result_pending", "result_ready"))).order_by(PostImageGenerationJob.id).limit(8)))
        for job_id in jobs:
            await self.process(job_id)

    def _spool_paths(self, job_id):
        return self.spool / f"{job_id}.pixels", self.spool / f"{job_id}.json"

    def _write_received(self, job_id, result):
        pixels_path, manifest_path = self._spool_paths(job_id)
        metadata = {"content_type": result.content_type, "receipt": result.receipt, "usage": result.usage,
            "content_base64": base64.b64encode(result.content).decode("ascii")}
        self.spool.mkdir(parents=True, exist_ok=True)
        # One atomic journal contains both pixels and metadata. The separate
        # pixel file remains readable by existing recovery/backup consumers.
        for path, value in ((manifest_path, json.dumps(metadata).encode("utf-8")), (pixels_path, result.content)):
            temporary = path.with_suffix(path.suffix + ".tmp")
            with temporary.open("wb") as output:
                output.write(value)
                output.flush()
                os.fsync(output.fileno())
            temporary.replace(path)
        return metadata

    def _read_received(self, job_id):
        pixels_path, manifest_path = self._spool_paths(job_id)
        if manifest_path.is_file():
            metadata = json.loads(manifest_path.read_text("utf-8"))
            content = base64.b64decode(metadata["content_base64"], validate=True) if "content_base64" in metadata else pixels_path.read_bytes()
            return content, metadata
        if job_id in self.received_results:
            result = self.received_results[job_id]
            return result.content, self._write_received(job_id, result)
        return None

    async def process(self, job_id):
        token = uuid4().hex
        with self.sessions() as db:
            job = db.get(PostImageGenerationJob, job_id)
            if job is None or job.intent_id is None:
                return
            if job.status not in {"queued", "running", "result_pending", "result_ready"}:
                return
            if job.status == "result_ready":
                self._attach(db, job)
                return
            pixels_path, manifest_path = self._spool_paths(job_id)
            if manifest_path.is_file() or job_id in self.received_results:
                now = self.clock()
                if job.lease_until and job.lease_until.replace(tzinfo=timezone.utc) > now:
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
                    content, metadata = self._read_received(job_id)
                    self._persist_result(db, job, content, metadata)
                    self.received_results.pop(job_id, None)
                except (OSError, ValueError, RuntimeError, SQLAlchemyError):
                    db.rollback()
                    current = db.get(PostImageGenerationJob, job_id)
                    if current.lease_token == token:
                        current.status, current.lease_until = "result_pending", self.clock()
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
            except Exception as exc:
                self._fail(db, job, str(exc) if isinstance(exc, ImagePreparationError) else "generation_preparation_failed", release=True)
                return
            attempt = db.scalar(select(ImageGenerationAttempt).where(ImageGenerationAttempt.job_id == job.id,
                ImageGenerationAttempt.status.in_(("reserved", "submitted", "outcome_unknown", "result_received")))
                .order_by(ImageGenerationAttempt.created_at.desc()))
            if attempt is None:
                self._fail(db, job, "generation_reservation_missing", release=True)
                return
            db.commit()
        async def submission_started():
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
                if reserved.quota_day != self.execution.quota_day():
                    raise ImagePreparationError("generation_reservation_day_expired")
                reserved.status = "submitted"
                current.attempt_count += 1
                submit_db.commit()
        async def receipt_received(receipt):
            nonlocal received_receipt
            received_receipt = receipt
            with self.sessions() as receipt_db:
                current = receipt_db.get(PostImageGenerationJob, job_id)
                if current and current.lease_token == token:
                    current.provider_receipt = receipt
                    for attempt in receipt_db.scalars(select(ImageGenerationAttempt).where(ImageGenerationAttempt.job_id == job_id,
                        ImageGenerationAttempt.status == "submitted")):
                        attempt.receipt = receipt
                    receipt_db.commit()
        result = None
        received_receipt = None
        try:
            result = await self.execution.submit(execution, on_receipt=receipt_received, on_submit=submission_started)
            self.received_results[job_id] = result
            while len(self.received_results) > 4:
                self.received_results.popitem(last=False)
            with self.sessions() as received_db:
                current = received_db.get(PostImageGenerationJob, job_id)
                if current and current.lease_token == token:
                    current.status = "result_pending"
                    current.provider_receipt = result.receipt or current.provider_receipt
                    for attempt in received_db.scalars(select(ImageGenerationAttempt).where(
                        ImageGenerationAttempt.job_id == job_id, ImageGenerationAttempt.status.in_(("submitted", "outcome_unknown")))):
                        attempt.status = "result_received"
                    received_db.commit()
            metadata = self._write_received(job_id, result)
            with self.sessions() as db:
                current = db.get(PostImageGenerationJob, job_id)
                if current and current.lease_token == token:
                    self._persist_result(db, current, result.content, metadata)
                elif current and current.status == "cancelled":
                    pixels_path.unlink(missing_ok=True)
                    manifest_path.unlink(missing_ok=True)
            self.received_results.pop(job_id, None)
        except asyncio.CancelledError:
            raise  # A submitted job stays recoverable; cancellation never refunds it.
        except Exception as exc:
            with self.sessions() as db:
                current = db.get(PostImageGenerationJob, job_id)
                if current and current.lease_token == token:
                    if result is not None or manifest_path.is_file():
                        current.status = "result_pending"
                        current.lease_until = self.clock()
                        current.failure_class = "local_result_persistence_pending"
                        db.commit()
                    else:
                        current.provider_receipt = received_receipt or current.provider_receipt
                        code = str(exc) if isinstance(exc, (ImagePreparationError, ImageSubmissionError)) else "generation_submission_failed"
                        self._fail(db, current, code, unknown=getattr(exc, "outcome_unknown", False) or (received_receipt is not None and not isinstance(exc, ImageSubmissionError)),
                            release=isinstance(exc, ImagePreparationError) and received_receipt is None)

    def _persist_result(self, db, job, content, metadata):
        try:
            self.execution.prepare(db, job, db.get(ImageIntent, job.intent_id))
        except (ImagePreparationError, InvalidProfileMediaError) as exc:
            self._fail(db, job, str(exc))
            for path in self._spool_paths(job.id):
                path.unlink(missing_ok=True)
            return
        if not job.result_asset_id:
            try:
                asset = self.assets.upload(db, owner_id=job.user_id, scope_kind="world",
                    scope_id=db.get(Post, job.post_id).world_id, content_type=metadata["content_type"], content=content, draft=False)
            except InvalidProfileMediaError:
                self._fail(db, job, "generation_result_pixels_invalid")
                for path in self._spool_paths(job.id):
                    path.unlink(missing_ok=True)
                return
            job.result_asset_id = asset.id
        job.provider_receipt = metadata.get("receipt") or job.provider_receipt
        job.status, job.lease_token, job.lease_until = "result_ready", None, None
        for attempt in db.scalars(select(ImageGenerationAttempt).where(ImageGenerationAttempt.job_id == job.id,
            ImageGenerationAttempt.status.in_(("submitted", "outcome_unknown", "result_received")))):
            attempt.status, attempt.usage_json = "succeeded", json.dumps(metadata.get("usage"))
        db.commit()
        for path in self._spool_paths(job.id):
            path.unlink(missing_ok=True)
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
        db.commit()
