"""Lazy activity reads keep attached values and the original summary order."""
from dataclasses import replace
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app import models as _registered_models
from app.domains.characters.models import Character
from app.domains.identity.models import User
from app.domains.routines.models import AgentActivityLog
from app.domains.routines.service import activity_presentation, slot_status
from app.runtime.characters.management import build_activity_presentation_reads


@pytest.mark.parametrize("profile_type", ["character", "user"])
def test_activity_target_uses_same_attached_profile_and_preserves_rollback(tmp_path, profile_type):
    engine = create_engine(f"sqlite:///{tmp_path / 'presentation.sqlite3'}")
    for table in (User.__table__, Character.__table__):
        table.create(engine)
    try:
        with Session(engine) as db:
            user = User(id="owner", display_name="original")
            character = Character(id="character", owner_id="owner", name="original", handle="presentation", persona_summary="fixture")
            db.add_all([user, character])
            db.commit()
            row = character if profile_type == "character" else user
            field = "name" if profile_type == "character" else "display_name"
            setattr(row, field, "pending")
            log = AgentActivityLog(action_type="followed", result=f"{profile_type}:{row.id}")
            original = build_activity_presentation_reads()
            getter = original.get_character if profile_type == "character" else original.get_user
            def read(current, identity):
                assert current is db
                result = getter(current, identity)
                assert result is row
                return result
            reads = replace(original, **{f"get_{profile_type}": read})
            result = activity_presentation._activity_log_target_profile(db, log, reads=reads)
            assert result["target_profile_name"] == "pending"
            assert result["target_profile_type"] == profile_type
            with Session(engine) as observer:
                assert getattr(observer.get(type(row), row.id), field) == "original"
            db.rollback()
            assert getattr(row, field) == "original"
    finally:
        engine.dispose()


def test_activity_summary_resolves_lazy_counts_in_original_field_order():
    at = datetime(2026, 9, 5, tzinfo=UTC)
    setting = SimpleNamespace(auto_enabled=True, max_comments_per_day=2, max_posts_per_day=3)
    character = SimpleNamespace(id="character")
    slot = SimpleNamespace(next_tick_at=at)
    policy = SimpleNamespace(within_active_hours=True, allowed_actions=("post", "observe", "like"), blocked_reasons={})
    db = object()
    calls = []
    def timezone(current, *, character_id):
        assert current is db and character_id == "character"
        calls.append("timezone")
        setting.auto_enabled = False
        return "Asia/Seoul"
    def count(current, *, character_id, action):
        assert current is db and character_id == "character"
        calls.append(action)
        if action == "comment":
            setting.max_comments_per_day = 9
        if action == "post":
            setting.max_posts_per_day = 11
        return 1
    reads = replace(build_activity_presentation_reads(), activity_timezone_name=timezone, count_action_today=count)
    summary = activity_presentation.build_activity_summary(db, character=character, setting=setting, slot=slot, policy=policy, last_activity_at=at, manual_run_available_at=None, first_greeting_available_at=None, reads=reads)
    assert calls == ["timezone", "comment", "post", "like"]
    assert summary.next_activity_at is None
    assert summary.allowed_actions == ["post", "like"]
    assert summary.max_comments_per_day == 9
    assert summary.max_posts_per_day == 11


def test_execution_readiness_rejects_missing_setting():
    assert slot_status._has_tendency_analysis(None) is False
