"""Receive failures must not silently turn a paid result into another submit."""
import asyncio
from dataclasses import replace
import json
import os

import pytest

from sqlalchemy import select

from app.domains.social.models.image_intents import ImageGenerationAttempt
from app.domains.social.models.posts import PostImageGenerationJob
from image_integration.test_generation_lifecycle import admit, configured


def test_first_database_failure_and_failure_handler_failure_retain_result(tmp_path, monkeypatch):
    sessions, media, provider = configured(tmp_path)
    job_id = admit(sessions, media)
    worker = media.worker
    original_receive, original_failure = worker._receive_result, worker._failed_result
    def unavailable(*args):
        raise RuntimeError("test_database_unavailable")
    monkeypatch.setattr(worker, "_receive_result", unavailable)
    monkeypatch.setattr(worker, "_failed_result", unavailable)
    try:
        asyncio.run(worker.process(job_id))
    except RuntimeError:
        pass
    assert provider.calls == 1
    assert len(worker.received_results) == 1
    with sessions() as db:
        assert db.get(PostImageGenerationJob, job_id).status == "running"
        assert db.scalar(select(ImageGenerationAttempt.status).where(ImageGenerationAttempt.job_id == job_id)) == "submitted"
    monkeypatch.setattr(worker, "_receive_result", original_receive)
    monkeypatch.setattr(worker, "_failed_result", original_failure)
    asyncio.run(worker.process(job_id))
    assert provider.calls == 1
    with sessions() as db:
        assert db.get(PostImageGenerationJob, job_id).status == "succeeded"


@pytest.mark.parametrize("failure", ["fsync", "replace"])
def test_journal_write_failure_keeps_buffer_without_durable_marker(tmp_path, monkeypatch, failure):
    sessions, media, provider = configured(tmp_path)
    job_id = admit(sessions, media)
    from pathlib import Path
    target = os if failure == "fsync" else Path
    original = getattr(target, failure)
    def fail(*args):
        raise OSError("test_disk_unavailable")
    monkeypatch.setattr(target, failure, fail)
    asyncio.run(media.worker.process(job_id))
    assert len(media.worker.received_results) == 1
    with sessions() as db:
        assert db.get(PostImageGenerationJob, job_id).status == "running"
        assert db.scalar(select(ImageGenerationAttempt.status)) == "submitted"
    monkeypatch.setattr(target, failure, original)
    asyncio.run(media.worker.process(job_id))
    assert provider.calls == 1
    assert not media.worker.received_results


def test_full_buffer_defers_submit_without_discarding_results(tmp_path):
    sessions, media, provider = configured(tmp_path)
    job_id = admit(sessions, media)
    worker = media.worker
    from app.domains.social.service.image_intent_generation import ReceivedSlot
    with sessions() as db:
        binding = worker._binding(db, db.get(PostImageGenerationJob, job_id))
    held = {}
    for number in range(4):
        value = replace(binding, job_id=1000 + number, attempt_id=str(number))
        held[(value.job_id, value.attempt_id)] = ReceivedSlot(value, "other", result=object())
    worker.received_results.update(held)
    asyncio.run(worker.process(job_id))
    assert provider.calls == 0
    assert worker.received_results == held
    with sessions() as db:
        assert db.get(PostImageGenerationJob, job_id).status == "queued"


@pytest.mark.parametrize("phase", ["journal_rollback", "asset_ambiguous_commit"])
def test_commit_failure_recovers_without_recreating_committed_asset(tmp_path, monkeypatch, phase):
    from sqlalchemy.orm import Session
    from sqlalchemy import func
    from app.domains.media.models import MediaAsset
    from app.domains.social.models.posts import PostMedia
    sessions, media, provider = configured(tmp_path)
    job_id = admit(sessions, media)
    commit = Session.commit
    failed = False
    def fail(db):
        nonlocal failed
        job = next((value for value in db.identity_map.values() if isinstance(value, PostImageGenerationJob)), None)
        stage = "result_pending" if phase == "journal_rollback" else "result_ready"
        if not failed and job is not None and job.status == stage:
            failed = True
            if phase == "asset_ambiguous_commit":
                commit(db)
            raise RuntimeError("test_commit_failure")
        return commit(db)
    monkeypatch.setattr(Session, "commit", fail)
    asyncio.run(media.worker.process(job_id))
    asyncio.run(media.worker.process(job_id))
    assert failed and provider.calls == 1
    with sessions() as db:
        assert db.get(PostImageGenerationJob, job_id).status == "succeeded"
        assert db.scalar(select(func.count()).select_from(MediaAsset)) == 1
        assert db.scalar(select(func.count()).select_from(PostMedia)) == 1
        assert db.scalar(select(ImageGenerationAttempt.status)) == "succeeded"
    assert not media.worker.received_results


def test_corrupt_or_different_attempt_journal_cannot_be_reused_or_unlinked(tmp_path, monkeypatch):
    sessions, media, provider = configured(tmp_path)
    job_id = admit(sessions, media)
    monkeypatch.setattr(media.worker, "_persist_result", lambda *args: (_ for _ in ()).throw(RuntimeError("test_hold")))
    asyncio.run(media.worker.process(job_id))
    slot = media.worker._slot(job_id)
    _, manifest = media.worker._spool_paths(job_id)
    value = json.loads(manifest.read_text())
    value["binding"]["attempt_id"] = "different-attempt"
    manifest.write_text(json.dumps(value))
    with pytest.raises(ValueError, match="binding_invalid"):
        media.worker._read_received(job_id, slot.binding)
    media.worker._remove_journal(slot.binding)
    assert manifest.exists()
    assert provider.calls == 1


def _crash_after_durable_result(path, stage):
    from pathlib import Path
    sessions, media, _ = configured(Path(path))
    job_id = admit(sessions, media)
    def crash(*args):
        os._exit(47)
    if stage == "journal":
        media.worker._persist_result = crash
    elif stage == "asset":
        media.worker._attach = crash
    else:
        attach = media.worker._attach
        def attached(*args):
            attach(*args)
            os._exit(47)
        media.worker._attach = attached
    asyncio.run(media.worker.process(job_id))


@pytest.mark.parametrize("stage", ["journal", "asset", "attachment"])
def test_actual_child_exit_recovers_durable_bytes_without_new_submit(tmp_path, stage):
    import subprocess
    import sys
    from datetime import UTC, datetime, timedelta
    from pathlib import Path
    from types import SimpleNamespace
    from sqlalchemy import create_engine, func
    from sqlalchemy.orm import sessionmaker
    from app.runtime.media.composition import MediaRuntime
    from app.domains.social.models.posts import PostMedia
    from image_integration.test_generation_lifecycle import Provider
    environment = {**os.environ, "PYTHONPATH": str(Path(__file__).parents[1]) + os.pathsep + str(Path.cwd())}
    child = subprocess.run([sys.executable, "-c",
        "from image_integration.test_received_result_recovery import _crash_after_durable_result; import sys; _crash_after_durable_result(sys.argv[1],sys.argv[2])",
        str(tmp_path), stage], env=environment, capture_output=True, timeout=60)
    assert child.returncode == 47, child.stderr.decode(errors="replace")[-1000:]
    engine = create_engine(f"sqlite:///{tmp_path / 'social-write.sqlite3'}")
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    provider = Provider("nanogpt", "krea-v2/turbo")
    media = MediaRuntime(sessions, SimpleNamespace(media_root_path=tmp_path / "media"), clients={"nanogpt": provider})
    media.worker.clock = lambda: datetime.now(UTC) + timedelta(minutes=10)
    with sessions() as db:
        job_id = db.scalar(select(PostImageGenerationJob.id))
        assert db.get(PostImageGenerationJob, job_id).status == ("result_pending" if stage == "journal" else "result_ready" if stage == "asset" else "succeeded")
    asyncio.run(media.worker.process(job_id))
    asyncio.run(media.worker.process(job_id))
    with sessions() as db:
        assert db.get(PostImageGenerationJob, job_id).status == "succeeded"
        assert db.scalar(select(func.count()).select_from(PostMedia)) == 1
        assert db.scalar(select(func.count()).select_from(ImageGenerationAttempt)) == 1
    assert provider.calls == 0
    engine.dispose()


def test_cancelled_waiter_keeps_owned_writer_and_result_idempotent(tmp_path, monkeypatch):
    from threading import Event
    sessions, media, provider = configured(tmp_path)
    job_id = admit(sessions, media)
    entered, release = Event(), Event()
    persist = media.worker._persist_result
    def held(*args):
        entered.set()
        assert release.wait(10)
        return persist(*args)
    monkeypatch.setattr(media.worker, "_persist_result", held)
    media.worker._local_work = media._canonical_work.call
    async def run():
        task = asyncio.create_task(media.worker.process(job_id))
        while not entered.is_set():
            await asyncio.sleep(.01)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert media.worker._slot(job_id).result is not None
        release.set()
        await media._canonical_work.drain()
        await media.worker.process(job_id)
        media._canonical_work.close()
    asyncio.run(run())
    assert provider.calls == 1
    with sessions() as db:
        assert db.get(PostImageGenerationJob, job_id).status == "succeeded"


def test_cancelled_prepare_future_reconciles_never_submitted_reservation(tmp_path, monkeypatch):
    from threading import Event
    sessions, media, provider = configured(tmp_path)
    job_id = admit(sessions, media)
    entered, release = Event(), Event()
    prepare = media.worker._prepare_job
    def held(*args):
        result = prepare(*args)
        entered.set()
        assert release.wait(10)
        return result
    monkeypatch.setattr(media.worker, "_prepare_job", held)
    media.worker._local_work = media._canonical_work.call
    async def run():
        task = asyncio.create_task(media.worker.process(job_id))
        while not entered.is_set():
            await asyncio.sleep(.01)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        release.set()
        await media._canonical_work.drain()
        assert provider.calls == 0
        await media.worker.tick()
        media._canonical_work.close()
    asyncio.run(run())
    assert provider.calls == 1
    with sessions() as db:
        assert db.get(PostImageGenerationJob, job_id).status == "succeeded"
