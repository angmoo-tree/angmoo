from sqlalchemy.orm import Session

from app import models
from app.runtime.worlds.foundation import ensure_angmoo_global_foundation
from tests.worlds.test_foundation import _character, _engine, _user


def test_foundation_flushes_within_the_callers_transaction_without_committing() -> None:
    with Session(_engine()) as db:
        owner = _user("foundation-owner")
        character = _character("foundation-character", owner.id)
        db.add_all([owner, character])
        db.commit()

        report = ensure_angmoo_global_foundation(db)
        assert report.seeded is True
        assert report.membership_count == 1
        assert report.world_character_count == 1
        world = db.get(models.World, report.world_id)
        assert world is not None
        assert db.get(models.World, report.world_id) is world
        assert db.query(models.CharacterActiveWorld).count() == 0

        db.rollback()
        assert db.query(models.World).count() == 0
        assert db.query(models.WorldMembership).count() == 0
        assert db.query(models.WorldCharacter).count() == 0
        assert db.query(models.User).count() == 1
        assert db.query(models.Character).count() == 1

        repeated = ensure_angmoo_global_foundation(db)
        assert repeated == report
