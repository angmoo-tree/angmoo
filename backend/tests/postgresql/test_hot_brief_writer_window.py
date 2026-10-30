"""Long brief preparation must not hold the scope writer; stale publication aborts."""
from datetime import UTC, datetime

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from postgresql.test_activity_transactions import store
from postgresql.test_memory_owner_transactions import seed
from app.domains.memory.models.items import MemoryItem, MemoryHotBrief, MemoryScopeSettingModel
from app.domains.memory.exceptions import MemoryConflictError
from app.runtime.memory.composition import memory_consolidation_repository


def prepare(db, seeded):
    repository=memory_consolidation_repository(db)
    setting=repository.get_scope_setting(seeded['scope'])
    now=datetime.now(UTC)
    sources=repository.hot_brief_source_items(setting=setting,now=now,limit=24)
    assert len(sources)==1
    return repository,setting,now,sources


def test_source_preparation_does_not_block_owner_scope_writer(store):
    engine,_,_=store;seeded=seed(engine)
    with Session(engine) as reader:
        prepare(reader,seeded)
        with Session(engine) as writer:
            writer.execute(text("SET LOCAL lock_timeout='100ms'"))
            setting=writer.scalar(select(MemoryScopeSettingModel).with_for_update())
            assert setting.enabled
            writer.rollback()


@pytest.mark.parametrize('change',['pin','phantom','disable'])
def test_intervening_canonical_change_cannot_publish_stale_brief(store,change,monkeypatch):
    engine,_,_=store;seeded=seed(engine)
    with Session(engine) as reader:
        repository,setting,now,sources=prepare(reader,seeded)
        original=repository._hot_brief_rows
        changed=[]
        def read_then_change(**kwargs):
            rows=original(**kwargs)
            assert not kwargs['for_update']
            with Session(engine) as writer:
                writer.execute(text("SET LOCAL lock_timeout='100ms'"))
                repo=memory_consolidation_repository(writer)
                scope_row=repo._require_setting(setting)
                if change=='pin':
                    repo.set_item_pin(scope=seeded['scope'],item_id=seeded['memory_id'],expected_version=1,pinned=True,now=now)
                elif change=='disable':
                    scope_row.enabled=False;scope_row.version+=1
                else:
                    # A new item outside the old selected set still reads the
                    # canonical scope fence before insertion, like accept/apply.
                    old=writer.get(MemoryItem,seeded['memory_id'])
                    values={column.name:getattr(old,column.name) for column in MemoryItem.__table__.columns}
                    values.update(id='phantom-new-memory',summary='A concurrently inserted memory.')
                    writer.add(MemoryItem(**values))
                    repo._invalidate_hot_briefs(setting.id,now=now)
                writer.commit()
            changed.append(True)
            return rows
        monkeypatch.setattr(repository,'_hot_brief_rows',read_then_change)
        with pytest.raises((DBAPIError,MemoryConflictError)) as error:
            repository.replace_hot_brief(setting=setting,expected_source_items=sources,
                summary='Derived summary',contract_version='memory-hot-brief.v1',now=now)
            reader.commit()
        if isinstance(error.value,DBAPIError):
            assert error.value.orig.sqlstate=='40001'
        assert changed==[True]
        reader.rollback()
    with Session(engine) as check:
        assert check.scalar(select(func.count()).select_from(MemoryHotBrief))==0
    assert engine.pool.checkedout()==0


def test_unchanged_brief_still_publishes_with_short_final_fence(store):
    engine,_,_=store;seeded=seed(engine)
    with Session(engine) as db:
        repository,setting,now,sources=prepare(db,seeded)
        value=repository.replace_hot_brief(setting=setting,expected_source_items=sources,
            summary='Derived summary',contract_version='memory-hot-brief.v1',now=now)
        db.commit()
        assert value.source_items==((seeded['memory_id'],1),)
    assert engine.pool.checkedout()==0
