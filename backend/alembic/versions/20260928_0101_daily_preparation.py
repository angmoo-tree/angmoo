"""Date-scoped preparation and direct daily plans; history is preserved."""
from alembic import op
import sqlalchemy as sa

revision = "20260928_0101"
down_revision = "20260927_0100"
branch_labels = None
depends_on = None


def upgrade():
    if op.get_context().as_sql:
        raise RuntimeError("daily_preparation_online_migration_required")
    connection = op.get_bind()
    if connection.dialect.name == "sqlite":
        from app.runtime.migrations.sqlite_versions.daily_preparation_v23 import upgrade as upgrade_sqlite
        upgrade_sqlite(connection)
        return
    if connection.dialect.name != "postgresql":
        raise RuntimeError("daily_preparation_dialect_unsupported")
    op.alter_column("daily_activity_plans", "repertoire_id", existing_type=sa.String(64), nullable=True)
    op.add_column("daily_activity_plans", sa.Column("generation_source", sa.String(24), nullable=False, server_default="repertoire"))
    op.add_column("daily_activity_plans", sa.Column("preparation_contract_version", sa.String(40), nullable=False, server_default="repertoire-v1"))
    op.create_check_constraint("ck_daily_activity_plans_source", "daily_activity_plans", "generation_source IN ('repertoire','daily_generation') AND (generation_source != 'repertoire' OR repertoire_id IS NOT NULL)")
    op.drop_constraint("ck_daily_activity_plan_items_origin", "daily_activity_plan_items", type_="check")
    op.create_check_constraint("ck_daily_activity_plan_items_origin", "daily_activity_plan_items", "origin_type IN ('repertoire','joint_activity','daily_generation')")
    op.execute("\nCREATE TABLE activity_preparation_jobs (\n\tid VARCHAR(64) NOT NULL, \n\tworld_id VARCHAR(64) NOT NULL, \n\tworld_character_id VARCHAR(64) NOT NULL, \n\tlocal_date DATE NOT NULL, \n\ttimezone_name VARCHAR(64) NOT NULL, \n\tcontract_version VARCHAR(40) NOT NULL, \n\trequest_id VARCHAR(128) NOT NULL, \n\tmode VARCHAR(20) NOT NULL, \n\tstate VARCHAR(24) NOT NULL, \n\tclaim_token VARCHAR(64), \n\tlease_expires_at TIMESTAMP WITH TIME ZONE, \n\tnext_retry_at TIMESTAMP WITH TIME ZONE, \n\tattempt_count INTEGER NOT NULL, \n\tjson_retry_count INTEGER NOT NULL, \n\tinput_digest VARCHAR(64) NOT NULL, \n\treason_code VARCHAR(100), \n\tplan_id VARCHAR(64), \n\tplan_version INTEGER, \n\tinput_snapshot JSONB NOT NULL, \n\tapplied_snapshot JSONB NOT NULL, \n\tusage_snapshot JSONB NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tversion INTEGER NOT NULL, \n\tPRIMARY KEY (id), \n\tCONSTRAINT uq_activity_preparation_request UNIQUE (world_character_id, local_date, request_id), \n\tCONSTRAINT fk_activity_preparation_scope FOREIGN KEY(world_character_id, world_id) REFERENCES world_characters (id, world_id), \n\tCONSTRAINT ck_activity_preparation_mode CHECK (mode IN ('initial','daily','manual_plan')), \n\tCONSTRAINT ck_activity_preparation_state CHECK (state IN ('pending','running','waiting','ready','failed','needs_user_action','cancelled')), \n\tCONSTRAINT ck_activity_preparation_attempts CHECK (attempt_count >= 0 AND attempt_count <= 4)\n)\n\n")
    op.execute('CREATE INDEX ix_activity_preparation_due ON activity_preparation_jobs (state, next_retry_at)')


def downgrade():
    raise RuntimeError("daily_preparation_preserves_history_forward_only")
