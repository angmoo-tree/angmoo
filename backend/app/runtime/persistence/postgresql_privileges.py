"""Provision the isolated runtime login; only the schema owner calls this."""
import psycopg
from psycopg import sql
from app.runtime.postgresql_configuration import RUN_ID,SOURCE_SHA
from app.core.postgresql_capacity import RUNTIME_CONNECTION_LIMIT

RUNTIME_ROLE='angmoo_pg_run01_runtime'
ADMIN_ROLE='angmoo_pg_run01_admin'
READ_ONLY=('angmoo_experiment_identity','angmoo_postgresql_schema_version',
    'checkpoint_migrations','pg_checkpoint_contract','pg_migration_state',
    'pg_migration_tables','pg_migration_checkpoints')


def provision_runtime(dsn,password):
    if len(password)<32:raise ValueError('postgresql_runtime_password_invalid')
    with psycopg.connect(dsn.replace('postgresql+psycopg://','postgresql://',1)) as db:
        identity=db.execute('SELECT run_id,source_sha FROM angmoo_experiment_identity').fetchone()
        user,database=db.execute('SELECT current_user,current_database()').fetchone()
        if identity!=(RUN_ID,SOURCE_SHA) or user!=ADMIN_ROLE or not database.startswith('angmoo_pg_run01'):
            raise ValueError('postgresql_runtime_owner_mismatch')
        existing=db.execute("SELECT shobj_description(oid,'pg_authid') FROM pg_roles WHERE rolname=%s",(RUNTIME_ROLE,)).fetchone()
        if existing is None:
            db.execute(sql.SQL('CREATE ROLE {} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS CONNECTION LIMIT {} PASSWORD {}').format(sql.Identifier(RUNTIME_ROLE),sql.Literal(RUNTIME_CONNECTION_LIMIT),sql.Literal(password)))
            db.execute(sql.SQL('COMMENT ON ROLE {} IS {}').format(sql.Identifier(RUNTIME_ROLE),sql.Literal(RUN_ID)))
        elif existing!=(RUN_ID,):raise ValueError('postgresql_runtime_role_owner_mismatch')
        else:
            flags=db.execute('SELECT rolsuper,rolcreatedb,rolcreaterole,rolreplication,rolbypassrls FROM pg_roles WHERE rolname=%s',(RUNTIME_ROLE,)).fetchone()
            if any(flags):raise ValueError('postgresql_runtime_role_privilege_mismatch')
            db.execute(sql.SQL('ALTER ROLE {} CONNECTION LIMIT {} PASSWORD {}').format(sql.Identifier(RUNTIME_ROLE),sql.Literal(RUNTIME_CONNECTION_LIMIT),sql.Literal(password)))
        db.execute(sql.SQL('REVOKE ALL ON DATABASE {} FROM PUBLIC').format(sql.Identifier(database)))
        db.execute(sql.SQL('GRANT CONNECT ON DATABASE {} TO {}').format(sql.Identifier(database),sql.Identifier(RUNTIME_ROLE)))
        db.execute('REVOKE CREATE ON SCHEMA public FROM PUBLIC')
        db.execute(sql.SQL('GRANT USAGE ON SCHEMA public TO {}').format(sql.Identifier(RUNTIME_ROLE)))
        db.execute(sql.SQL('GRANT SELECT,INSERT,UPDATE,DELETE ON ALL TABLES IN SCHEMA public TO {}').format(sql.Identifier(RUNTIME_ROLE)))
        db.execute(sql.SQL('GRANT USAGE,SELECT ON ALL SEQUENCES IN SCHEMA public TO {}').format(sql.Identifier(RUNTIME_ROLE)))
        protected=[]
        for table in READ_ONLY:
            if db.execute('SELECT to_regclass(%s)',(table,)).fetchone()[0] is not None:
                db.execute(sql.SQL('REVOKE INSERT,UPDATE,DELETE ON {} FROM {}').format(sql.Identifier(table),sql.Identifier(RUNTIME_ROLE)))
                protected.append(table)
        db.execute(sql.SQL('ALTER ROLE {} SET search_path TO public').format(sql.Identifier(RUNTIME_ROLE)))
        return {'runtime_role':RUNTIME_ROLE,'schema_owner':ADMIN_ROLE,'database':database,
            'runtime_ddl':False,'runtime_createdb':False,'runtime_superuser':False,'read_only_tables':protected,
            'connection_limit':RUNTIME_CONNECTION_LIMIT}


def update_runtime_connection_limit(dsn):
    """Update the owned existing role without touching credentials or grants."""
    with psycopg.connect(dsn.replace('postgresql+psycopg://','postgresql://',1)) as db:
        identity=db.execute('SELECT run_id,source_sha FROM angmoo_experiment_identity').fetchone()
        user,database=db.execute('SELECT current_user,current_database()').fetchone()
        if identity!=(RUN_ID,SOURCE_SHA) or user!=ADMIN_ROLE or not database.startswith('angmoo_pg_run01'):
            raise ValueError('postgresql_runtime_owner_mismatch')
        role=db.execute("SELECT shobj_description(oid,'pg_authid'),rolsuper,rolcreatedb,rolcreaterole,rolreplication,rolbypassrls FROM pg_roles WHERE rolname=%s",(RUNTIME_ROLE,)).fetchone()
        if role is None or role[0]!=RUN_ID or any(role[1:]):
            raise ValueError('postgresql_runtime_role_privilege_mismatch')
        db.execute(sql.SQL('ALTER ROLE {} CONNECTION LIMIT {}').format(sql.Identifier(RUNTIME_ROLE),sql.Literal(RUNTIME_CONNECTION_LIMIT)))
        return {'runtime_role':RUNTIME_ROLE,'connection_limit':RUNTIME_CONNECTION_LIMIT,'password_changed':False,'privileges_changed':False}
