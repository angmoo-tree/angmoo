"""Daypart composition shares the caller Session and preserves write ordering."""
import app.domains.social.repository.posts as social_posts_actual

from datetime import date
import os
from pathlib import Path
import subprocess
import sys

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.domains.characters.models import Character
from app.domains.identity.models import User
from app.domains.memory.models.daypart import AgentDaypartMemoryEvent
from app.domains.social.models.posts import Post
from app.runtime.memory import daypart_observations
from app.runtime.persistence.model_registration import register_models
from app.runtime.resident.context_references import SqlAlchemyResidentActionReferences


@pytest.fixture
def engine(tmp_path):
    value = create_engine(f"sqlite:///{tmp_path / 'daypart-bindings.sqlite3'}")
    register_models().create_all(value)
    with Session(value) as db:
        db.add(User(id="owner", display_name="Original user"))
        db.add(Character(id="character", owner_id="owner", name="Original character", handle="daypart", persona_summary="Synthetic fixture"))
        db.add_all([
            Post(id="character-post", author_character_id="character", author_name="Character", title="Synthetic", body="Fixture"),
            Post(id="user-post", author_user_id="owner", author_name="User", title="Synthetic", body="Fixture"),
        ])
        db.commit()
    try:
        yield value
    finally:
        value.dispose()


@pytest.mark.parametrize("author_type", ["character", "user"])
def test_note_author_uses_attached_profile_without_committing(engine, author_type):
    with Session(engine, autoflush=False) as db:
        model, identity, field = (Character, "character", "name") if author_type == "character" else (User, "owner", "display_name")
        author = db.get(model, identity)
        setattr(author, field, "Pending author")
        expected = "Pending author (@daypart)" if author_type == "character" else "Pending author"
        note = daypart_observations._build_daypart_memory_note(
            profile_references=SqlAlchemyResidentActionReferences,
            db=db, activity_daypart="morning", daypart_start_date=date(2026, 6, 24),
            character=db.get(Character, "character"), run_id="run-a", inbox_candidates=[],
            feed_interest_payload={"interests": [{"post_id": f"{author_type}-post", "summary": "Synthetic observation"}]},
        )
        assert f"- seen_person: {expected}" in note
        assert db.is_modified(author)
        with Session(engine) as observer:
            assert getattr(observer.get(model, identity), field).startswith("Original")
        def unavailable_references(current):
            raise AssertionError("missing post must not create profile references")
        assert daypart_observations._daypart_observation_author(db, "missing", "unknown", profile_references=unavailable_references) == "unknown"
        assert daypart_observations._daypart_observation_author(db, None, None, profile_references=unavailable_references) is None
        db.rollback()
        assert getattr(author, field).startswith("Original")


def test_provided_observations_commit_inbox_before_same_session_author_read(engine, monkeypatch):
    with Session(engine) as db:
        calls = []
        original = daypart_observations.community_crud.get_post

        def get_post(current, post_id):
            assert current is db
            calls.append(post_id)
            with Session(engine) as observer:
                assert [row.event_type for row in observer.scalars(select(AgentDaypartMemoryEvent))] == ["observation_inbox"]
            return original(current, post_id)

        monkeypatch.setattr(social_posts_actual, "get_post", get_post)
        daypart_observations._record_provided_daypart_observations(
            db, character_id="character", memory_session_key="session-a",
            profile_references=SqlAlchemyResidentActionReferences,
            daypart_start_date=date(2026, 6, 24), activity_daypart="morning", run_id="run-a",
            inbox_candidates=[{"notification_id": "12", "actor_name": "Inbox author", "root_summary": "Inbox"}],
            feed_interest_payload={"interests": [{"post_id": "character-post", "summary": "Feed"}]},
        )
        assert calls == ["character-post"]
        db.rollback()
        with Session(engine) as observer:
            rows = list(observer.scalars(select(AgentDaypartMemoryEvent).order_by(AgentDaypartMemoryEvent.id)))
            assert [row.event_type for row in rows] == ["observation_inbox", "observation_feed"]
            assert rows[1].payload == {"source_item_id": "post:character-post", "seen_person": "Original character (@daypart)"}


def test_cold_resident_imports_use_actual_owners_and_explicit_registration():
    backend = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        [sys.executable, "-c", """
import sys
from sqlalchemy.orm import configure_mappers
from app.models import Base
from app.runtime.memory import daypart_observations
from app.runtime.resident import execution, writing, langgraph
from app.domains.memory.service import daypart, daypart_observations as observations
from app.domains.identity.repository import credentials
from app.domains.relationships.service import points
from app.runtime.persistence.model_registration import register_models
import app.database as database
assert execution._build_daypart_memory_note is daypart_observations._build_daypart_memory_note
assert execution._record_provided_daypart_observations is daypart_observations._record_provided_daypart_observations
assert execution._filter_daypart_duplicate_inbox_candidates is observations.filter_daypart_duplicate_inbox_candidates
assert writing._record_daypart_action_memory is daypart.record_action_memory
assert writing.agent_run_crud.get_credential is credentials.get_credential
assert langgraph.relationship_points is points
assert 'app.services.agent_writing' not in sys.modules
assert 'app.cruds.agent_runs' not in sys.modules
metadata = register_models()
configure_mappers()
assert metadata is Base.metadata is register_models()
assert len(Base.registry.mappers) == len(metadata.tables) == 103
assert database._default_engine is None
assert database._default_session_factory is None
"""],
        cwd=backend, env={**os.environ, "APP_ENV": "test", "PYTHONPATH": str(backend)},
        capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == ""
