from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

from app import models as registered_models
from app.core import unit_of_work
from app.core.db import Base
from app.domains.routines import models, schemas
from app.domains.routines.service import activity_logs, activity_settings
from app.domains.routines.contracts.plans import PlanScope
from app.domains.routines.exceptions import DailyActivityPlanValidationError
from app.domains.routines.service import plans
from app.runtime.routines import plan_references
from routine_posts.test_runtime import _seed


def _file_engine(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'activity.sqlite3'}")
    @event.listens_for(engine, "connect")
    def foreign_keys(dbapi_connection, _connection_record):
        dbapi_connection.execute("PRAGMA foreign_keys=ON")
    Base.metadata.create_all(engine)
    return engine


@pytest.mark.parametrize("commit", (False, True))
def test_setting_update_preserves_explicit_commit_and_caller_rollback(tmp_path, commit):
    engine = _file_engine(tmp_path)
    with Session(engine, expire_on_commit=False) as db:
        fixture = _seed(db)
        character_id = fixture.character.id
        setting = activity_settings.ensure_setting(db, character_id)
        original_interval = setting.activity_interval_minutes
        original_allow_post = setting.allow_post
        result = activity_settings.update_setting(
            db, setting, schemas.AgentActivitySettingUpdate(
                activity_interval_minutes=90, allow_post=None,
            ), commit=commit,
        )
        assert result is setting
        assert setting.activity_interval_minutes == 90
        assert setting.allow_post == original_allow_post
        with Session(engine) as observer:
            observed = activity_settings.get_setting(observer, character_id)
            assert observed.activity_interval_minutes == (90 if commit else original_interval)
        db.rollback()
        assert setting.activity_interval_minutes == (90 if commit else original_interval)
    engine.dispose()


def test_activity_log_joins_caller_transaction_and_keeps_visibility_policy(tmp_path):
    engine = _file_engine(tmp_path)
    now = datetime(2026, 9, 6, tzinfo=UTC)
    with Session(engine, expire_on_commit=False) as db:
        fixture = _seed(db)
        with unit_of_work.deferred_commits():
            visible = activity_logs.log_activity(
                db, user_id=fixture.user.id, character_id=fixture.character.id,
                action_type="post", target_post_id=None, reason="visible", result="saved",
            )
            visible.created_at = now
            hidden = activity_logs.log_activity(
                db, user_id=fixture.user.id, character_id=fixture.character.id,
                action_type="feed_viewed", target_post_id=None, reason="hidden", result="saved",
            )
            hidden.created_at = now + timedelta(seconds=20)
            first_state = activity_logs.log_activity(
                db, user_id=fixture.user.id, character_id=fixture.character.id,
                action_type="state_saved", target_post_id=None, reason="first state", result="saved",
            )
            first_state.created_at = now + timedelta(seconds=30)
            last_state = activity_logs.log_activity(
                db, user_id=fixture.user.id, character_id=fixture.character.id,
                action_type="state_saved", target_post_id=None, reason="last state", result="saved",
            )
            last_state.created_at = now + timedelta(seconds=60)
            log_ids = [visible.id, hidden.id, first_state.id, last_state.id]
            result = activity_logs.list_recent_activity(db, fixture.character.id)
            assert result == [last_state, visible]
            assert result[0] is last_state
            with Session(engine) as observer:
                assert [observer.get(models.AgentActivityLog, log_id) for log_id in log_ids] == [None] * 4
        db.rollback()
        assert [db.get(models.AgentActivityLog, log_id) for log_id in log_ids] == [None] * 4
    engine.dispose()


def test_plan_hash_collaboration_keeps_readiness_order_and_attached_character(tmp_path, monkeypatch):
    engine = _file_engine(tmp_path)
    with Session(engine, expire_on_commit=False) as db:
        fixture = _seed(db)
        scope = PlanScope(
            world=fixture.world, world_character=fixture.world_character,
            character=fixture.character, membership=None,
        )
        references = plan_references.SqlAlchemyPlanReferences(db)
        original_hash = plan_references.character_contract_hash
        original_repertoire = references.get_ready_repertoire
        seen = []

        def hash_character(character):
            assert character is fixture.character
            seen.append("hash")
            return original_hash(character)

        def repertoire(character_id):
            seen.append("repertoire")
            return original_repertoire(character_id)

        monkeypatch.setattr(plan_references, "character_contract_hash", hash_character)
        monkeypatch.setattr(references, "get_ready_repertoire", repertoire)
        result, candidates = plans._ready_repertoire(references, scope=scope)
        assert len(candidates) == 40
        assert result.character_contract_hash == original_hash(fixture.character)
        assert seen == ["hash", "repertoire"]
        seen.clear()
        fixture.world.status = "draft"
        with pytest.raises(DailyActivityPlanValidationError, match="world_not_ready"):
            plans._ready_repertoire(references, scope=scope)
        assert seen == []
    engine.dispose()
