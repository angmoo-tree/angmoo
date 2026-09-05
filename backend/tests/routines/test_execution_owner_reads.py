from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from app.domains.characters.models import CharacterState
from app.domains.characters.service.state import get_character_state
from app.domains.routines.models import AgentSlot
from app.domains.routines.repository.slots import get_agent_slot
from app.domains.routines.service.activity_settings import get_setting
from app.domains.routines.service.post_selection import _select_tick_post_id
from app.domains.social.repository import resident_context as queries
from app.runtime.resident.post_selection import SqlAlchemyPostSelectionReferences
from routine_posts.test_runtime import _seed
from social.test_resident_context_queries import _engine, _post


def test_target_queries_keep_visibility_nonself_priority_and_pending_rollback(tmp_path):
    engine = _engine(tmp_path)
    with Session(engine, expire_on_commit=False) as db:
        fixture = _seed(db)
        actor = fixture.character.id
        now = datetime(2026, 9, 6, 9, tzinfo=UTC)
        own = _post('self-newest', actor)
        foreign_a = _post('foreign-a', None)
        foreign_z = _post('foreign-z', None)
        hidden = _post('hidden-new', None, hidden=True)
        deleted = _post('deleted-new', None, deleted=True)
        reply = _post('reply-new', None, parent_id='foreign-a')
        for row in [foreign_a, foreign_z]:
            row.created_at = now
        for row in [own, hidden, deleted, reply]:
            row.created_at = now + timedelta(minutes=1)
        db.add_all([own, foreign_a, foreign_z, hidden, deleted])
        db.flush()
        db.add(reply)
        db.commit()
        references = SqlAlchemyPostSelectionReferences(db)
        assert queries.get_latest_visible_nonself_root_id(db, actor) == 'foreign-z'
        assert queries.get_latest_visible_root_id(db) == 'self-newest'
        assert _select_tick_post_id(references, preferred_post_id=None, character_id=actor) == 'foreign-z'
        assert _select_tick_post_id(None, preferred_post_id='unqueried-preferred', character_id=actor) == 'unqueried-preferred'
        foreign_a.report_hidden_at = now
        foreign_z.deleted_at = now
        assert _select_tick_post_id(references, preferred_post_id=None, character_id=actor) == 'self-newest'
        own.deleted_at = now
        assert _select_tick_post_id(references, preferred_post_id=None, character_id=actor) is None
        with Session(engine) as observer:
            assert queries.get_latest_visible_nonself_root_id(observer, actor) == 'foreign-z'
        db.rollback()
        assert queries.get_latest_visible_nonself_root_id(db, actor) == 'foreign-z'
    engine.dispose()


def test_nullable_owner_reads_keep_attached_identity_without_flush_or_commit(tmp_path):
    engine = _engine(tmp_path)
    with Session(engine, expire_on_commit=False) as db:
        fixture = _seed(db)
        actor = fixture.character.id
        assert get_character_state(db, 'missing') is None
        assert get_agent_slot(db, 'missing') is None
        assert get_setting(db, 'missing') is None
        state = db.get(CharacterState, actor)
        if state is None:
            state = CharacterState(character_id=actor, mood='neutral', summary='original', memory_note='')
            db.add(state)
        state.summary = 'original'
        slot = AgentSlot(agent_id='read-slot', status='idle')
        db.add(slot)
        db.commit()
        state.summary = 'pending'
        slot.status = 'running'
        assert get_character_state(db, actor) is state
        assert get_agent_slot(db, slot.agent_id) is slot
        assert state in db.dirty
        assert slot in db.dirty
        with Session(engine) as observer:
            assert get_character_state(observer, actor).summary == 'original'
            assert get_agent_slot(observer, slot.agent_id).status == 'idle'
        db.rollback()
        assert state.summary == 'original'
        assert slot.status == 'idle'
    engine.dispose()
