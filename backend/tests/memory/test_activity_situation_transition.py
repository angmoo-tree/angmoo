import pytest
from sqlalchemy import select, func
from app.domains.memory.models.items import MemoryCandidate, MemoryMaintenanceJob, MemoryItem
from app.domains.memory.models.batch import MemorySourceDelivery
from app.domains.memory.models.activity_situation import MemorySituationTransition
from app.domains.memory.repository.situation_transition import inspect_discard
from app.domains.memory.exceptions import MemoryConflictError
from app.domains.social.models.posts import Post
from app.runtime.memory.situation_retirement import discard
from memory.test_activity32_integration import prepare, response_session


def test_exact_legacy_discard_rolls_back_and_then_fences_resume_without_sources_or_keys_loss(response_session):
    db = response_session
    repo, batch, now, _ = prepare(db, posts=3)
    before = [(p.id, p.body) for p in db.scalars(select(Post).order_by(Post.id))]
    plan = inspect_discard(db, batch.setting.id)
    assert plan.job_ids == (batch.job_id,)
    assert len(plan.candidate_ids) == 4
    discard(db, plan, request_key="legacy-transition-001", now=now)
    db.rollback()
    assert db.get(MemoryMaintenanceJob, batch.job_id) is not None
    assert db.get(MemorySituationTransition, batch.setting.id) is None
    discard(db, plan, request_key="legacy-transition-001", now=now)
    db.commit()
    assert db.get(MemoryMaintenanceJob, batch.job_id) is None
    assert db.scalar(select(func.count()).select_from(MemoryCandidate)) == 0
    assert all(row.state == "invalidated" for row in db.scalars(select(MemorySourceDelivery)))
    assert [(p.id, p.body) for p in db.scalars(select(Post).order_by(Post.id))] == before
    assert db.scalar(select(func.count()).select_from(MemoryItem)) == 0
    assert discard(db, plan, request_key="legacy-transition-001", now=now).discard_key == "legacy-transition-001"
    db.commit()
    assert repo.claim(lease_token="cannot-resume", now=now) is None
    db.rollback()
    assert repo.enqueue(scope_setting_id=batch.setting.id, candidate_ids=(), cutoff=plan.cutoff,
        trigger="shutdown", now=now, generation_policy="activity32") is None


def test_discard_inventory_change_does_not_partially_retire(response_session):
    from dataclasses import replace
    db = response_session
    _, batch, now, _ = prepare(db, posts=1)
    plan = inspect_discard(db, batch.setting.id)
    with pytest.raises(MemoryConflictError):
        discard(db, replace(plan, cutoff=plan.cutoff + 1), request_key="legacy-transition-002", now=now)
    db.rollback()
    assert db.get(MemoryMaintenanceJob, batch.job_id) is not None
    assert db.get(MemorySituationTransition, batch.setting.id) is None


def test_shared_canonical_bundle_pin_new_receipt_and_every_nonqueue_table_are_preserved(response_session, tmp_path):
    from pathlib import Path
    import importlib.util
    import sys
    import json
    from datetime import timedelta
    from app.domains.memory.models.episode import MemoryEpisodeBundle, MemoryEpisodeInfo
    from app.domains.memory.contracts.activity_batch import ACTIVITY_POLICY_VERSION
    from memory.test_activity_situation_contract import values
    from app.domains.memory.repository.situation_admission import admit
    db = response_session
    _, batch, now, _ = prepare(db, posts=3)
    from app.domains.memory.models.items import MemoryScopeSettingModel
    # A no-op locking UPDATE must also suppress the ORM's automatic timestamp.
    db.get(MemoryScopeSettingModel, batch.setting.id).updated_at = now - timedelta(days=7)
    db.add(MemoryEpisodeBundle(id="shared-canonical-bundle", scope_setting_id=batch.setting.id,
        policy_version=ACTIVITY_POLICY_VERSION, activation_epoch="fixture", cutoff_sequence=1,
        manifest_hash="0"*64, manifest_json=json.dumps({"job_id": batch.job_id, "state": "pending"}), result_hash="0"*64))
    db.add(MemoryItem(id="saved-pin", owner_id=batch.setting.scope.owner_id, world_id=batch.setting.scope.world_id,
        subject_world_character_id=batch.setting.scope.subject_world_character_id, summary="이미 저장된 경험",
        memory_kind="AUTOBIOGRAPHICAL_EVENT", status="active", confidence=1, salience=.5, version=1,
        pinned_at=now, valid_from=now, valid_until=now+timedelta(days=180)))
    db.flush()
    db.add(MemoryEpisodeInfo(memory_item_id="saved-pin", bundle_id="shared-canonical-bundle", policy_version=ACTIVITY_POLICY_VERSION))
    m, d, r = values(db, batch.setting.scope)
    admit(db, manifest=m, draft=d, result=r, now=now)
    db.commit()
    script = Path(__file__).resolve().parents[3]/"scripts/diagnostics/retire_activity32_tasks.py"
    spec = importlib.util.spec_from_file_location("retirement_diagnostic", script)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    import sqlite3
    root = tmp_path / "isolated-contributor"
    database = root / "canonical/generations/contributor-v1/angmoo.sqlite3"
    database.parent.mkdir(parents=True)
    (root / "secrets").mkdir()
    (root / "secrets/app-secret").write_text("synthetic-maintenance-key", encoding="utf-8")
    with sqlite3.connect(database) as destination:
        db.connection().connection.driver_connection.backup(destination)
    inventory = json.loads(json.dumps(module.inspect_root(root)))
    result = module.apply_inventory(root, inventory)
    assert result["remaining_target_work"] == 0 and result["providers_called"] == 0
    assert module.apply_inventory(root, inventory)["changed_tables"] == []
    before = module.fingerprint(db.connection())
    plan = inspect_discard(db, batch.setting.id)
    discard(db, plan, request_key="shared-bundle-discard", now=now)
    after = module.fingerprint(db.connection())
    assert {name for name in before if before[name] != after[name]} <= module.MUTABLE
    assert db.get(MemoryEpisodeBundle, "shared-canonical-bundle") is not None
    assert db.get(MemoryItem, "saved-pin").pinned_at is not None
    assert db.connection().exec_driver_sql("PRAGMA foreign_key_check").all() == []
    db.commit()
