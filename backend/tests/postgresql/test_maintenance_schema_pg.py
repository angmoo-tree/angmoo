"""Actual PG v3 upgrade and common-slot exclusion in an owned fixture schema."""
from sqlalchemy import text, event, select, func
from sqlalchemy.orm import sessionmaker
from postgresql.test_activity_transactions import store
from app.runtime.persistence.postgresql_schema import initialize, VERSION
from app.runtime.memory.maintenance_slot import MaintenanceSlot


def test_v3_upgrade_preserves_rows_and_slot_excludes_second_runtime(store):
    engine,_,_=store
    with engine.begin() as connection:
        before=connection.execute(text("SELECT count(*) FROM users")).scalar_one()
        connection.exec_driver_sql("DROP TABLE memory_maintenance_slot")
        for name in ("relationship_review_work","relationship_review_requests","memory_situation_runs"):
            connection.exec_driver_sql(f"ALTER TABLE {name} DROP COLUMN maintenance")
        connection.exec_driver_sql("UPDATE angmoo_postgresql_schema_version SET version=3")
        initialize(connection)
        assert connection.execute(text("SELECT version FROM angmoo_postgresql_schema_version")).scalar_one()==VERSION
        assert connection.execute(text("SELECT count(*) FROM users")).scalar_one()==before
        initialize(connection)  # Repeatable upgrade, no duplicate slot/data.
    first,second=MaintenanceSlot(sessionmaker(engine)),MaintenanceSlot(sessionmaker(engine))
    token=first.acquire("memory")
    assert token and second.acquire("relationship") is None
    first.release(token)
    other=second.acquire("relationship")
    assert other
    second.release(other)


def test_inbox_received_draft_survives_exhausted_round_then_publishes_once(store):
    """Four real 40001 aborts defer only storage; the next round reuses a draft."""
    from datetime import datetime, UTC
    import time
    from sqlalchemy.orm import Session
    from postgresql.test_activity_transactions import seed
    from app.domains.social.models.posts import PostLike
    from app.domains.routines.models.resident import AgentPublicActionExecution as Execution
    from app.runtime.social.planned_actions import _execute_planned_action
    from app.runtime.social.delivery_recovery import DeliveryStorageWait
    import pytest
    engine,_,_=store
    with Session(engine,expire_on_commit=False) as db:
        ctx,post,actor,run=seed(db)
        action={"action_type":"like","post_id":post.id,"brief":"Remembered draft"}
        writes=[]
        in_other=False
        def collide(connection,cursor,statement,parameters,context,many):
            nonlocal in_other
            if in_other or len(writes)>=4 or not statement.startswith('UPDATE agent_slots SET lease_expires_at'):
                return
            writes.append(1)
            in_other=True
            try:
                with engine.begin() as other:
                    other.execute(text("UPDATE agent_slots SET lease_expires_at=lease_expires_at+interval '1 second' WHERE agent_id=:id"),{'id':ctx.agent_id})
            finally:
                in_other=False
        def validate():
            db.execute(text('SELECT lease_expires_at FROM agent_slots WHERE agent_id=:id'),{'id':ctx.agent_id}).one()
            db.execute(text("UPDATE agent_slots SET lease_expires_at=lease_expires_at+interval '1 millisecond' WHERE agent_id=:id"),{'id':ctx.agent_id})
        event.listen(engine,'before_cursor_execute',collide)
        try:
            with pytest.raises(DeliveryStorageWait) as error:
                _execute_planned_action(ctx,action=action,writing={},scope='inbox',index=0,relationship_validator=validate)
        finally:
            event.remove(engine,'before_cursor_execute',collide)
        assert len(writes)==4
        saved=db.scalar(select(Execution))
        assert saved.status=='storage_retry_wait' and saved.result['_delivery']['payload']['action']==action
        identifier=saved.id
        db.rollback()
        time.sleep(error.value.seconds)
        result=_execute_planned_action(ctx,action=action,writing={},scope='inbox',index=0,relationship_validator=validate)
        assert result['status']=='succeeded'
        assert db.scalar(select(func.count(PostLike.id)))==1
        assert db.scalar(select(func.count(Execution.id)))==1 and db.get(Execution,identifier).status=='succeeded'
        assert _execute_planned_action(ctx,action=action,writing={},scope='inbox',index=0,relationship_validator=validate)['status']=='reused'
