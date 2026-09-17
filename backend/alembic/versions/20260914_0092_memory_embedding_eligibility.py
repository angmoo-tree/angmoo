"""Independent memory embedding selection and accepted-result registration."""
from alembic import op
import sqlalchemy as sa

revision = "20260914_0092"
down_revision = "20260910_0091"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("memory_embedding_settings",
        sa.Column("scope_setting_id", sa.String(64), sa.ForeignKey("memory_scope_settings.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("provider", sa.String(40), nullable=False),
        sa.Column("model", sa.String(120), nullable=False),
        sa.Column("credential_id", sa.String(64), sa.ForeignKey("llm_credentials.id", ondelete="SET NULL")),
        sa.Column("profile", sa.String(128), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("version >= 1", name="ck_memory_embedding_version"))
    op.create_table("memory_vector_eligibility",
        sa.Column("memory_item_id", sa.String(64), sa.ForeignKey("memory_items.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("item_version", sa.Integer(), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("registration_revision", sa.String(40), nullable=False),
        sa.Column("registered_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("item_version >= 1", name="ck_memory_vector_eligibility_version"))


def downgrade():
    op.drop_table("memory_vector_eligibility")
    op.drop_table("memory_embedding_settings")
