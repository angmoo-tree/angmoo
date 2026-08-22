from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app import models
from app.core import security
from app.core.db import Base, engine
from app.integrations.ladybug_projection import LadybugRelationshipProjection
from app.runtime.desktop_sidecar import _selected_generation
from app.runtime.migrations.alembic_source import AlembicMigrationSource
from app.runtime.migrations.postgres_to_sqlite import (
    PostgresToSqliteOfflineDryRun,
)
from app.runtime.migrations.release_candidate import (
    SYNTHETIC_FIXTURE_MARKER,
    RuntimeGenerationController,
    SyntheticReleaseCandidateBackup,
)
from app.runtime.persistence.runtime_data_path import StaticRuntimeDataPath
from app.services.graph_projection_replay import (
    GraphProjectionReplayService,
    create_replay_run,
)
from p7_graph_support import seed_projection_fixture

BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = BACKEND_ROOT.parent


pytestmark = pytest.mark.skipif(
    os.getenv("ER6_POSTGRES_MIGRATION") != "1",
    reason="set ER6_POSTGRES_MIGRATION=1 on an isolated PostgreSQL fixture",
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _synthetic_marker(root: Path) -> None:
    (root / SYNTHETIC_FIXTURE_MARKER).write_text(
        json.dumps(
            {
                "schema_version": 1,
                "fixture_id": "er6-postgres-installer-roundtrip",
                "synthetic_fixture": True,
                "contains_real_credentials": False,
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )


def test_postgres_to_installed_runtime_roundtrip(
    tmp_path: Path,
) -> None:
    assert engine.dialect.name == "postgresql"
    with engine.connect() as connection:
        assert connection.scalar(select(models.User.id).limit(1)) is None

    scope = security.SecretScope(
        owner_id="p7-owner-er6-installer",
        character_id="p7-actor-er6-installer",
        provider="gemini",
        purpose="agent",
    )
    envelope = security.encrypt_secret("synthetic-er6-api-key", scope=scope)
    with Session(engine, expire_on_commit=False) as source_session:
        fixture = seed_projection_fixture(source_session, suffix="er6-installer")
        source_session.add(
            models.LlmCredential(
                id="credential-er6-installer",
                owner_id=fixture.owner.id,
                character_id=fixture.actor.id,
                provider="gemini",
                purpose="agent",
                model="gemini-er6-fixture",
                auth_profile_id="er6-installer-fixture",
                label="Synthetic ER6 key",
                encrypted_api_key=envelope,
                key_fingerprint="synthetic-er6",
                enabled=True,
            )
        )
        source_session.commit()
        world_id = fixture.world.id

    runtime_root = tmp_path / "한글 사용자" / "Angmoo RC data"
    generation = "er6-postgres-roundtrip"
    report = PostgresToSqliteOfflineDryRun(
        source_engine=engine,
        source_metadata=Base.metadata,
        data_paths=StaticRuntimeDataPath(runtime_root),
        migration_source=AlembicMigrationSource(
            BACKEND_ROOT / "app" / "alembic" / "versions"
        ),
        conversion_inventory_path=(
            REPOSITORY_ROOT
            / "docs"
            / "architecture"
            / "migration-conversion-inventory.json"
        ),
        generation=generation,
        app_version="0.4.0-1",
    ).dry_run()
    assert report.source_read_only is True
    assert report.production_switched is False
    assert report.foreign_key_violation_count == 0
    assert report.integrity_check == "ok"

    target_engine = create_engine(
        "sqlite+pysqlite:///" + Path(report.target_database_path).as_posix(),
        connect_args={"check_same_thread": False},
    )
    session_factory = sessionmaker(
        bind=target_engine,
        expire_on_commit=False,
        autoflush=False,
    )
    with session_factory() as target_session:
        restored_envelope = target_session.scalar(
            select(models.LlmCredential.encrypted_api_key).where(
                models.LlmCredential.id == "credential-er6-installer"
            )
        )
        assert restored_envelope == envelope
        replay_run = create_replay_run(
            target_session,
            world_id=world_id,
            mode="world_rebuild",
            source_event_id=None,
            requested_by="er6-installer-roundtrip",
            reason_code="migration_rebuild",
        )
        target_session.commit()
        replay_run_id = replay_run.id

    graph_root = runtime_root / "graph" / "ladybug"
    with LadybugRelationshipProjection(database_root=graph_root) as projection:
        completed = GraphProjectionReplayService(
            session_factory=session_factory,
            store=projection,
            worker_id="er6-installer-roundtrip",
        ).execute(replay_run_id)
        assert completed.status == "succeeded"
        digest = projection.world_digest(world_id)
        assert digest["relationships"]
        assert digest["evidence"]
    target_engine.dispose()

    secret_path = runtime_root / "secrets" / "app-secret"
    secret_path.parent.mkdir(parents=True)
    secret_path.write_text(
        security.settings.APP_SECRET.get_secret_value() + "\n",
        encoding="utf-8",
    )
    _synthetic_marker(runtime_root)
    controller = RuntimeGenerationController(StaticRuntimeDataPath(runtime_root))
    controller.promote(
        generation,
        content_sha256=report.manifest.content_sha256,
    )
    assert _selected_generation(runtime_root) == generation

    backup_root = tmp_path / "ER6 synthetic backup"
    restored_root = tmp_path / "ER6 restored data"
    backup = SyntheticReleaseCandidateBackup(
        data_paths=StaticRuntimeDataPath(runtime_root),
        app_version="0.4.0-1",
    )
    created = backup.create(backup_root)
    restored = backup.restore(backup_root, restored_root)
    assert created.manifest.content_sha256 == restored.manifest.content_sha256
    restored_database = (
        restored_root
        / "canonical"
        / "generations"
        / generation
        / "angmoo.sqlite3"
    )
    assert _sha256(restored_database) == _sha256(
        Path(report.target_database_path)
    )
    restored_engine = create_engine(
        "sqlite+pysqlite:///" + restored_database.as_posix()
    )
    with Session(restored_engine) as restored_session:
        restored_envelope = restored_session.scalar(
            select(models.LlmCredential.encrypted_api_key).where(
                models.LlmCredential.id == "credential-er6-installer"
            )
        )
    restored_engine.dispose()
    assert restored_envelope is not None
    assert security.decrypt_secret(restored_envelope, scope=scope) == (
        "synthetic-er6-api-key"
    )
