"""PostgreSQL memory admission protects policy without writing shared policy rows."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from threading import Barrier

import pytest
from sqlalchemy import event, func, select, text, update
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from postgresql.test_activity_transactions import store
from postgresql.test_situation_admission_reads import seed
from memory.test_activity_situation_contract import values, NOW
from app.core.database_transactions import database_write
from app.domains.memory.exceptions import MemoryConflictError
from app.domains.memory.models.items import MemoryScopeSettingModel
from app.domains.memory.models.activity_situation import MemorySituationManifest, MemorySituationReceipt
from app.domains.memory.repository.situation_admission import admit


def material(engine, scope, **kwargs):
    with Session(engine) as db:
        return values(db, scope, **kwargs)


def test_old_lock_only_update_conflicts_with_a_shared_policy_reader(store):
    engine, _, _ = store
    _, identifier = seed(engine)
    with Session(engine) as reader, Session(engine) as writer:
        reader.scalar(select(MemoryScopeSettingModel.id).where(
            MemoryScopeSettingModel.id == identifier).with_for_update(read=True))
        writer.execute(text("SET LOCAL lock_timeout='100ms'"))
        with pytest.raises(OperationalError) as error:
            writer.execute(update(MemoryScopeSettingModel).where(
                MemoryScopeSettingModel.id == identifier).values(
                    id=MemoryScopeSettingModel.id, updated_at=MemoryScopeSettingModel.updated_at)
                .execution_options(memory_scope_lock_only=True))
        assert error.value.orig.sqlstate == '55P03'
        writer.rollback()


def test_admission_shares_policy_guard_without_fake_policy_update(store):
    engine, _, _ = store
    scope, identifier = seed(engine)
    manifest, draft, result = material(engine, scope)
    statements=[]
    def record(_conn, _cursor, statement, *_):
        statements.append(statement)
    with Session(engine) as policy_reader:
        policy_reader.scalar(select(MemoryScopeSettingModel.id).where(
            MemoryScopeSettingModel.id==identifier).with_for_update(read=True))
        event.listen(engine,'before_cursor_execute',record)
        try:
            with Session(engine) as writer:
                writer.execute(text("SET LOCAL lock_timeout='100ms'"))
                row=admit(writer,manifest=manifest,draft=draft,result=result,now=NOW)
                assert row.state=='pending'
                writer.commit()
        finally:
            event.remove(engine,'before_cursor_execute',record)
    assert not any(s.lstrip().upper().startswith('UPDATE MEMORY_SCOPE_SETTINGS') for s in statements)
    assert engine.pool.checkedout()==0


@pytest.mark.parametrize('same_identity',[False,True])
def test_parallel_admissions_preserve_exact_receipt_identity(store,same_identity):
    engine, _, _ = store
    scope, _ = seed(engine)
    inputs=[material(engine,scope,target='p'+str(0 if same_identity else i),
                     logical='a'+str(0 if same_identity else i),call='c'+str(0 if same_identity else i))
            for i in range(2)]
    barrier=Barrier(2)
    def write(index):
        attempts=0
        with Session(engine) as db:
            def operation():
                nonlocal attempts
                attempts+=1
                if attempts==1:barrier.wait(timeout=5)
                manifest,draft,result=inputs[index]
                return admit(db,manifest=manifest,draft=draft,result=result,now=NOW).sequence
            return database_write(db,operation)
    with ThreadPoolExecutor(2) as pool:
        identifiers=list(pool.map(write,range(2)))
    expected=1 if same_identity else 2
    assert len(set(identifiers))==expected
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(MemorySituationReceipt))==expected
        assert db.scalar(select(func.count()).select_from(MemorySituationManifest))==expected
    assert engine.pool.checkedout()==0


def test_concurrent_changed_receipt_is_rejected_instead_of_overwritten(store):
    engine, _, _ = store
    scope, _ = seed(engine)
    manifest,draft,result=material(engine,scope)
    barrier=Barrier(2)
    def write(index):
        attempted=False
        with Session(engine) as db:
            def operation():
                nonlocal attempted
                if not attempted:
                    attempted=True
                    barrier.wait(timeout=5)
                return admit(db,manifest=manifest,draft=replace(draft,description='different '+str(index)),
                             result=result,now=NOW).sequence
            try:
                return ('stored',database_write(db,operation))
            except MemoryConflictError as exc:
                assert str(exc)=='situation_receipt_content_conflict'
                return ('conflict',None)
    with ThreadPoolExecutor(2) as pool:
        outcomes=list(pool.map(write,range(2)))
    assert sorted(state for state,_ in outcomes)==['conflict','stored']
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(MemorySituationReceipt))==1
    assert engine.pool.checkedout()==0


def test_one_manifest_can_admit_two_targets_concurrently(store):
    engine, _, _ = store
    scope, _ = seed(engine)
    manifest, draft, result = material(engine, scope)
    manifest = replace(manifest, sources=(*manifest.sources,
        replace(manifest.sources[0], source_id='p0', target_key='p0', ordinal=1)))
    barrier = Barrier(2)
    def write(index):
        attempted = False
        target = 'p' + str(index)
        with Session(engine) as db:
            def operation():
                nonlocal attempted
                if not attempted:
                    attempted = True
                    barrier.wait(timeout=5)
                return admit(db, manifest=manifest, draft=replace(draft, target_key=target),
                    result=replace(result, target_key=target,
                        effects=(replace(result.effects[0], source_id='reaction-' + str(index)),)),
                    now=NOW).sequence
            return database_write(db, operation)
    with ThreadPoolExecutor(2) as pool:
        assert len(set(pool.map(write, range(2)))) == 2
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(MemorySituationManifest)) == 1
        assert db.scalar(select(func.count()).select_from(MemorySituationReceipt)) == 2
    assert engine.pool.checkedout() == 0


def test_receipt_guard_blocks_consent_update_until_effect_transaction_ends(store):
    engine, _, _ = store
    scope, identifier = seed(engine)
    manifest,draft,result=material(engine,scope)
    with Session(engine) as writer, Session(engine) as settings_writer:
        admit(writer,manifest=manifest,draft=draft,result=result,now=NOW)
        settings_writer.execute(text("SET LOCAL lock_timeout='100ms'"))
        with pytest.raises(OperationalError) as error:
            settings_writer.execute(update(MemoryScopeSettingModel).where(
                MemoryScopeSettingModel.id==identifier).values(enabled=False))
        assert error.value.orig.sqlstate=='55P03'
        settings_writer.rollback()
        writer.rollback()
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(MemorySituationReceipt))==0
        assert db.scalar(select(func.count()).select_from(MemorySituationManifest))==0


def test_stale_policy_snapshot_retries_before_late_receipt(store):
    engine, _, _ = store
    scope, identifier = seed(engine)
    manifest,draft,result=material(engine,scope)
    with Session(engine) as stale:
        assert stale.get(MemoryScopeSettingModel,identifier).enabled
        with Session(engine) as settings_writer:
            settings_writer.execute(update(MemoryScopeSettingModel).where(
                MemoryScopeSettingModel.id==identifier).values(enabled=False,
                    version=MemoryScopeSettingModel.version+1))
            settings_writer.commit()
        with pytest.raises(OperationalError) as error:
            admit(stale,manifest=manifest,draft=draft,result=result,now=NOW)
        assert error.value.orig.sqlstate=='40001'
        stale.rollback()
    with Session(engine) as fresh:
        receipt=admit(fresh,manifest=manifest,draft=draft,result=result,now=NOW)
        assert receipt.state=='skipped' and receipt.error_code=='situation_activation_closed'
        fresh.commit()
