"""Frozen v27 transition with actual file DBs, rollback/resume and source races."""
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
import json
from threading import Event
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from app.domains.characters.models import AgentCreationDraft, CharacterRegistrationReceipt, Character
from app.domains.characters.models_import import CharacterImportSnapshot, CharacterImportOrigin
from app.domains.world_characters.configuration_models import WorldCharacterConfiguration
from app.domains.world_characters.models import WorldCharacter
from app.domains.world_characters.service.configuration import effective_configuration
from app.domains.characters.service.import_snapshots import get_import_snapshot
from app.runtime.migrations.sqlite_versions import world_configuration_v28 as v28
from app.runtime.migrations.sqlite_versions.registry import load_sqlite_manifest
from app.runtime.persistence.sqlite_schema import build_sqlite_v27_metadata, sqlite_schema_contract_digest
from world_configuration_fixture_support import seed_configuration_fixture


def transition(engine):
    with engine.begin() as connection:
        before = v28.capture_delta(connection)
        v28.upgrade(connection)
        v28.verify_delta(connection, before)
        assert sqlite_schema_contract_digest(connection) == load_sqlite_manifest(28).schema_digest
        assert not connection.exec_driver_sql("PRAGMA foreign_key_check").all()


def test_t99_t111_three_origin_cases_and_existing_world_saved_state_preserved(tmp_path):
    engine = seed_configuration_fixture(tmp_path / "three-cases.sqlite3", legacy=True)
    with Session(engine) as db:
        draft = AgentCreationDraft(id="proven-creation", user_id="fixture-owner", model="gemini-3.1-flash-lite",
            status="completed", source_kind="direct", contract_version=2, revision=7,
            name="Initial Bram", handle="initial_bram", one_liner="Original verified intro", personality="Verified first persona",
            worldview="Verified first world", expires_at=datetime.now(UTC) + timedelta(days=10))
        db.add(draft)
        db.flush()
        db.add(CharacterRegistrationReceipt(draft_id=draft.id, character_id="config-actor-a",
            world_character_id="config-role-a", request_digest="a" * 64))
        a, b = (db.get(WorldCharacter, "config-role-" + suffix) for suffix in ("a", "b"))
        a.local_profile = {"display_name": "Preserved A", "intro": "", "avatar_url": None}
        a.autonomous_enabled, a.version = True, 9
        b.local_profile = {"intro": "Saved B"}
        b.version = 4
        db.commit()
    legacy = build_sqlite_v27_metadata()
    now = datetime.now(UTC)
    with engine.begin() as connection:
        connection.execute(legacy.tables["agent_runs"].insert().values(id="old-admitted-run", user_id="fixture-owner",
            character_id="config-actor-a", agent_id="old-slot", session_key="old-session", status="running",
            gateway_result={"accepted": {"persona": "Original admitted input"}}))
        connection.execute(legacy.tables["agent_slots"].insert().values(agent_id="old-slot", assigned_user_id="fixture-owner",
            assigned_character_id="config-actor-a", assigned_credential_id="config-credential-a", status="running",
            lease_expires_at=now + timedelta(minutes=5), locked_by_run_id="old-admitted-run"))
    transition(engine)
    with Session(engine) as db:
        restored, creation = get_import_snapshot(db, "config-actor-a")
        legacy_origin, legacy_basis = get_import_snapshot(db, "config-actor-b")
        assert restored.kind == "restored_initial" and restored.source_revision == "registration:7"
        assert restored.provenance == "completed_registration:proven-creation"
        assert creation.profile.display_name == "Initial Bram" and creation.settings.personality == "Verified first persona"
        assert legacy_origin.kind == "legacy_transition" and legacy_origin.provenance == "v28:confirmed_source_configuration"
        assert legacy_origin.captured_at and legacy_origin.source_revision.startswith("transition:")
        assert legacy_basis.settings.personality == "Original persona"
        a, b = (effective_configuration(db, world_character_id="config-role-" + suffix) for suffix in ("a", "b"))
        assert a.profile.display_name == "Preserved A" and a.profile.intro == "" and a.profile.avatar_url is None
        assert a.revision == 9 and a.autonomous_enabled and a.settings.personality == "Original persona"
        assert b.profile.intro == "Saved B" and b.revision == 4 and not b.autonomous_enabled
        assert db.execute(text("SELECT input_snapshot FROM agent_runs WHERE id='old-admitted-run'")).scalar() is None
        assert db.execute(text("SELECT admission_metadata FROM agent_slots WHERE agent_id='old-slot'")).scalar() is None
        assert db.execute(text("SELECT locked_by_run_id FROM agent_slots WHERE agent_id='old-slot'")).scalar() == "old-admitted-run"
        assert "Original admitted input" in db.execute(text("SELECT gateway_result FROM agent_runs WHERE id='old-admitted-run'")).scalar()
    engine.dispose()


def test_t112_t114_t115_reentry_never_recaptures_or_merges_worlds(tmp_path):
    engine = seed_configuration_fixture(tmp_path / "reentry.sqlite3", legacy=True)
    transition(engine)
    with Session(engine) as db:
        first = {row.source_character_id: (row.id, row.digest, row.payload, row.captured_at) for row in db.query(CharacterImportSnapshot)}
        assert first["config-actor-a"][0] != first["config-actor-b"][0]
        source = db.get(Character, "config-actor-a")
        source.personality = "Changed after transition"
        source.name = "Same name does not merge basis"
        role = db.get(WorldCharacter, "config-role-a")
        role.version, role.autonomous_enabled = 12, True
        stored = db.get(WorldCharacterConfiguration, role.id)
        stored.settings = {**stored.settings, "personality": "World A changed after transition"}
        db.commit()
    with engine.begin() as connection:
        v28.backfill(connection)
        v28.backfill(connection)
    with Session(engine) as db:
        second = {row.source_character_id: (row.id, row.digest, row.payload, row.captured_at) for row in db.query(CharacterImportSnapshot)}
        assert first == second
        a = effective_configuration(db, world_character_id="config-role-a")
        assert a.settings.personality == "World A changed after transition" and a.autonomous_enabled and a.revision == 12
        assert get_import_snapshot(db, "config-actor-a")[1].settings.personality == "Original persona"
    engine.dispose()


def test_t115_transition_transaction_rollback_then_resume(tmp_path):
    engine = seed_configuration_fixture(tmp_path / "rollback.sqlite3", legacy=True)
    # Explicit SQLite transaction includes DDL, as required by the migration UoW.
    with engine.connect() as connection:
        connection.exec_driver_sql("BEGIN IMMEDIATE")
        v28.upgrade(connection)
        assert connection.exec_driver_sql("SELECT count(*) FROM character_import_snapshots").scalar_one() == 2
        connection.rollback()
        assert connection.exec_driver_sql("SELECT count(*) FROM sqlite_master WHERE name='character_import_snapshots'").scalar_one() == 0
        assert "input_snapshot" not in [row[1] for row in connection.exec_driver_sql("PRAGMA table_info(agent_runs)")]
    transition(engine)
    engine.dispose()


def test_t115_source_edit_waits_for_one_confirmed_transition_revision(tmp_path):
    engine = seed_configuration_fixture(tmp_path / "race.sqlite3", legacy=True)
    frozen, editing = Event(), Event()
    def migrate():
        with engine.connect() as connection:
            connection.exec_driver_sql("BEGIN IMMEDIATE")
            v28.upgrade(connection)
            frozen.set()
            assert editing.wait(10)
            connection.commit()
    def edit():
        assert frozen.wait(10)
        with engine.connect() as connection:
            editing.set()
            connection.execute(text("UPDATE characters SET personality='Late source edit' WHERE id='config-actor-a'"))
            connection.commit()
    with ThreadPoolExecutor(max_workers=2) as pool:
        a, b = pool.submit(migrate), pool.submit(edit)
        a.result(20)
        b.result(20)
    with Session(engine) as db:
        assert db.get(Character, "config-actor-a").personality == "Late source edit"
        assert get_import_snapshot(db, "config-actor-a")[1].settings.personality == "Original persona"
        assert effective_configuration(db, world_character_id="config-role-a").settings.personality == "Original persona"
    engine.dispose()


def test_t116_credential_url_is_not_copied_into_new_origin_or_config(tmp_path):
    engine = seed_configuration_fixture(tmp_path / "unsafe-media.sqlite3", legacy=True)
    with Session(engine) as db:
        db.get(Character, "config-actor-a").avatar_url = "https://example.test/image.png?token=synthetic-secret"
        db.commit()
    transition(engine)
    with Session(engine) as db:
        row, basis = get_import_snapshot(db, "config-actor-a")
        assert basis.profile.avatar_url is None
        assert "synthetic-secret" not in json.dumps(row.payload)
        assert "synthetic-secret" in db.get(Character, "config-actor-a").avatar_url
    engine.dispose()
