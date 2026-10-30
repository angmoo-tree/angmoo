"""Release-source compatibility and installation isolation regressions."""
import json
from pathlib import Path
import sqlite3
import pytest
from sqlalchemy import create_engine
from app.runtime.persistence.postgresql_schema import metadata
from app.runtime.persistence.migration_source_v013 import metadata as source_metadata, additional_values,source_values
from app.runtime.postgresql_migration import inspect_source, canonical_path
from app.runtime.postgresql_installation import snapshot


def source(root):
    database=root/'canonical/generations/release-013/angmoo.sqlite3'
    database.parent.mkdir(parents=True)
    engine=create_engine('sqlite+pysqlite:///'+database.as_posix())
    metadata();source_metadata().create_all(engine);engine.dispose()
    with sqlite3.connect(database) as db:
        db.execute('CREATE TABLE angmoo_schema_version(schema_version,source_revision,source_migration_count)')
        db.execute("INSERT INTO angmoo_schema_version VALUES(41,'20261022_0118',117)")
    return database


def test_released_source_accepts_missing_postgresql_controls(tmp_path):
    source(tmp_path)
    result=inspect_source(tmp_path)
    assert result['canonical_tables']==181
    assert 'memory_maintenance_slot' not in source_metadata().tables
    assert 'maintenance' not in source_metadata().tables['relationship_review_work'].c
    assert 'maintenance' in metadata().tables['relationship_review_work'].c


def test_selected_generation_not_old_retained_database(tmp_path):
    selected=source(tmp_path)
    other=selected.parent.parent/'previous/angmoo.sqlite3'
    other.parent.mkdir();other.write_bytes(b'old generation must not be opened')
    pointer=tmp_path/'canonical/current-generation.json'
    pointer.write_text(json.dumps({'schema_version':1,'data_version':41,'generation':'release-013','relative_path':'generations/release-013'}))
    assert canonical_path(tmp_path)==selected
    assert inspect_source(tmp_path)['supported']
    pointer.write_text(json.dumps({'schema_version':1,'data_version':41,'generation':'../other','relative_path':'generations/../other'}))
    with pytest.raises(ValueError,match='pointer_invalid'):canonical_path(tmp_path)


def test_unknown_source_column_still_refused(tmp_path):
    database=source(tmp_path)
    with sqlite3.connect(database) as db:db.execute('ALTER TABLE users ADD COLUMN unknown_future_value TEXT')
    with pytest.raises(ValueError,match='columns_mismatch'):inspect_source(tmp_path)


def test_snapshot_resume_and_source_change_are_distinguished(tmp_path):
    root=tmp_path/'source';source(root)
    first=snapshot(root,tmp_path/'work','angmoo-test-release-20261030')
    assert snapshot(root,tmp_path/'work','angmoo-test-release-20261030')['migration_id']==first['migration_id']
    (root/'new-file').write_text('changed source')
    with pytest.raises(ValueError,match='resume_mismatch'):snapshot(root,tmp_path/'work','angmoo-test-release-20261030')


def test_old_failures_require_manual_recovery_without_fabricated_closure():
    failed=additional_values('relationship_review_work',{'status':'failed'})['maintenance']
    assert failed['hold']=='manual' and 'closed_at' not in failed
    assert additional_values('memory_situation_runs',{'state':'completed'})=={'maintenance':{}}


def test_old_running_lease_is_history_and_requires_explicit_recovery():
    original={'state':'running','lease_token':'old-process','lease_until':'2030-01-01','error_code':None}
    value=source_values('memory_situation_runs',original)
    assert value['state']=='error' and value['lease_token'] is None and value['lease_until'] is None
    assert additional_values('memory_situation_runs',original)['maintenance']['source_lease_token']=='old-process'
    assert original['state']=='running'
