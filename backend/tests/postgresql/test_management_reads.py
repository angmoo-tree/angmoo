"""Serializable read conflicts restart the entire authorized dashboard snapshot."""
from sqlalchemy import event
from sqlalchemy.orm import Session, sessionmaker
from postgresql.test_activity_transactions import store
from social.test_l4_social_write_uow import _seed
from app.domains.identity.models import User
from app.runtime.world_characters.management import management_service


def test_dashboard_read_retries_confirmed_abort_and_returns_connections(store):
    engine, _, _ = store
    _seed(sessionmaker(engine, expire_on_commit=False))
    seen = []
    def abort_once(connection, cursor, statement, parameters, context, many):
        if statement.startswith('SELECT agent_slots.'):
            seen.append(1)
            if len(seen)==1:
                connection.exec_driver_sql("DO $$ BEGIN RAISE EXCEPTION 'synthetic read abort' USING ERRCODE='40001'; END $$")
    with Session(engine) as db:
        owner = db.get(User, 'social-uow-owner')
        service = management_service(db)
        before = service.dashboard(world_id='social-uow-world',user=owner)
        event.listen(engine,'before_cursor_execute',abort_once)
        try:
            after = service.dashboard(world_id='social-uow-world',user=owner)
        finally:
            event.remove(engine,'before_cursor_execute',abort_once)
        assert after.model_dump()==before.model_dump()
        assert len(seen)==2
        assert not db.in_transaction()
    assert engine.pool.checkedout()==0


def test_retained_character_is_readable_without_reopening_activity_admission(store):
    import pytest
    from sqlalchemy import select
    from app.domains.characters.models import Character
    from app.domains.world_characters.models import CharacterActiveWorld, WorldCharacter
    from app.domains.routines.exceptions import ActivityRuntimeValidationError
    from app.runtime.routines.configuration_reads import capture_activity_input
    from app.runtime.characters.management import _build_agent_detail
    engine, _, _ = store
    _seed(sessionmaker(engine, expire_on_commit=False))
    with Session(engine) as db:
        character=db.get(Character,'social-uow-autonomous-character')
        role=db.scalar(select(WorldCharacter).where(WorldCharacter.character_id==character.id))
        role.status='inactive'
        binding=db.get(CharacterActiveWorld,character.id)
        if binding is not None:db.delete(binding)
        db.commit()
        detail=_build_agent_detail(db,character)
        assert detail.character.id==character.id
        assert detail.activity_summary.allowed_actions==[]
        assert set(detail.activity_summary.blocked_reasons.values())=={'world_character_binding_invalid'}
        assert detail.activity_summary.next_activity_at is None
        assert detail.activity_summary.manual_run_available_at is None
        assert detail.activity_summary.first_greeting_available_at is None
        assert not detail.activity_profile_readiness.can_view_graph
        with pytest.raises(ActivityRuntimeValidationError,match='world_character_binding_invalid'):
            capture_activity_input(db,character_id=character.id)
        assert db.get(CharacterActiveWorld,character.id) is None and role.status=='inactive'
