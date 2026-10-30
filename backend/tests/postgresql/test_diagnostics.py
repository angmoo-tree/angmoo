import importlib.util,os
from pathlib import Path
import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session
from postgresql.test_canonical_contracts import engine
from app.runtime.diagnostics.postgresql_snapshot import memory_snapshot,scheduler_snapshot
from app.config import Settings
from app.domains.runtime.constants import RuntimeDiagnosticCode
from app.domains.runtime.contracts.status import RuntimeComponentState
from app.runtime.diagnostics.status_composition import create_runtime_status_reader
from app.runtime.persistence.postgresql_schema import VERSION


@pytest.mark.parametrize('actual_version', [VERSION - 1, VERSION, VERSION + 1])
def test_pg_home_diagnostics_accept_only_shipped_schema_version(engine, actual_version):
    # Roll back the marker mutation: this probe must not change the shared
    # experiment schema, including when an assertion fails.
    with engine.connect() as connection:
        transaction = connection.begin()
        try:
            connection.execute(
                text('UPDATE angmoo_postgresql_schema_version SET version=:version'),
                {'version': actual_version},
            )
            with Session(bind=connection) as session:
                status = create_runtime_status_reader(
                    session, config=Settings(DATABASE_URL=os.environ['ANGMOO_EXPERIMENT_DATABASE_URL']),
                )._migration_status()
            assert status.current_revision == f'postgresql-v{actual_version}'
            assert status.head_revision == f'postgresql-v{VERSION}'
            if actual_version == VERSION:
                assert status.state is RuntimeComponentState.READY
                assert status.reason_code is None
            else:
                assert status.state is RuntimeComponentState.DEGRADED
                assert status.reason_code is RuntimeDiagnosticCode.MIGRATION_NOT_CURRENT
        finally:
            transaction.rollback()


def test_pg_diagnostic_snapshot_uses_one_database_and_no_sqlite(engine,tmp_path,monkeypatch):
    from app.runtime.memory.postgresql_vector import PostgresMemoryVectorIndex
    from app.runtime.memory.postgresql_generations import initialize_state
    from app.runtime.memory.postgresql_recall import PostgresMemoryRecallIndex
    from app.runtime.search.postgresql_fts import PostgresFtsSearchIndex
    PostgresMemoryVectorIndex(engine).open()
    initialize_state(engine,budget_state='fresh')
    PostgresMemoryRecallIndex(engine).open();PostgresFtsSearchIndex(engine).open()
    import sqlite3
    def denied(*a,**k):raise AssertionError('diagnostic opened SQLite')
    monkeypatch.setattr(sqlite3,'connect',denied)
    with engine.connect() as c:
        world,actors=c.execute(text('SELECT world_id,array_agg(id) FROM world_characters GROUP BY world_id LIMIT 1')).one()
    manifest={'world_id':world,'actor_ids':actors}
    snapshot=memory_snapshot(tmp_path,manifest,dsn=os.environ['ANGMOO_EXPERIMENT_DATABASE_URL'])
    assert snapshot['status']=='ok' and snapshot['atomic_across_databases'] is True
    assert scheduler_snapshot(tmp_path,manifest,dsn=os.environ['ANGMOO_EXPERIMENT_DATABASE_URL'])['scheduler_snapshot']=='ready'


def test_restore_definition_normalization_only_accepts_equivalent_constant_casts():
    path=Path(__file__).parents[3]/'scripts/postgresql_experiment/pg_fingerprint.py'
    spec=importlib.util.spec_from_file_location('pg_fingerprint',path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    before="CHECK (((status)::text = ANY ((ARRAY['pending'::character varying, 'running'::character varying])::text[])))"
    after="CHECK (((status)::text = ANY (ARRAY[('pending'::character varying)::text, ('running'::character varying)::text])))"
    assert module.normalize_definition(before)==module.normalize_definition(after)
    assert module.normalize_definition(before)!=module.normalize_definition(after.replace('running','failed'))
    assert module.normalize_definition('CHECK (balance > 0)')!='CHECK (balance >= 0)'
