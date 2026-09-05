"""Joined reads retain SQL shape, membership scope and caller attachment."""
from sqlalchemy import event, inspect
from sqlalchemy.orm import Session
from app import models
from app.runtime.world_characters.queries import SqlAlchemyWorldCharacterQueries
from test_lifecycle import _fixture, _seed_world, _character, _world_character


def test_joined_read_adapter_retains_filters_order_null_rows_and_one_query_each():
    _client, engine, principal = _fixture()
    owner, outsider = _seed_world(engine, principal)
    with Session(engine) as db:
        db.add_all([
            _character("tie-first", owner.id, name="Equal"),
            _character("tie-second", owner.id, name="Equal"),
            _character("suspended", owner.id, name="A", moderation_status="suspended"),
            _character("pending", owner.id, name="B"),
            _character("unlinked", owner.id, name="C"),
            _character("outsider", outsider.id, name="A"),
        ])
        db.flush()
        db.add_all([
            _world_character("wc-b", "tie-first", status="active"),
            _world_character("wc-a", "tie-second", status="active"),
            _world_character("wc-s", "suspended", status="active"),
            _world_character("wc-p", "pending", status="pending"),
        ])
        db.commit()
    calls = []
    event.listen(engine, "before_cursor_execute", lambda *_: calls.append(1))
    with Session(engine) as db:
        queries = SqlAlchemyWorldCharacterQueries()
        public = queries.public_profile_rows(db, "world-a")
        assert len(calls) == 1
        assert [wc.id for wc, _character_row in public] == ["wc-a", "wc-b"]
        assert all(inspect(row).session is db for pair in public for row in pair)
        studio = queries.studio_rows(db, "world-a")
        assert len(calls) == 2
        assert [wc.id for wc, _character_row in studio] == ["wc-s", "wc-p", "wc-a", "wc-b"]
        candidates = queries.candidate_rows(db, "world-a", owner.id)
        assert len(calls) == 3
        assert [character.id for character, _wc in candidates] == ["suspended", "pending", "unlinked", "tie-first", "tie-second"]
        assert next(wc for character, wc in candidates if character.id == "unlinked") is None
        assert queries.public_profile_row(db, "world-a", "wc-a")[1] is public[0][1]
        assert len(calls) == 4
        db.get(models.WorldMembership, "membership-owner-a").status = "left"
        db.flush()
        calls.clear()
        assert queries.public_profile_rows(db, "world-a") == []
        assert len(calls) == 1
