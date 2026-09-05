from dataclasses import replace
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app import exceptions as common_errors
from app.domains.characters import exceptions as character_errors
from app.domains.characters.models import Character
from app.domains.routines import exceptions, models, schemas
from app.domains.routines.service import activity_management, activity_settings
from app.runtime.characters.management import build_activity_management_references
from routine_posts.test_runtime import _seed
from social.test_resident_context_queries import _engine


def test_activity_setting_owner_preserves_pending_schedule_transaction_and_error_identity(tmp_path):
    engine = _engine(tmp_path)
    with Session(engine, expire_on_commit=False) as db:
        fixture = _seed(db)
        character_id = fixture.character.id
        setting = activity_settings.ensure_setting(db, character_id)
        setting.auto_enabled = True
        slot = models.AgentSlot(
            agent_id='settings-owner-slot', status='assigned_idle',
            assigned_user_id=fixture.user.id, assigned_character_id=character_id,
            assigned_credential_id='credential-routine', heartbeat_interval_seconds=3600,
            next_tick_at=datetime.now(UTC) - timedelta(hours=1),
        )
        db.add(slot)
        db.commit()
        previous_tick = slot.next_tick_at
        fixture.character.name = 'pending-settings-owner'
        references = build_activity_management_references()
        observed = []
        def get_owned(session, user, key):
            assert session is db and user is fixture.user and key == character_id
            result = references.get_owned_character(session, user, key)
            assert result is fixture.character
            observed.append('owner')
            return result
        def mutable(user):
            assert user is fixture.user
            observed.append('mutable')
            references.ensure_mutable(user)
        def timezone_reader(session, *, character_id):
            assert session is db
            assert activity_settings.get_setting(session, character_id) is setting
            assert setting.activity_interval_minutes == 120
            assert slot.heartbeat_interval_seconds == 7200
            with Session(engine) as observer:
                assert activity_settings.get_setting(observer, character_id).activity_interval_minutes == 60
                assert observer.get(Character, character_id).name == 'Mira'
            observed.append('timezone')
            return ZoneInfo('UTC')
        response = activity_management.update_settings(
            db, fixture.user, character_id,
            schemas.AgentActivitySettingUpdate(activity_interval_minutes=120),
            references=replace(references, get_owned_character=get_owned, ensure_mutable=mutable, timezone_reader=timezone_reader),
        )
        assert observed == ['owner', 'mutable', 'timezone']
        assert response.activity_interval_minutes == 120
        assert db.get(models.AgentSlot, slot.agent_id) is slot
        assert slot.next_tick_at != previous_tick
        with Session(engine) as observer:
            assert activity_settings.get_setting(observer, character_id).activity_interval_minutes == 120
            assert observer.get(Character, character_id).name == 'pending-settings-owner'
            assert observer.get(models.AgentSlot, slot.agent_id).heartbeat_interval_seconds == 7200
        assert character_errors.AgentServiceError is common_errors.AgentServiceError
        try:
            raise exceptions.AgentAutonomyCapacityError('full', active_count=3, max_active=3)
        except character_errors.AgentServiceError as error:
            assert error.reason_code == 'autonomy_capacity_full'
            assert error.active_count == error.max_active == 3
        else:
            raise AssertionError('The original Character error catch no longer handles activity errors')
    engine.dispose()
