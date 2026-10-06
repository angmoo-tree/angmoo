"""Autonomous ownership, frozen runs and bounded future scheduling on real SQLite."""
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from app.domains.characters.models import Character
from app.domains.identity.models import InstallationIdentity
from app.domains.identity.schemas_environment import EnvironmentReport
from app.domains.identity.service.environment import report_environment
from app.domains.routines.models import AgentActivitySetting, AgentSlot
from app.domains.routines.service.environment_schedule import reconcile_environment_schedules
from app.domains.world_characters.activity_models import ActivityGraphRun
from app.domains.world_characters.models import CharacterActiveWorld, CharacterWorldBinding, WorldCharacter
from app.domains.world_characters.service.activity_engines import bind_run
from app.runtime.autonomous_activity.combined_provider import RecoveryLedger
from app.runtime.world_characters.creation_configuration import initialize_created_world_character
from retention_support import database

pytestmark = pytest.mark.usefixtures("deny_external_network")
NOW = datetime(2026, 10, 3, 0, tzinfo=UTC)


def test_autonomous_owner_snapshot_survives_restart_while_idle_schedule_moves(tmp_path):
    engine, factory, ids = database(tmp_path)
    try:
        with factory() as db:
            owner, a_id, actor_id, world_id, _ = ids
            actor = db.get(WorldCharacter, actor_id)
            # This is the supported autonomous schema: owner_user_id is NULL.
            assert actor.owner_user_id is None
            db.add(InstallationIdentity(singleton_key="local-installation", installation_id="synthetic",
                                       owner_user_id=owner, bootstrap_state="claimed", claimed_at=NOW))
            for key in ("idle-b", "cooldown-c"):
                db.add(Character(id=key, owner_id=owner, name=key, handle=key, persona_summary="Original A-17"))
                db.add(AgentActivitySetting(character_id=key, active_hours_start="09:00", active_hours_end="10:00"))
            db.add(WorldCharacter(id="actor-b", world_id=world_id, character_id="idle-b",
                                  membership_id=actor.membership_id, status="active", control_mode="autonomous"))
            db.flush()
            db.add(CharacterWorldBinding(character_id="idle-b", world_id=world_id))
            db.add(CharacterActiveWorld(character_id="idle-b", world_character_id="actor-b",
                selected_at=NOW, idempotency_key="synthetic:actor-b", version=1))
            db.flush()
            initialize_created_world_character(db, character=db.get(Character, "idle-b"),
                world_character=db.get(WorldCharacter, "actor-b"))
            first = report_environment(db, owner, EnvironmentReport(client_id="synthetic-screen-1",
                expected_revision=0, sequence=1, preferred_language="ko-KR", timezone="Asia/Seoul"),
                session_hash="session", now=NOW)
            a = bind_run(db, actor=actor, activity_id="frozen-a")
            assert a.result["environment_snapshot"]["memory_search_locale"] == "ko-KR"
            assert a.result["environment_snapshot"]["timezone"] == "Asia/Seoul"
            db.add_all([
                AgentSlot(agent_id="running-a", status="running", assigned_user_id=owner,
                    assigned_character_id=a_id, locked_by_run_id="frozen-a", timezone_revision=1,
                    next_tick_at=NOW + timedelta(minutes=30), lease_expires_at=NOW + timedelta(minutes=10)),
                AgentSlot(agent_id="idle-b", status="assigned_idle", assigned_user_id=owner,
                    assigned_character_id="idle-b", timezone_revision=1, next_tick_at=NOW + timedelta(minutes=2)),
                AgentSlot(agent_id="cooldown-c", status="cooldown", assigned_user_id=owner,
                    assigned_character_id="cooldown-c", timezone_revision=1, next_tick_at=NOW + timedelta(minutes=5)),
            ])
            db.commit()
            RecoveryLedger(db, "frozen-a").reserve("FeedActionPlanner:json")
            old_result = dict(a.result)
            report_environment(db, owner, EnvironmentReport(client_id="synthetic-screen-1",
                expected_revision=1, sequence=2, lease_token=first.lease_token,
                preferred_language="ja-JP", timezone="America/New_York"), session_hash="session", now=NOW+timedelta(seconds=60))
            assert reconcile_environment_schedules(db, now=NOW+timedelta(seconds=60), limit=1) == 1
            db.commit()
        # A fresh process/session sees the same frozen admission and recovery ID.
        with factory() as restarted:
            assert bind_run(restarted, actor=restarted.get(WorldCharacter, actor_id), activity_id="frozen-a").result == old_result
            assert reconcile_environment_schedules(restarted, now=NOW+timedelta(seconds=60), limit=1) == 1
            b = bind_run(restarted, actor=restarted.get(WorldCharacter, "actor-b"), activity_id="new-b")
            assert b.result["environment_snapshot"]["memory_search_locale"] == "ja-JP"
            assert b.result["environment_snapshot"]["timezone_revision"] == 2
            assert restarted.get(AgentSlot, "running-a").timezone_revision == 1
            assert restarted.get(AgentSlot, "running-a").locked_by_run_id == "frozen-a"
            assert restarted.get(AgentSlot, "cooldown-c").next_tick_at.replace(tzinfo=UTC) == NOW+timedelta(minutes=5)
            idle = restarted.get(AgentSlot, "idle-b")
            assert idle.timezone_revision == 2
            assert datetime(2026, 10, 3, 13, tzinfo=UTC) <= idle.next_tick_at.replace(tzinfo=UTC) < datetime(2026, 10, 3, 14, tzinfo=UTC)
            restarted.commit()
        with factory() as final:
            assert reconcile_environment_schedules(final, now=NOW+timedelta(minutes=2), limit=32) == 0
            assert final.get(ActivityGraphRun, "frozen-a").result == old_result
            with pytest.raises(ValueError, match="recovery_exhausted"):
                RecoveryLedger(final, "frozen-a").reserve("FeedActionPlanner:json")
    finally:
        engine.dispose()
