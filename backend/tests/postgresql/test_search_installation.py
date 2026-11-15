"""Fresh and pre-fix PG homes prepare search without elevating the serving role."""
import json
import os
import uuid

import psycopg
from psycopg import sql
import pytest
from sqlalchemy import text
from sqlalchemy.engine import make_url

from app.database import create_database_engine
from app.runtime.postgresql_installation import initialize, private_file
from app.runtime.postgresql_search_installation import prepare_search, ready
from app.runtime.memory.postgresql_recall import PostgresMemoryRecallIndex
from app.runtime.memory.sqlite_fts5_recall import MemoryRecallIndexSettings


def test_fresh_search_and_old_missing_schema_repair_preserve_runtime_boundary(tmp_path):
    admin = os.environ.get("ANGMOO_TEST_ADMIN_DSN")
    if not admin:
        pytest.skip("explicit disposable PostgreSQL test administrator required")
    url = make_url(admin)
    assert url.host in {"127.0.0.1", "localhost"}
    name = "angmoo_test_search_" + uuid.uuid4().hex[:12]
    role = "runtime_" + uuid.uuid4().hex[:12]
    identifier = "angmoo-" + uuid.uuid4().hex
    owner = url.set(database=name).render_as_string(hide_password=False)
    runtime = url.set(database=name, username=role, password=uuid.uuid4().hex * 2).render_as_string(hide_password=False)
    connect = lambda dsn: psycopg.connect(dsn.replace("postgresql+psycopg://", "postgresql://"), autocommit=True)
    with connect(admin) as db:
        db.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    root = tmp_path / "data"
    owner_file = tmp_path / "private" / "owner-dsn"
    owner_engine = runtime_engine = None
    try:
        private_file(owner_file, (owner + "\n").encode())
        initialize(root, owner, runtime, identifier)
        owner_engine = create_database_engine(owner)
        runtime_engine = create_database_engine(runtime)
        with runtime_engine.begin() as db:
            assert ready(db)
            assert not db.execute(text("SELECT has_schema_privilege(current_user,'public','CREATE')")).scalar_one()
            db.execute(text("INSERT INTO site_operation_settings(key,value) VALUES('search-repair-fixture','바질 🪴')"))
        index = PostgresMemoryRecallIndex(runtime_engine, settings=MemoryRecallIndexSettings.for_representation("episode_v1"))
        assert index.open().healthy
        # Reproduce the released fresh-install omission, not a failed AI task.
        with owner_engine.begin() as db:
            for table in ("pg_recall_documents", "pg_search_generations", "pg_search_progress", "pg_search_state"):
                db.execute(text("DROP TABLE " + table))
        with runtime_engine.connect() as db:
            assert not ready(db)
        marker = root / "runtime/postgresql-runtime.json"
        original_marker = marker.read_bytes()
        value = json.loads(original_marker)
        value["installation_id"] = "angmoo-" + uuid.uuid4().hex
        marker.write_text(json.dumps(value))
        with pytest.raises(ValueError, match="identity_mismatch"):
            prepare_search(root, owner_file)
        marker.write_bytes(original_marker)
        assert prepare_search(root, owner_file) == {"state": "search_prepared"}
        assert index.open().healthy
        with runtime_engine.connect() as db:
            assert db.execute(text("SELECT value FROM site_operation_settings WHERE key='search-repair-fixture'")).scalar_one() == "바질 🪴"
            assert not db.execute(text("SELECT has_schema_privilege(current_user,'public','CREATE')")).scalar_one()
        # A healthy migrated/custom home need not mount administrator secrets.
        assert prepare_search(root, tmp_path / "absent-owner") == {"state": "search_ready"}
        assert marker.read_bytes() == original_marker
    finally:
        for engine in (owner_engine, runtime_engine):
            if engine is not None:
                engine.dispose()
        with connect(admin) as db:
            db.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name)))
            db.execute(sql.SQL("DROP ROLE IF EXISTS {}").format(sql.Identifier(role)))
