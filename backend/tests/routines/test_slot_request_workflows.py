from dataclasses import replace
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy.orm import Session

from app.config import settings
from app.domains.identity.repository.credentials import get_credential, get_default_credential
from app.domains.characters.models import Character
from app.domains.routines.service import activity_settings, slot_requests
from app.domains.routines.repository.slots import get_agent_slot
from app.runtime.resident.slots import build_slot_request_workflows
from routine_posts.test_runtime import _seed
from social.test_resident_context_queries import _engine


@pytest.mark.parametrize('commit', [False, True])
def test_slot_request_keeps_lazy_gate_read_clock_lock_and_original_transaction(tmp_path, monkeypatch, commit):
    monkeypatch.setattr(settings, 'OPENCLAW_AGENT_IDS', 'request-slot')
    engine = _engine(tmp_path)
    with Session(engine, expire_on_commit=False) as db:
        fixture = _seed(db)
        actor = fixture.character.id
        events = []
        def gate(session):
            assert session is db
            events.append('gate')
        def credential_lookup(session, key):
            assert session is db
            events.append('credential')
            return get_credential(session, key)
        def timezone_reader(session, *, character_id):
            assert session is db
            assert character_id == actor
            assert activity_settings.get_setting(db, actor) is not None
            events.append('timezone')
            return ZoneInfo('UTC')
        workflows = build_slot_request_workflows(
            db, credential_lookup=credential_lookup, default_credential_lookup=get_default_credential,
            ensure_auto_ticks_available=gate, ensure_run_now_available=gate, timezone_reader=timezone_reader,
        )
        assert events == []
        original_slot_factory = workflows.slot_references
        def slot_factory():
            events.append('slot')
            references = original_slot_factory()
            assert references.db is db
            return references
        workflows = replace(workflows, slot_references=slot_factory)
        fixture.character.name = 'pending-request-owner'
        result = slot_requests.assign_resident_slot(
            db, user_id=fixture.user.id, character_id=actor, credential_id='credential-routine',
            heartbeat_interval_seconds=1800, commit=commit, workflows=workflows,
        )
        assert events == ['gate', 'credential', 'timezone', 'slot']
        assert result.agent_id == 'request-slot'
        assert result.assigned_character_id == actor
        assert result.next_tick_at is not None
        with Session(engine) as observer:
            assert (get_agent_slot(observer, 'request-slot') is not None) is commit
            assert (activity_settings.get_setting(observer, actor) is not None) is commit
            assert observer.get(Character, actor).name == ('pending-request-owner' if commit else 'Mira')
        db.rollback()
        assert (get_agent_slot(db, 'request-slot') is not None) is commit
        events.clear()
        def reject(_session):
            events.append('rejected')
            raise RuntimeError('maintenance gate closed')
        with pytest.raises(RuntimeError, match='maintenance gate closed'):
            slot_requests.assign_resident_slot(
                db, user_id=fixture.user.id, character_id=actor, credential_id='credential-routine',
                heartbeat_interval_seconds=1800, workflows=replace(workflows, ensure_auto_ticks_available=reject),
            )
        assert events == ['rejected']
    engine.dispose()
