"""Privacy erasure preserves live World copies and shares the parent UoW."""
from copy import deepcopy
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domains.characters.models_import import CharacterImportOrigin, CharacterImportSnapshot
from app.domains.routines.models.resident import AgentSlot
from app.domains.world_characters.configuration_models import WorldCharacterConfiguration
from app.runtime.creator_privacy import delete_creator_private_data
from world_configuration_fixture_support import fixture_owner, seed_configuration_fixture


def test_one_instance_erasure_preserves_the_other_world_and_immutable_basis(tmp_path):
    engine = seed_configuration_fixture(tmp_path / "single.sqlite3")
    with Session(engine) as db:
        other = db.get(WorldCharacterConfiguration, "config-role-b")
        basis_id = other.snapshot_id
        before = (deepcopy(other.profile), deepcopy(other.settings), deepcopy(db.get(CharacterImportSnapshot, basis_id).payload))
        delete_creator_private_data(db, character_ids=["config-actor-a"])
        db.commit()
        assert db.get(WorldCharacterConfiguration, "config-role-a") is None
        assert db.get(CharacterImportOrigin, "config-actor-a") is None
        assert db.get(CharacterImportOrigin, "config-actor-b").snapshot_id == basis_id
        assert (other.profile, other.settings, db.get(CharacterImportSnapshot, basis_id).payload) == before
        assert db.connection().exec_driver_sql("PRAGMA foreign_key_check").all() == []
    engine.dispose()


def test_last_instance_erasure_removes_the_unreferenced_private_basis(tmp_path):
    engine = seed_configuration_fixture(tmp_path / "last.sqlite3")
    with Session(engine) as db:
        basis_id = db.get(CharacterImportOrigin, "config-actor-a").snapshot_id
        retained_origins = {
            row.character_id: row.snapshot_id
            for row in db.scalars(select(CharacterImportOrigin))
            if row.character_id not in {"config-actor-a", "config-actor-b"}
        }
        retained_roles = {
            row.world_character_id: row.snapshot_id
            for row in db.scalars(select(WorldCharacterConfiguration))
            if row.world_character_id not in {"config-role-a", "config-role-b"}
        }
        delete_creator_private_data(db, character_ids=["config-actor-a", "config-actor-b"])
        db.commit()
        assert db.get(CharacterImportSnapshot, basis_id) is None
        assert {row.character_id: row.snapshot_id for row in db.scalars(select(CharacterImportOrigin))} == retained_origins
        assert {row.world_character_id: row.snapshot_id for row in db.scalars(select(WorldCharacterConfiguration))} == retained_roles
        assert db.connection().exec_driver_sql("PRAGMA foreign_key_check").all() == []
    engine.dispose()


def test_import_erasure_rolls_back_with_the_parent_deletion_transaction(tmp_path):
    engine = seed_configuration_fixture(tmp_path / "rollback.sqlite3")
    with Session(engine) as db:
        basis_id = db.get(CharacterImportOrigin, "config-actor-a").snapshot_id
        before = deepcopy(db.get(CharacterImportSnapshot, basis_id).payload)
        delete_creator_private_data(db, character_ids=["config-actor-a", "config-actor-b"])
        db.rollback()
        assert db.get(CharacterImportSnapshot, basis_id).payload == before
        assert db.get(CharacterImportOrigin, "config-actor-a").snapshot_id == basis_id
        assert db.get(WorldCharacterConfiguration, "config-role-b").snapshot_id == basis_id
    engine.dispose()


def test_account_erasure_clears_import_state_and_private_slot_input(tmp_path):
    from app.runtime.account_deletion import delete_current_user_account
    engine = seed_configuration_fixture(tmp_path / "account.sqlite3")
    with Session(engine) as db:
        owner = fixture_owner(db)
        db.add(AgentSlot(agent_id="privacy-slot", status="idle", assigned_user_id=owner.id,
            assigned_character_id="config-actor-a", admission_metadata={"input_snapshot": {"private_persona": "synthetic"}}))
        db.commit()
        delete_current_user_account(db, owner)
        assert owner.deleted_at is not None
        assert db.get(AgentSlot, "privacy-slot").admission_metadata is None
        assert list(db.scalars(select(CharacterImportSnapshot))) == []
        assert list(db.scalars(select(CharacterImportOrigin))) == []
        assert list(db.scalars(select(WorldCharacterConfiguration))) == []
        assert db.connection().exec_driver_sql("PRAGMA foreign_key_check").all() == []
    engine.dispose()
