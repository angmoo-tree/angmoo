"""PostgreSQL canonical schema v5, retaining embedded schema 41 data."""
import hashlib
from sqlalchemy import JSON, MetaData, text
from sqlalchemy.dialects.postgresql import JSONB
from app.runtime.persistence.model_registration import register_models

VERSION=5
SOURCE_SQLITE_VERSION=41


def metadata():
    original=register_models()
    if len(original.tables)!=186:
        raise RuntimeError("postgresql_canonical_inventory_drift")
    # JSONB supports equality/currentness and indexed JSON operations. The
    # SQLite variant remains unchanged for offline baseline/migration fixtures.
    for table in original.tables.values():
        for column in table.columns:
            if isinstance(column.type, JSON) and "postgresql" not in column.type._variant_mapping:
                column.type=column.type.with_variant(JSONB(none_as_null=column.type.none_as_null),"postgresql")
    result=MetaData()
    for table in original.tables.values():
        table.to_metadata(result)
    for table in result.tables.values():
        for index in table.indexes:
            where=index.dialect_options["sqlite"].get("where")
            if where is not None and index.dialect_options["postgresql"].get("where") is None:
                index.dialect_options["postgresql"]["where"]=where
    return result


def install_json_functions(connection):
    # The few existing SQL expressions use these scalar names. They execute
    # entirely in PostgreSQL; no SQLite library/file is used by these functions.
    connection.exec_driver_sql("""
    CREATE OR REPLACE FUNCTION json_extract(value jsonb, path text) RETURNS text
    LANGUAGE sql IMMUTABLE STRICT AS $$
      SELECT value #>> string_to_array(substr(path,3),'.')
    $$;
    CREATE OR REPLACE FUNCTION json_extract(value json, path text) RETURNS text
    LANGUAGE sql IMMUTABLE STRICT AS $$ SELECT json_extract(value::jsonb,path) $$;
    CREATE OR REPLACE FUNCTION json_extract(value text, path text) RETURNS text
    LANGUAGE sql IMMUTABLE STRICT AS $$ SELECT json_extract(value::jsonb,path) $$;
    CREATE OR REPLACE FUNCTION json_valid(value text) RETURNS int
    LANGUAGE plpgsql IMMUTABLE STRICT AS $$ BEGIN
      PERFORM value::jsonb; RETURN 1;
    EXCEPTION WHEN invalid_text_representation THEN RETURN 0; END $$;
    CREATE OR REPLACE FUNCTION json_type(value text, path text DEFAULT '$') RETURNS text
    LANGUAGE sql IMMUTABLE STRICT AS $$
      SELECT CASE jsonb_typeof(CASE WHEN path='$' THEN value::jsonb ELSE
        value::jsonb #> string_to_array(substr(path,3),'.') END)
        WHEN 'string' THEN 'text' WHEN 'number' THEN 'real'
        ELSE jsonb_typeof(CASE WHEN path='$' THEN value::jsonb ELSE
          value::jsonb #> string_to_array(substr(path,3),'.') END) END
    $$;
    """)


def initialize(connection, *, fences=True, experience_sources=None):
    if connection.dialect.name!="postgresql":
        raise ValueError("postgresql_required")
    tables=metadata()
    install_json_functions(connection)
    tables.create_all(connection)
    connection.exec_driver_sql("""CREATE TABLE IF NOT EXISTS angmoo_postgresql_schema_version
        (singleton boolean PRIMARY KEY CHECK(singleton),version integer NOT NULL,
         source_sqlite_version integer NOT NULL,created_at timestamptz NOT NULL DEFAULT now())""")
    existing=connection.execute(text("SELECT version,source_sqlite_version FROM angmoo_postgresql_schema_version")).first()
    if existing is not None and tuple(existing) not in {(v,SOURCE_SQLITE_VERSION) for v in range(1,VERSION+1)}:
        raise RuntimeError("postgresql_schema_version_unsupported")
    if existing is not None and existing[0] == 1 and not fences:
        raise RuntimeError("postgresql_epoch_upgrade_requires_fences")
    connection.execute(text("INSERT INTO angmoo_postgresql_schema_version(singleton,version,source_sqlite_version) VALUES(true,:v,:s) ON CONFLICT(singleton) DO NOTHING"),dict(v=VERSION,s=SOURCE_SQLITE_VERSION))
    if existing is not None and existing[0] < 3:
        from sqlalchemy.orm import Session
        from app.runtime.persistence.experience_migration import migrate
        with Session(bind=connection, join_transaction_mode="create_savepoint") as session:
            migrate(session, read_sources=experience_sources(session) if experience_sources is not None else None)
            session.commit()
    for name in ("relationship_review_work", "relationship_review_requests", "memory_situation_runs"):
        connection.exec_driver_sql(f"ALTER TABLE {name} ADD COLUMN IF NOT EXISTS maintenance jsonb NOT NULL DEFAULT '{{}}'::jsonb")
    if existing is not None and existing[0] < 5:
        from sqlalchemy.orm import Session
        from app.domains.relationships.service.review_history import reconcile_closed_history
        with Session(bind=connection, join_transaction_mode="create_savepoint") as session:
            reconcile_closed_history(session)
            session.commit()
    if fences:
        from app.runtime.persistence.postgresql_triggers import install
        install(connection,tables)
    # Migration, new tables, fences and marker commit atomically. Older readers
    # reject v3 rather than interpreting snapshots as live-source proofs.
    connection.execute(text("UPDATE angmoo_postgresql_schema_version SET version=:v WHERE singleton=true"),dict(v=VERSION))
    return tables
