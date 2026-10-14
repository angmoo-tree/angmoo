"""Two-phase pages retain fresh fences and atomic prefix application."""
from datetime import timedelta
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session
import pytest

from memory.test_p8_l_o_memory_consolidation import _stack
from memory.test_activity_situation_application import real_source, receipt
from memory.test_activity_situation_contract import NOW
from app.runtime.persistence.model_registration import register_models
from app.runtime.memory.situation_sources import SituationSources
from app.domains.memory.repository.situation_runs import get_or_create_settings, request_run, claim_run
from app.domains.memory.repository.situation_apply import prepare_page, apply_page, SituationPageStale
from app.domains.memory.models.activity_situation import MemorySituationReceipt, MemorySituationApplyRun, MemorySituationManifest
from app.domains.memory.models.items import MemoryItem


def setup(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'situation.sqlite'}")
    @event.listens_for(engine, "connect")
    def configure(raw, _):
        raw.execute("PRAGMA foreign_keys=ON")
        raw.execute("PRAGMA journal_mode=WAL")
    register_models().create_all(engine)
    with Session(engine, expire_on_commit=False) as db:
        scope, setting, _, _, *_ = _stack(db)
        post = real_source(db, scope)
        row = receipt(db, scope, post)
        get_or_create_settings(db, setting.id, timezone="Asia/Seoul", now=NOW)
        request = request_run(db, setting, trigger="manual", request_key="prepared-page-001", expected_version=1, now=NOW)
        token = claim_run(db, request.run_id, now=NOW)
        db.commit()
        return engine, request.run_id, token, row.sequence, row.manifest_id


@pytest.mark.parametrize("mutation", ["receipt", "manifest", "cursor"])
def test_prepared_material_change_rolls_back_cursor_and_memory(tmp_path, mutation):
    engine, run_id, token, sequence, manifest_id = setup(tmp_path)
    with Session(engine) as db:
        page = prepare_page(db, run_id=run_id, token=token, now=NOW)
    with Session(engine) as db:
        if mutation == "receipt":
            db.get(MemorySituationReceipt, sequence).state_version += 1
        elif mutation == "manifest":
            db.get(MemorySituationManifest, manifest_id).payload = {"changed": True}
        else:
            db.get(MemorySituationApplyRun, run_id).cursor = sequence
        db.commit()
    with Session(engine) as db:
        from app.runtime.memory.composition import memory_repository
        with pytest.raises(SituationPageStale):
            apply_page(db, memory_repository(db), SituationSources(db), run_id=run_id, token=token, now=NOW, page_size=16, prepared=page)
        db.rollback()
        assert db.scalar(select(MemoryItem.id)) is None
        assert db.get(MemorySituationReceipt, sequence).state == "pending"
    engine.dispose()


def test_prepare_hash_work_does_not_hold_writer_and_apply_skips_reparsing(tmp_path, monkeypatch):
    engine, run_id, token, sequence, _ = setup(tmp_path)
    from app.domains.memory.repository import situation_validation
    original = situation_validation.stable_digest
    reads = []
    def digest(value):
        # A second, independent connection can acquire the real SQLite writer
        # while immutable preparation is parsing/hashing receipt data.
        with engine.connect() as writer:
            writer.exec_driver_sql("BEGIN IMMEDIATE")
            writer.rollback()
        reads.append(1)
        return original(value)
    monkeypatch.setattr(situation_validation, "stable_digest", digest)
    with Session(engine) as db:
        page = prepare_page(db, run_id=run_id, token=token, now=NOW)
    assert reads
    monkeypatch.setattr(situation_validation, "restore_admission", lambda *_args, **_kwargs: pytest.fail("parsed under writer"))
    with Session(engine) as db:
        from app.runtime.memory.composition import memory_repository
        assert apply_page(db, memory_repository(db), SituationSources(db), run_id=run_id, token=token, now=NOW, page_size=16, prepared=page) == 1
        db.commit()
        assert db.get(MemorySituationReceipt, sequence).state == "applied"
        assert db.get(MemorySituationApplyRun, run_id).cursor == sequence
    engine.dispose()
