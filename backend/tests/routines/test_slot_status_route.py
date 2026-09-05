from sqlalchemy.orm import Session

from app.api.v1.routes import agent_runs as routes
from app.domains.routines.models import AgentSlot
from routine_posts.test_runtime import _seed
from social.test_resident_context_queries import _engine


def test_slot_route_keeps_owner_filter_and_original_public_response(tmp_path):
    engine = _engine(tmp_path)
    with Session(engine, expire_on_commit=False) as db:
        fixture = _seed(db)
        own = AgentSlot(agent_id="owned-slot", assigned_user_id=fixture.user.id,
                        assigned_character_id=fixture.character.id,
                        locked_by_run_id="private-lock-owner")
        other = AgentSlot(agent_id="unassigned-slot")
        db.add_all([own, other])
        db.commit()
        output = routes.list_resident_slots(db=db, user=fixture.user)
        assert len(output) == 1
        assert output[0].agent_id == own.agent_id
        assert output[0].assigned_character_id == fixture.character.id
        payload = output[0].model_dump()
        assert "assigned_user_id" not in payload
        assert "assigned_credential_id" not in payload
        assert "locked_by_run_id" not in payload
        own.assigned_user_id = None
        assert routes.list_resident_slots(db=db, user=fixture.user) == []
        with Session(engine) as observer:
            assert len(routes.list_resident_slots(db=observer, user=fixture.user)) == 1
        db.rollback()
        assert len(routes.list_resident_slots(db=db, user=fixture.user)) == 1
    engine.dispose()
