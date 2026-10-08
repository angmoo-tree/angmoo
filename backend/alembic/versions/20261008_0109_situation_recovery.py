"""Receipt recovery runs, bounded audit and terminal discarded tombstones."""
from alembic import op
import sqlalchemy as sa

revision = "20261008_0109"
down_revision = "20261008_0108"
branch_labels = None
depends_on = None


def upgrade():
    connection = op.get_bind()
    if connection.dialect.name == "sqlite":
        from app.runtime.migrations.sqlite_versions.situation_recovery_v32 import upgrade as embedded_upgrade
        embedded_upgrade(connection)
        return
    op.add_column("memory_situation_runs", sa.Column("work_kind", sa.String(24), nullable=False, server_default="pending_apply"))
    op.create_check_constraint("ck_situation_run_work_kind", "memory_situation_runs", "work_kind IN ('pending_apply','blocked_recheck')")
    op.add_column("memory_situation_receipts", sa.Column("state_version", sa.Integer(), nullable=False, server_default="1"))
    op.add_column("memory_situation_receipts", sa.Column("discarded_at", sa.DateTime(timezone=True)))
    op.add_column("memory_situation_receipts", sa.Column("discard_request_key", sa.String(128)))
    op.alter_column("memory_situation_receipts", "manifest_id", existing_type=sa.String(64), nullable=True)
    op.drop_constraint("ck_situation_receipt_state", "memory_situation_receipts", type_="check")
    op.create_check_constraint("ck_situation_receipt_state", "memory_situation_receipts", "state IN ('pending','claimed','applied','blocked','skipped','error','discarded')")
    op.create_check_constraint("ck_situation_receipt_version", "memory_situation_receipts", "state_version >= 1")
    op.create_check_constraint("ck_situation_receipt_manifest", "memory_situation_receipts", "(state = 'discarded' AND manifest_id IS NULL AND description IS NULL AND applied_item_id IS NULL) OR (state <> 'discarded' AND manifest_id IS NOT NULL)")
    op.create_table("memory_situation_recheck_attempts",
        sa.Column("run_id", sa.String(64), sa.ForeignKey("memory_situation_runs.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("receipt_sequence", sa.Integer(), sa.ForeignKey("memory_situation_receipts.sequence", ondelete="CASCADE"), primary_key=True),
        sa.Column("validation_revision", sa.String(40), nullable=False), sa.Column("outcome", sa.String(16), nullable=False),
        sa.Column("reason", sa.String(80)), sa.Column("previous_run_id", sa.String(64), sa.ForeignKey("memory_situation_runs.id", ondelete="SET NULL")),
        sa.Column("previous_state", sa.String(16), nullable=False), sa.Column("previous_error_code", sa.String(80)),
        sa.Column("applied_item_id", sa.String(64), sa.ForeignKey("memory_items.id", ondelete="SET NULL")),
        sa.Column("before_version", sa.Integer(), nullable=False), sa.Column("after_version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))


def downgrade():
    raise RuntimeError("situation_recovery_migration_forward_only")
