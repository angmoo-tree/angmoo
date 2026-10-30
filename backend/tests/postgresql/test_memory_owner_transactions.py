"""Owner memory mutations replay only a rolled-back DB unit, including guards."""
from dataclasses import replace

import pytest
from sqlalchemy import event, func, select, text
from sqlalchemy.orm import Session

from postgresql.test_activity_transactions import store
from memory.test_p8_l_q_memory_read_inspector import _seed
from app.domains.memory.exceptions import MemoryConflictError
from app.domains.memory.models.items import MemoryItem, MemoryScopeSettingModel
from app.domains.memory.schemas import MemoryCorrectionCreate, MemoryDeleteCreate, MemoryPinUpdate
from app.domains.memory.service import management
from app.domains.chat.models import MessageMessage
from app.runtime.memory_http import build_memory_workflows


def seed(engine):
    result = _seed(engine, {})
    with Session(engine) as db:
        setting = db.scalar(select(MemoryScopeSettingModel))
        setting.enabled = True
        setting.version += 1
        db.commit()
        result['scope_version'] = setting.version
    return result


def request(action, seeded):
    if action == 'correct':
        return management.correct_memory_item, MemoryCorrectionCreate(
            schema_version='memory-correction-create.v1', expected_item_version=1,
            expected_scope_version=seeded['scope_version'], summary='A corrected memory.',
            idempotency_key='owner-correction-pg-001')
    if action == 'pin':
        return management.update_memory_pin, MemoryPinUpdate(
            schema_version='memory-pin-update.v1', expected_version=1,
            pinned=True, idempotency_key='owner-pin-pg-001')
    return management.delete_memory_item, MemoryDeleteCreate(
        schema_version='memory-delete.v1', expected_version=1,
        idempotency_key='owner-delete-pg-001')


@pytest.mark.parametrize('action', ['correct', 'pin', 'delete'])
@pytest.mark.parametrize('code', ['40001', '40P01'])
def test_late_abort_replays_whole_mutation_without_duplicate_or_version_drift(store, action, code):
    engine, _, _ = store
    seeded = seed(engine)
    original = build_memory_workflows()
    seen = []

    def abort_once(db, scope):
        # This read happens after mutation and before publication of its DTO.
        seen.append(db.get(MemoryItem, seeded['memory_id']).version)
        if len(seen) == 1:
            db.connection().exec_driver_sql(
                f"DO $$ BEGIN RAISE EXCEPTION 'synthetic owner abort' USING ERRCODE='{code}'; END $$")
        return original.character_names(db, scope)

    workflows = replace(original, character_names=abort_once)
    operation, data = request(action, seeded)
    with Session(engine) as db:
        result = operation(db=db, workflows=workflows, scope=seeded['scope'],
            memory_id=seeded['memory_id'], data=data)
        assert seen == [2, 2]
        assert not db.in_transaction()
        replay = operation(db=db, workflows=original, scope=seeded['scope'],
            memory_id=seeded['memory_id'], data=data)
        assert replay.outcome == 'reused'
        assert replay.item.id == result.item.id
        assert db.scalar(select(func.count()).select_from(MemoryItem)) == (2 if action == 'correct' else 1)
        assert db.get(MemoryItem, seeded['memory_id']).version == 2
    assert engine.pool.checkedout() == 0


@pytest.mark.parametrize('change', ['source_edit', 'memory_version'])
def test_correction_retry_preserves_experience_but_rechecks_current_memory(store,change):
    engine, _, _ = store
    seeded = seed(engine)
    original = build_memory_workflows()
    seen = []

    def abort_once(db, scope):
        seen.append(1)
        if len(seen)==1:
            db.connection().exec_driver_sql(
                "DO $$ BEGIN RAISE EXCEPTION 'synthetic source conflict' USING ERRCODE='40001'; END $$")
        return original.character_names(db,scope)

    operation, data = request('correct', seeded)
    with Session(engine) as db:
        changed = []
        def change_after_rollback(session, transaction):
            # Inject a distinct committed edit after the failed mutation rolls back.
            if not seen or changed:
                return
            changed.append(True)
            with Session(engine) as writer:
                writer.execute(text("SET LOCAL lock_timeout='1s'"))
                if change=='source_edit':
                    source = writer.get(MessageMessage, seeded['source_message_id'])
                    source.content = 'Canonical source changed between attempts.'
                else:
                    writer.get(MemoryItem,seeded['memory_id']).version+=1
                writer.commit()
        event.listen(db, 'after_soft_rollback', change_after_rollback)
        def execute():
            return operation(db=db,workflows=replace(original,character_names=abort_once),
                scope=seeded['scope'],memory_id=seeded['memory_id'],data=data)
        try:
            if change=='source_edit':
                result=execute()
                assert result.outcome=='updated' and result.item.id!=seeded['memory_id']
                assert seen==[1,1]
            else:
                with pytest.raises(MemoryConflictError,match='memory_item_version_conflict'):execute()
                assert seen==[1]
        finally:event.remove(db,'after_soft_rollback',change_after_rollback)
        assert db.scalar(select(func.count()).select_from(MemoryItem)) == (2 if change=='source_edit' else 1)
        assert db.get(MemoryItem,seeded['memory_id']).version==2
    assert engine.pool.checkedout() == 0
