"""Initialized policy capture does not take the memory application's writer."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from threading import Barrier

import pytest
from sqlalchemy import event, select, func, text, update
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from postgresql.test_activity_transactions import store
from memory.test_p8_l_o_memory_consolidation import _stack
from memory.test_activity_situation_contract import values, NOW
from app.contracts.environment import EnvironmentSnapshot
from app.core.database_transactions import database_write
from app.domains.memory.models.items import MemoryScopeSettingModel
from app.domains.memory.models.activity_situation import MemorySituationProcessingSetting
from app.domains.memory.repository.situation_admission import admit
from app.domains.memory.repository.situation_runs import get_or_create_settings
from app.domains.memory.service.situation_policy import capture, restore


def seed(engine, *, initialized=True):
    with Session(engine) as db:
        scope, setting, *_ = _stack(db)
        if initialized:
            capture(db, owner_id=scope.owner_id, world_id=scope.world_id,
                actor_id=scope.subject_world_character_id, environment=EnvironmentSnapshot(),
                policy='activity_situation')
        db.commit()
        return scope, setting.id


def test_existing_capture_reads_while_application_holds_scope_writer(store):
    engine, _, _ = store
    scope, identifier = seed(engine)
    statements = []
    def record(conn, cursor, sql, params, context, many):
        statements.append(sql)
    with Session(engine) as writer:
        writer.execute(update(MemoryScopeSettingModel).where(MemoryScopeSettingModel.id==identifier)
            .values(updated_at=MemoryScopeSettingModel.updated_at))
        event.listen(engine, 'before_cursor_execute', record)
        try:
            with Session(engine) as reader:
                reader.execute(text("SET LOCAL lock_timeout='50ms'"))
                result = capture(reader, owner_id=scope.owner_id, world_id=scope.world_id,
                    actor_id=scope.subject_world_character_id, environment=EnvironmentSnapshot(),
                    policy='activity_situation')
                assert restore(result).setting_id == identifier
        finally:
            event.remove(engine, 'before_cursor_execute', record)
    assert not any(s.lstrip().upper().startswith(('INSERT','UPDATE','DELETE')) for s in statements)


def test_mutating_settings_still_take_scope_fence(store):
    engine, _, _ = store
    _, identifier = seed(engine)
    with Session(engine) as first, Session(engine) as second:
        get_or_create_settings(first, identifier, timezone='UTC', now=NOW)
        second.execute(text("SET LOCAL lock_timeout='50ms'"))
        with pytest.raises(OperationalError) as error:
            get_or_create_settings(second, identifier, timezone='UTC', now=NOW)
        assert error.value.orig.sqlstate == '55P03'


@pytest.mark.parametrize('first_isolation', ['SERIALIZABLE', 'REPEATABLE READ'])
def test_concurrent_first_initialization_retries_to_one_row(store, first_isolation):
    engine, _, _ = store
    _, identifier = seed(engine, initialized=False)
    barrier=Barrier(2)
    def initialize(number):
        with Session(engine) as db:
            barrier.wait(timeout=5)
            def operation():
                result=capture(db,owner_id='consolidation-owner',world_id='consolidation-world',
                    actor_id='consolidation-subject',environment=EnvironmentSnapshot(),policy='activity_situation')
                assert restore(result).setting_id == identifier
                return db.get(MemorySituationProcessingSetting,identifier).version
            return database_write(db,operation,
                postgres_isolation=first_isolation if number == 0 else 'SERIALIZABLE')
    with ThreadPoolExecutor(2) as pool:
        assert list(pool.map(initialize,range(2))) == [1,1]
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(MemorySituationProcessingSetting)) == 1
    assert engine.pool.checkedout() == 0


def test_disabled_scope_after_capture_still_skips_late_receipt(store):
    engine, _, _ = store
    scope, identifier = seed(engine)
    with Session(engine) as db:
        frozen = capture(db,owner_id=scope.owner_id,world_id=scope.world_id,
            actor_id=scope.subject_world_character_id,environment=EnvironmentSnapshot(),
            policy='activity_situation')
        manifest,draft,result=values(db,scope)
        manifest=replace(manifest,snapshot=restore(frozen))
        db.commit()
    with Session(engine) as db:
        setting=db.get(MemoryScopeSettingModel,identifier)
        setting.enabled=False;setting.version+=1
        db.commit()
    with Session(engine) as db:
        receipt=admit(db,manifest=manifest,draft=draft,result=result,now=NOW)
        assert receipt.state=='skipped' and receipt.error_code=='situation_activation_closed'
        db.commit()
