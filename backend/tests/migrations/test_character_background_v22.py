"""A populated v21 database gains two empty columns without rewriting persona."""

from datetime import UTC, datetime, timedelta
from contextlib import closing
import sqlite3

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from model_fixture_support import models as registered_models
from app.domains.characters import models as character_models
from app.runtime.migrations.sqlite_versions import character_background_v22
from app.runtime.migrations.sqlite_versions.registry import load_sqlite_manifest
from app.runtime.persistence.sqlite_schema import (
    build_sqlite_v21_metadata, create_schema_version_table, sqlite_schema_contract_digest,
)
from app.runtime.persistence.model_registration import register_models
from historical_schema_fixture import populate_frozen_schema


def test_populated_v21_upgrade_keeps_original_description_and_draft(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'v21.sqlite3'}")
    with engine.begin() as connection:
        build_sqlite_v21_metadata().create_all(connection)
        create_schema_version_table(connection)
        assert sqlite_schema_contract_digest(connection) == load_sqlite_manifest(21).schema_digest
    def seed(db):
        db.add(registered_models.User(id="owner", display_name="Owner"))
        db.add(character_models.Character(id="bird", owner_id="owner", name="Bird",
            handle="bird", worldview="원래 설명", personality="원래 성격", persona_summary="원래 요약"))
        db.add(character_models.AgentCreationDraft(id="draft", user_id="owner",
            model="gemini-3.1-flash-lite", name="Draft", worldview="초안 설명",
            personality="", expires_at=datetime.now(UTC) + timedelta(days=1)))
    populate_frozen_schema(engine, build_sqlite_v21_metadata(), seed)
    with engine.begin() as connection:
        assert sqlite_schema_contract_digest(connection) == load_sqlite_manifest(21).schema_digest
        before = character_background_v22.capture_delta(connection)
        character_background_v22.upgrade(connection)
        character_background_v22.verify_delta(connection, before)
        assert sqlite_schema_contract_digest(connection) == load_sqlite_manifest(22).schema_digest
        assert connection.execute(text(
            "SELECT worldview, personality, persona_summary, character_background "
            "FROM characters WHERE id='bird'"
        )).one() == ("원래 설명", "원래 성격", "원래 요약", "")
        assert connection.execute(text(
            "SELECT worldview, personality, character_background FROM agent_creation_drafts WHERE id='draft'"
        )).one() == ("초안 설명", "", "")
    engine.dispose()


def test_current_sqlite_backup_restores_description_and_separate_background(tmp_path):
    source_path = tmp_path / "source.sqlite3"
    backup_path = tmp_path / "backup.sqlite3"
    engine = create_engine(f"sqlite:///{source_path}")
    register_models().create_all(engine)
    with Session(engine) as db:
        db.add(registered_models.User(id="owner", display_name="Owner"))
        db.add(character_models.Character(id="bird", owner_id="owner", name="Bird",
            handle="bird", worldview="새 설명", character_background="분리된 과거",
            personality="", persona_summary="새 설명"))
        db.add(character_models.AgentCreationDraft(id="draft", user_id="owner",
            model="gemini-3.1-flash-lite", name="Draft", worldview="초안 설명",
            character_background="초안의 별도 배경", expires_at=datetime.now(UTC) + timedelta(days=1)))
        db.commit()
    engine.dispose()

    with closing(sqlite3.connect(source_path)) as source, closing(sqlite3.connect(backup_path)) as target:
        source.backup(target)

    restored = create_engine(f"sqlite:///{backup_path}")
    with restored.connect() as connection:
        assert connection.execute(text(
            "SELECT worldview, character_background FROM characters WHERE id='bird'"
        )).one() == ("새 설명", "분리된 과거")
        assert connection.execute(text(
            "SELECT worldview, character_background FROM agent_creation_drafts WHERE id='draft'"
        )).one() == ("초안 설명", "초안의 별도 배경")
    restored.dispose()
