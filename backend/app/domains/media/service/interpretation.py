"""Shared, scope-bound analysis jobs. Uploads and preflight perform no AI calls."""
import asyncio
import hashlib
import json
import os
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from sqlalchemy import select, update, func
from app.domains.media.models import InterpretationSetting, ImageInterpretation, InterpretationAttempt
from app.domains.media.interpretation_contracts import parse_analysis
from app.domains.media.generation_contracts import ImagePreparationError
from app.domains.identity.contracts import CredentialPurpose
from app.domains.identity.service import media_credentials
from app.domains.identity.exceptions import CredentialResolutionError
from app.domains.media.contracts import InvalidProfileMediaError


def cache_key(asset, model, thinking_level):
    values = (asset.owner_id, asset.scope_kind, asset.scope_id, asset.id, str(asset.revision), asset.content_hash, model, thinking_level, "image-analysis-v1")
    return hashlib.sha256("|".join(values).encode()).hexdigest()


def read_interpretation_settings(db, owner_id):
    row = db.get(InterpretationSetting, owner_id)
    credential = media_credentials.find_credential(db, owner_id=owner_id, character_id="", provider="gemini", purpose=CredentialPurpose.IMAGE_INTERPRETATION)
    return {"enabled": bool(row and row.enabled), "revision": row.revision if row else 0,
        "model": row.model if row else "gemini-3.1-flash-lite", "thinking_level": row.thinking_level if row else "medium",
        "daily_limit": row.daily_limit if row else None, "has_api_key": bool(credential and credential.enabled)}


def write_interpretation_settings(db, owner_id, data):
    row = db.get(InterpretationSetting, owner_id)
    if data.expected_revision != (row.revision if row else 0):
        raise ImagePreparationError("settings_revision_conflict")
    if data.api_key is not None or data.clear_api_key:
        media_credentials.save_credential(db, owner_id=owner_id, character_id="", provider="gemini",
            purpose=CredentialPurpose.IMAGE_INTERPRETATION, secret=data.api_key.get_secret_value() if data.api_key else None)
    credential = media_credentials.find_credential(db, owner_id=owner_id, character_id="", provider="gemini", purpose=CredentialPurpose.IMAGE_INTERPRETATION)
    if data.enabled and (not data.daily_limit or not credential or not credential.enabled):
        raise ImagePreparationError("interpretation_limit_and_key_required")
    if row is None:
        row = InterpretationSetting(owner_id=owner_id, revision=1)
        db.add(row)
    else:
        previous = row.revision
        changed = db.execute(update(InterpretationSetting).where(InterpretationSetting.owner_id == owner_id,
            InterpretationSetting.revision == previous).values(revision=previous + 1))
        if changed.rowcount != 1:
            raise ImagePreparationError("settings_revision_conflict")
        db.refresh(row)
    row.enabled, row.model, row.thinking_level, row.daily_limit = data.enabled, data.model, data.thinking_level, data.daily_limit
    db.flush()
    return read_interpretation_settings(db, owner_id)


class InterpretationService:
    def __init__(self, session_factory, assets, interpreter, *, quota_day, clock=lambda: datetime.now(timezone.utc)):
        self.sessions, self.assets, self.interpreter = session_factory, assets, interpreter
        self.quota_day, self.clock = quota_day, clock
        self.tasks = set()
        self.spool = assets.root / "received-interpretations"

    def _result_path(self, identity):
        if len(identity) != 32 or any(c not in "0123456789abcdef" for c in identity):
            raise ImagePreparationError("interpretation_identity_invalid")
        return self.spool / f"{identity}.json"

    def _persist_received(self, db, row, value):
        identity = row.id
        claim = db.execute(update(ImageInterpretation).where(ImageInterpretation.id == identity,
            ImageInterpretation.status == "running", ImageInterpretation.lease_token == value["lease_token"])
            .values(error_code=ImageInterpretation.error_code))
        db.refresh(row)
        if claim.rowcount != 1:
            if row.status == "succeeded":
                return
            raise ImagePreparationError("interpretation_stale_result")
        self._validate_current(db, row)
        result = parse_analysis(value["analysis"])
        row.description, row.recall_hint = result.description, result.recall_hint
        row.result_json, row.status, row.error_code = result.model_dump_json(), "succeeded", None
        attempt = db.scalar(select(InterpretationAttempt).where(InterpretationAttempt.id == value["attempt_id"],
            InterpretationAttempt.interpretation_id == row.id))
        if attempt is None or row.lease_token != value["lease_token"]:
            raise ImagePreparationError("interpretation_stale_result")
        attempt.usage_json, attempt.status = json.dumps(value["usage"]), "succeeded"
        row.lease_token, row.lease_until = None, None
        db.commit()
        self._result_path(row.id).unlink(missing_ok=True)

    def _validate_current(self, db, row):
        setting = db.get(InterpretationSetting, row.owner_id, populate_existing=True)
        if not setting or not setting.enabled or (setting.model, setting.thinking_level) != (row.model, row.thinking_level):
            raise ImagePreparationError("interpretation_settings_changed")
        credential = media_credentials.find_credential(db, owner_id=row.owner_id, character_id="", provider="gemini",
            purpose=CredentialPurpose.IMAGE_INTERPRETATION)
        try:
            material = media_credentials.resolve_credential(credential, owner_id=row.owner_id, character_id="", provider="gemini",
                purpose=CredentialPurpose.IMAGE_INTERPRETATION, revision=row.credential_revision)
            asset, content = self.assets.read(db, owner_id=row.owner_id, asset_id=row.asset_id)
        except (CredentialResolutionError, InvalidProfileMediaError) as exc:
            raise ImagePreparationError("interpretation_source_or_key_changed") from exc
        if asset.revision != row.asset_revision:
            raise ImagePreparationError("interpretation_asset_changed")
        return material, asset, content

    def cached(self, db, owner_id, asset_id):
        asset, _ = self.assets.read(db, owner_id=owner_id, asset_id=asset_id)
        setting = db.get(InterpretationSetting, owner_id)
        key = cache_key(asset, setting.model if setting else "gemini-3.1-flash-lite", setting.thinking_level if setting else "medium")
        row = db.scalar(select(ImageInterpretation).where(ImageInterpretation.cache_key == key, ImageInterpretation.status == "succeeded"))
        return row if row is not None and row.description else None

    def preflight(self, db, owner_id, asset_id):
        if row := self.cached(db, owner_id, asset_id):
            return {"allowed": True, "reason": "cached", "interpretation_id": row.id}
        setting = db.get(InterpretationSetting, owner_id)
        credential = media_credentials.find_credential(db, owner_id=owner_id, character_id="", provider="gemini", purpose=CredentialPurpose.IMAGE_INTERPRETATION)
        shared = None
        if setting and setting.enabled:
            asset = self.assets.owned(db, owner_id=owner_id, asset_id=asset_id)
            shared = db.scalar(select(ImageInterpretation).where(
                ImageInterpretation.cache_key == cache_key(asset, setting.model, setting.thinking_level),
                ImageInterpretation.status.in_(("queued", "running", "outcome_unknown"))))
            if shared is not None and self._result_path(shared.id).is_file():
                return {"allowed": True, "reason": "received_result", "interpretation_id": shared.id}
            if shared is not None and shared.lease_until is not None and shared.lease_until.replace(tzinfo=timezone.utc) > self.clock():
                return {"allowed": True, "reason": "joined", "interpretation_id": shared.id}
        reason = None
        if not setting or not setting.enabled:
            reason = "interpretation_disabled"
        elif not setting.daily_limit:
            reason = "interpretation_limit_required"
        elif not credential or not credential.enabled:
            reason = "interpretation_key_required"
        elif shared is not None and (shared.status == "outcome_unknown" or shared.lease_until is None or shared.lease_until.replace(tzinfo=timezone.utc) <= self.clock()):
            reason = "interpretation_outcome_unknown"
        elif db.scalar(select(func.count()).select_from(InterpretationAttempt).where(
            InterpretationAttempt.owner_id == owner_id, InterpretationAttempt.quota_day == self.quota_day(self.clock()),
            InterpretationAttempt.status != "released")) >= setting.daily_limit:
            reason = "interpretation_daily_limit_reached"
        return {"allowed": reason is None, "reason": reason, "settings_path": "/settings"}

    def admit(self, db, owner_id, asset_id, *, retry_failed=False):
        """Reserve/share a job inside the caller's transaction; never call AI."""
        if cached := self.cached(db, owner_id, asset_id):
            return cached
        # Lock one owner setting before cache/job/quota reads; all callers use this path.
        if db.execute(update(InterpretationSetting).where(InterpretationSetting.owner_id == owner_id)
            .values(revision=InterpretationSetting.revision)).rowcount != 1:
            raise ImagePreparationError("interpretation_disabled")
        if cached := self.cached(db, owner_id, asset_id):
            return cached
        state = self.preflight(db, owner_id, asset_id)
        if not state["allowed"]:
            raise ImagePreparationError(state["reason"])
        asset = self.assets.owned(db, owner_id=owner_id, asset_id=asset_id)
        setting = db.get(InterpretationSetting, owner_id, populate_existing=True)
        key = cache_key(asset, setting.model, setting.thinking_level)
        row = db.scalar(select(ImageInterpretation).where(ImageInterpretation.cache_key == key))
        if row is None or (row.status == "failed" and retry_failed):
            state = self.preflight(db, owner_id, asset_id)
            if not state["allowed"]:
                raise ImagePreparationError(state["reason"])
            credential = media_credentials.find_credential(db, owner_id=owner_id, character_id="", provider="gemini", purpose=CredentialPurpose.IMAGE_INTERPRETATION)
            if row is None:
                row = ImageInterpretation(id=uuid4().hex, cache_key=key, asset_id=asset.id, owner_id=owner_id,
                scope_key=f"{asset.scope_kind}:{asset.scope_id}", asset_revision=asset.revision,
                model=setting.model, thinking_level=setting.thinking_level, credential_revision=credential.revision,
                status="queued", lease_token=None, lease_until=self.clock()+timedelta(minutes=5))
                db.add(row)
            else:
                row.status, row.error_code = "queued", None
                row.credential_revision = credential.revision
                row.lease_token, row.lease_until = None, self.clock()+timedelta(minutes=5)
            db.flush()
            db.add(InterpretationAttempt(id=uuid4().hex, interpretation_id=row.id, owner_id=owner_id,
                quota_day=self.quota_day(self.clock()), status="reserved"))
            db.flush()
        elif row.status == "failed":
            raise ImagePreparationError(row.error_code or "interpretation_failed")
        return row

    async def interpret(self, db, owner_id, asset_id, *, retry_failed=False, admitted_id=None):
        if admitted_id is None:
            row = self.admit(db, owner_id, asset_id, retry_failed=retry_failed)
        else:
            row = db.get(ImageInterpretation, admitted_id)
            asset = self.assets.owned(db, owner_id=owner_id, asset_id=asset_id)
            setting = db.get(InterpretationSetting, owner_id, populate_existing=True)
            model = setting.model if setting else "gemini-3.1-flash-lite"
            thinking = setting.thinking_level if setting else "medium"
            if row is None or row.owner_id != owner_id or row.asset_id != asset_id or row.cache_key != cache_key(asset, model, thinking):
                raise ImagePreparationError("interpretation_admission_changed")
            if row.status == "failed":
                raise ImagePreparationError(row.error_code or "interpretation_failed")
        if row.status == "succeeded":
            return row
        if self._result_path(row.id).is_file():
            self._persist_received(db, row, json.loads(self._result_path(row.id).read_text("utf-8")))
            return row
        identity, queued = row.id, row.status == "queued"
        db.commit()
        if queued:
            task = asyncio.create_task(self._execute(identity))
            self.tasks.add(task)
            task.add_done_callback(self.tasks.discard)
            await asyncio.shield(task)
        # Another process can own the same durable job. Consumer cancellation is local.
        for _ in range(1800):
            db.expire_all()
            row = db.get(ImageInterpretation, identity)
            if row.status == "succeeded":
                self.assets.owned(db, owner_id=owner_id, asset_id=asset_id)
                return row
            if row.status == "running" and self._result_path(identity).is_file():
                self._persist_received(db, row, json.loads(self._result_path(identity).read_text("utf-8")))
                return row
            if row.status not in {"queued", "running"}:
                raise ImagePreparationError(row.error_code or "interpretation_failed")
            if row.lease_until is None or row.lease_until.replace(tzinfo=timezone.utc) < self.clock():
                raise ImagePreparationError("interpretation_outcome_unknown")
            db.rollback()
            await asyncio.sleep(0.05)
        raise ImagePreparationError("interpretation_wait_timeout")

    async def _execute(self, identity):
        with self.sessions() as db:
            token = uuid4().hex
            claim = db.execute(update(ImageInterpretation).where(ImageInterpretation.id == identity,
                ImageInterpretation.status == "queued").values(status="running", lease_token=token,
                lease_until=self.clock()+timedelta(seconds=90)))
            if claim.rowcount != 1:
                db.rollback()
                return
            row = db.get(ImageInterpretation, identity)
            attempt = db.scalar(select(InterpretationAttempt).where(InterpretationAttempt.interpretation_id == identity,
                InterpretationAttempt.status == "reserved"))
            try:
                if attempt is None or attempt.quota_day != self.quota_day(self.clock()):
                    raise ImagePreparationError("interpretation_reservation_expired")
                material, asset, content = self._validate_current(db, row)
                model, thinking = row.model, row.thinking_level
                attempt_id = attempt.id
                attempt.status = "submitted"
                db.commit()
                result, usage = await self.interpreter.analyze(key=material.reveal(), model=model, thinking_level=thinking, content=content, content_type=asset.content_type)
                result = parse_analysis(result.model_dump())
                # The durable file contains observations, never credentials or image bytes.
                self.spool.mkdir(parents=True, exist_ok=True)
                received = {"analysis": result.model_dump(), "usage": usage, "attempt_id": attempt_id, "lease_token": token}
                target = self._result_path(identity)
                temporary = target.with_suffix(".tmp")
                with temporary.open("w", encoding="utf-8") as output:
                    json.dump(received, output, ensure_ascii=False)
                    output.flush()
                    os.fsync(output.fileno())
                temporary.replace(target)
                db.expire_all()
                row = db.get(ImageInterpretation, identity)
                if row.lease_token != token:
                    raise ImagePreparationError("interpretation_stale_result")
                self._persist_received(db, row, received)
                return
            except asyncio.CancelledError:
                db.rollback()
                row = db.get(ImageInterpretation, identity)
                row.status, row.error_code = "outcome_unknown", "interpretation_outcome_unknown"
                attempt = db.get(InterpretationAttempt, attempt_id)
                attempt.status = "outcome_unknown"
                row.lease_token, row.lease_until = None, None
                db.commit()
                raise
            except Exception as exc:
                db.rollback()
                row = db.get(ImageInterpretation, identity)
                attempt = db.get(InterpretationAttempt, attempt.id) if attempt else None
                if self._result_path(identity).is_file() and not isinstance(exc, ImagePreparationError):
                    # Local database failure: retain the lease and received result for recovery.
                    row.error_code = "interpretation_local_persistence_pending"
                    db.commit()
                    return
                submitted = attempt is not None and attempt.status == "submitted"
                unknown = isinstance(exc, (TimeoutError, ConnectionError)) or getattr(exc, "outcome_unknown", False) or getattr(exc, "failure_class", None) in {"timeout", "transport_failed", "provider_unavailable"}
                row.status = "outcome_unknown" if unknown else "failed"
                row.error_code = str(exc) if isinstance(exc, ImagePreparationError) else "interpretation_provider_failed"
                if attempt:
                    attempt.status = "outcome_unknown" if unknown else "failed" if submitted else "released"
                self._result_path(identity).unlink(missing_ok=True)
            row.lease_token, row.lease_until = None, None
            db.commit()

    async def close(self):
        if self.tasks:
            _, pending = await asyncio.wait(self.tasks, timeout=10)
            for task in pending:
                task.cancel()
            await asyncio.gather(*pending, return_exceptions=True)

    def recover_elapsed(self):
        with self.sessions() as db:
            rows = list(db.scalars(select(ImageInterpretation).where(ImageInterpretation.status.in_(("queued", "running")),
                ImageInterpretation.lease_until < self.clock())))
            for row in rows:
                target = self._result_path(row.id)
                if target.is_file():
                    try:
                        self._persist_received(db, row, json.loads(target.read_text("utf-8")))
                        continue
                    except ImagePreparationError:
                        db.rollback()
                        row = db.get(ImageInterpretation, row.id)
                        target.unlink(missing_ok=True)
                submitted = False
                for attempt in db.scalars(select(InterpretationAttempt).where(InterpretationAttempt.interpretation_id == row.id)):
                    if attempt.status == "reserved":
                        attempt.status = "released"
                    elif attempt.status == "submitted":
                        submitted = True
                        attempt.status = "outcome_unknown"
                row.status = "outcome_unknown" if submitted else "failed"
                row.error_code = "interpretation_outcome_unknown" if submitted else "interpretation_interrupted_before_submission"
                row.lease_token, row.lease_until = None, None
                db.commit()


def read_interpretation_usage(db, owner_id, quota_day):
    setting = db.get(InterpretationSetting, owner_id)
    count = db.scalar(select(func.count()).select_from(InterpretationAttempt).where(
        InterpretationAttempt.owner_id == owner_id, InterpretationAttempt.quota_day == quota_day,
        InterpretationAttempt.status != "released"))
    return {"interpretation_reserved_or_used": count,
        "interpretation_daily_limit": setting.daily_limit if setting else None}
