"""WC runtime-mode ownership preserves the activity plan caller transaction."""
from sqlalchemy import create_engine, event, inspect
from sqlalchemy.orm import Session
from app.core.db import Base
from app.domains.world_characters.service.runtime_modes import set_activity_runtime_mode
from test_runtime_mode_repair import _user, _seed_world_scope, _seed_ready_entry


def test_mode_write_defers_flush_and_commit_and_rolls_back_with_caller():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add(_user())
        db.flush()
        _seed_world_scope(db, "world-local")
        target = _seed_ready_entry(db, world_id="world-local", suffix="mode-write")
        db.commit()
        db.refresh(target)
        original_version, original_mode = target.version, target.activity_runtime_mode
        calls = []
        event.listen(db, "after_flush", lambda *_: calls.append("flush"))
        event.listen(db, "after_commit", lambda *_: calls.append("commit"))
        set_activity_runtime_mode(target, activity_runtime_mode="legacy_agent_v1")
        assert inspect(target).session is db
        assert target.activity_runtime_mode == "legacy_agent_v1"
        assert target.version == original_version + 1
        assert target.feed_runtime_mode == "legacy_latest_v1"
        assert calls == []
        db.rollback()
        assert target.activity_runtime_mode == original_mode
        assert target.version == original_version
