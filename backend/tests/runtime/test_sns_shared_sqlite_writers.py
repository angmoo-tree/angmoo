"""Two Worlds, independent connections, four actual canonical writer owners."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from threading import Barrier

from sqlalchemy import select

from image_integration.test_generation_lifecycle import configured, admit, CHARACTER
from memory.test_p8_l_o_memory_consolidation import _stack
from memory.test_activity_situation_application import real_source, receipt
from memory.test_activity_situation_contract import NOW
from app.core.sqlite_concurrency import run_sqlite_session_immediate
from app.domains.world_characters.models import WorldCharacter
from app.domains.world_characters.activity_models import CharacterActivityState
from app.domains.world_characters.service.activity_state import settle_state
from app.domains.social.models.posts import PostImageGenerationJob, PostMedia
from app.domains.memory.models.activity_situation import MemorySituationReceipt
from app.domains.memory.repository.situation_runs import get_or_create_settings, request_run, claim_run
from app.domains.memory.repository.situation_apply import prepare_page, apply_page
from app.runtime.memory.composition import memory_repository
from app.runtime.memory.situation_sources import SituationSources
from app.runtime.persistence.sqlite_scheduler_lease import SqliteSchedulerLeaseRepository


def test_memory_image_sns_settlement_and_heartbeat_progress_without_cross_world_effects(tmp_path, monkeypatch):
    sessions, media, provider = configured(tmp_path)
    job_id = admit(sessions, media)
    engine = sessions.kw["bind"]
    with sessions() as db:
        actor = db.scalar(select(WorldCharacter).where(WorldCharacter.character_id == CHARACTER))
        actor_id, image_world = actor.id, actor.world_id
        scope, setting, _, _, *_ = _stack(db)
        post = real_source(db, scope)
        captured = receipt(db, scope, post)
        get_or_create_settings(db, setting.id, timezone="Asia/Seoul", now=NOW)
        request = request_run(db, setting, trigger="manual", request_key="shared-writer-page", expected_version=1, now=NOW)
        token = claim_run(db, request.run_id, now=NOW)
        db.commit()
        run_id, sequence = request.run_id, captured.sequence
        assert scope.world_id != image_world
    with sessions() as db:
        prepared = prepare_page(db, run_id=run_id, token=token, now=NOW)
    lease = SqliteSchedulerLeaseRepository(engine)
    proof = lease.acquire(owner_id="shared-writer-owner", ttl_seconds=45)
    barrier = Barrier(4)
    receive = media.worker._receive_result
    def concurrent_receive(*args):
        barrier.wait(timeout=10)
        return receive(*args)
    monkeypatch.setattr(media.worker, "_receive_result", concurrent_receive)
    def image():
        asyncio.run(media.worker.process(job_id))
    def memory():
        barrier.wait(timeout=10)
        with sessions() as db:
            return run_sqlite_session_immediate(db, lambda: apply_page(db, memory_repository(db), SituationSources(db),
                run_id=run_id, token=token, now=NOW, page_size=16, prepared=prepared), require_clean=True)
    def sns():
        barrier.wait(timeout=10)
        with sessions() as db:
            return run_sqlite_session_immediate(db, lambda: settle_state(db, world_id=image_world, actor_id=actor_id,
                activity_id="shared-sns-activity", decision_key="shared-sns-decision", expected_version=0,
                proposal=None, judged_at=datetime.now(UTC), source_keys=[], valid_source_keys=set(), context_reassessment=True), require_clean=True)
    def heartbeat():
        barrier.wait(timeout=10)
        return lease.heartbeat(owner_id="shared-writer-owner", fencing_epoch=proof.fencing_epoch, ttl_seconds=45)
    with ThreadPoolExecutor(max_workers=4) as workers:
        futures = [workers.submit(operation) for operation in (image, memory, sns, heartbeat)]
        results = [future.result(timeout=15) for future in futures]
    assert results[1] == 1
    assert results[3].fencing_epoch == proof.fencing_epoch
    assert provider.calls == 1
    with sessions() as db:
        assert db.get(PostImageGenerationJob, job_id).status == "succeeded"
        assert db.scalar(select(PostMedia)) is not None
        assert db.get(MemorySituationReceipt, sequence).state == "applied"
        state = db.get(CharacterActivityState, actor_id)
        assert state is None or state.world_id == image_world
        assert db.get(MemorySituationReceipt, sequence).scope_setting_id == prepared.admissions[0][1].receipt.scope_setting_id
