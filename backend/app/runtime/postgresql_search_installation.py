"""Create missing derived search structures at the installation boundary.

The serving role keeps DML-only privileges. Existing search generations and
canonical data are retained; this does not rebuild or re-embed memories.
"""
import json
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.engine import make_url
from app.database import create_database_engine
from app.runtime.persistence import postgresql_identity as identity

OBJECTS = ("pg_search_state", "pg_search_progress", "pg_search_generations",
    "pg_recall_documents", "pg_recall_documents_terms", "pg_recall_documents_scope")


def ready(connection):
    return connection.execute(text("SELECT bool_and(to_regclass(name) IS NOT NULL) "
        "FROM unnest(CAST(:names AS text[])) AS names(name)"), {"names": list(OBJECTS)}).scalar_one()


def initialize_search(engine):
    from app.runtime.memory.postgresql_recall import PostgresMemoryRecallIndex
    from app.runtime.memory.sqlite_fts5_recall import MemoryRecallIndexSettings
    PostgresMemoryRecallIndex(engine, settings=MemoryRecallIndexSettings.for_representation("episode_v1")).open()


def prepare_search(data_root, owner_file):
    from app.runtime.postgresql_installation import read_dsn, provision_runtime
    root = Path(data_root)
    marker = json.loads((root / "runtime/postgresql-runtime.json").read_text(encoding="utf-8"))
    runtime_dsn = read_dsn(root / "secrets/postgresql-runtime-dsn")
    runtime_engine = create_database_engine(runtime_dsn)
    try:
        with runtime_engine.connect() as connection:
            identity.verify(connection, marker["installation_id"])
            if ready(connection):
                return {"state": "search_ready"}
    finally:
        runtime_engine.dispose()
    if not Path(owner_file).is_file():
        raise ValueError("postgresql_search_owner_credentials_required")
    owner_dsn = read_dsn(owner_file)
    runtime, owner = make_url(runtime_dsn), make_url(owner_dsn)
    if (runtime.host, runtime.port, runtime.database) != (owner.host, owner.port, owner.database) or runtime.username == owner.username:
        raise ValueError("postgresql_runtime_role_separation_required")
    owner_engine = create_database_engine(owner_dsn)
    try:
        with owner_engine.connect() as connection:
            identity.verify(connection, marker["installation_id"])
        initialize_search(owner_engine)
        provision_runtime(owner_dsn, runtime_dsn, marker["installation_id"])
    finally:
        owner_engine.dispose()
    return {"state": "search_prepared"}
