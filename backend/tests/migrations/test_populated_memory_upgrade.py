"""Preserve populated Memory state across supported upgrades and rejected changes."""
from datetime import UTC, datetime, timedelta
import hashlib
import json
import sqlite3

import pytest
from sqlalchemy import URL, create_engine, event
from sqlalchemy.orm import Session

from memory.test_p8_l_o_memory_consolidation import _seed_world
from app.domains.memory.models.items import MemoryScopeSettingModel, MemoryItem, MemoryItemEvidence
from app.domains.memory.models.batch import MEMORY_BATCH_TABLES
from app.runtime.migrations.embedded_data import EmbeddedDataUpgradeCoordinator
from app.runtime.migrations.embedded_sqlite import SqliteCanonicalUpgradeError
from app.runtime.migrations.generation import EmbeddedGenerationController
from app.runtime.migrations.sqlite_versions import registry
from app.runtime.persistence.runtime_data_path import StaticRuntimeDataPath
from app.runtime.persistence.sqlite_codecs import encode_utc_timestamp
from app.runtime.persistence.sqlite_schema import (
    SCHEMA_VERSION_TABLE, build_sqlite_v8_metadata, create_schema_version_table,
    sqlite_schema_digest,
)

GENERATION = 'er6-preview-v2-schema-v3-schema-v4-schema-v6-schema-v7-schema-v8'
NOW = datetime(2026, 9, 7, 0, 0, tzinfo=UTC)
TABLES = ('users','characters','worlds','world_memberships','world_characters',
          'memory_scope_settings','memory_items','memory_item_evidence')


def _rows(path):
    with sqlite3.connect(f'{path.as_uri()}?mode=ro', uri=True) as connection:
        return {name: connection.execute(f'SELECT * FROM "{name}" ORDER BY id').fetchall()
                for name in TABLES}


def _seed(root):
    source = root / 'canonical/generations' / GENERATION / 'angmoo.sqlite3'
    source.parent.mkdir(parents=True)
    manifest = registry.load_sqlite_manifest(8)
    engine = create_engine(URL.create('sqlite+pysqlite', database=str(source)))
    @event.listens_for(engine, 'connect')
    def foreign_keys(connection, _):
        connection.execute('PRAGMA foreign_keys=ON')
    try:
        with engine.begin() as connection:
            create_schema_version_table(connection)
            build_sqlite_v8_metadata().create_all(connection)
            connection.exec_driver_sql(
                f'INSERT INTO {SCHEMA_VERSION_TABLE} '
                '(singleton_key,schema_version,source_revision,source_migration_count,schema_digest,created_at) '
                'VALUES (?,?,?,?,?,?)',
                (1,8,manifest.source_revision,manifest.source_migration_count,
                 sqlite_schema_digest(connection),encode_utc_timestamp(NOW)),
            )
        with Session(engine) as session:
            scope = _seed_world(session)
            session.add_all([
                MemoryScopeSettingModel(id='scope-on',owner_id=scope.owner_id,world_id=scope.world_id,
                    subject_world_character_id=scope.subject_world_character_id,enabled=True,
                    retention_days=180,provider_mode='none',version=4),
                MemoryScopeSettingModel(id='scope-off',owner_id=scope.owner_id,world_id=scope.world_id,
                    subject_world_character_id='consolidation-counterpart',enabled=False,
                    retention_days=45,provider_mode='none',version=2),
            ])
            common = dict(owner_id=scope.owner_id,world_id=scope.world_id,
                subject_world_character_id=scope.subject_world_character_id,
                counterpart_world_character_id='consolidation-counterpart',
                memory_kind='AUTOBIOGRAPHICAL_EVENT',confidence=0.8,salience=0.6,
                valid_from=NOW,valid_until=NOW+timedelta(days=180))
            session.add(MemoryItem(id='memory-current',summary='합성 기억',pinned_at=NOW,version=3,**common))
            session.flush()
            session.add_all([
                MemoryItem(id='memory-old',summary='정정 전 기억',status='superseded',
                    superseded_by_id='memory-current',version=2,**common),
                MemoryItem(id='memory-deleted',summary='삭제된 합성 기억',status='deleted',
                    deleted_at=NOW,version=2,**common),
                MemoryItemEvidence(id='evidence-current',memory_item_id='memory-current',
                    source_type='POST',source_id='synthetic-source',source_world_id=scope.world_id,
                    actor_world_character_id=scope.subject_world_character_id,source_created_at=NOW,
                    source_digest=hashlib.sha256(b'synthetic-source').hexdigest()),
            ])
            session.commit()
    finally:
        engine.dispose()
    EmbeddedGenerationController(root/'canonical',artifact_relative_path='angmoo.sqlite3').promote(
        f'generations/{GENERATION}',manifest_sha256=manifest.manifest_sha256,data_version=8)
    return source


@pytest.mark.parametrize('undeclared_mutation',[False,True])
def test_populated_v8_memory_upgrade_preserves_state_or_rejects_unowned_change(tmp_path,monkeypatch,undeclared_mutation):
    root = tmp_path/'populated-memory'
    source = _seed(root)
    before = _rows(source)
    source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    marker = root/'canonical/current-generation.json'
    marker_before = marker.read_bytes()
    assert len(GENERATION) == 64
    assert len(before['memory_scope_settings']) == 2
    assert len(before['memory_items']) == 3
    assert len(before['memory_item_evidence']) == 1
    coordinator = EmbeddedDataUpgradeCoordinator(StaticRuntimeDataPath(root),fallback_generation=GENERATION)
    if undeclared_mutation:
        original = registry.MIGRATIONS[8]
        def mutate(connection):
            original(connection)
            connection.exec_driver_sql("UPDATE memory_items SET summary='unexpected' WHERE id='memory-current'")
        monkeypatch.setitem(registry.MIGRATIONS,8,mutate)
        with pytest.raises(SqliteCanonicalUpgradeError,match='sqlite_migration_identity_changed'):
            coordinator.upgrade()
        assert marker.read_bytes() == marker_before
        assert not (root/'canonical/previous-generation.json').exists()
        assert not list((root/'canonical/generations').glob('.*.tmp-*'))
    else:
        result = coordinator.upgrade()
        assert result.canonical.migrated is True
        assert result.canonical.source_version == 8
        assert result.canonical.target_version == 9
        current = json.loads(marker.read_text(encoding='utf-8'))
        target = root/'canonical'/current['relative_path']/'angmoo.sqlite3'
        assert _rows(target) == before
        with sqlite3.connect(target) as connection:
            assert connection.execute('PRAGMA foreign_key_check').fetchall() == []
            for name in MEMORY_BATCH_TABLES:
                assert connection.execute(f'SELECT count(*) FROM "{name}"').fetchone()[0] == 0
        repeated = coordinator.upgrade()
        assert repeated.canonical.migrated is False
        assert repeated.canonical.generation == result.canonical.generation
        assert _rows(target) == before
        previous = json.loads((root/'canonical/previous-generation.json').read_text(encoding='utf-8'))
        assert previous['data_version'] == 8
        assert previous['generation'] == GENERATION
    assert hashlib.sha256(source.read_bytes()).hexdigest() == source_hash
    assert _rows(source) == before
