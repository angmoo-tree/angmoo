"""Add bounded, content-free Chat retrieval observations."""
from alembic import op
import sqlalchemy as sa

revision = "20260910_0091"
down_revision = "20260909_0090"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table("chat_retrieval_diagnostics",
        sa.Column("request_id", sa.String(64), sa.ForeignKey("chat_response_requests.request_id", ondelete="CASCADE"), primary_key=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload_bytes", sa.Integer(), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.CheckConstraint("payload_bytes >= 0 AND payload_bytes <= 16384", name="ck_chat_diagnostic_size"))
    op.create_index("ix_chat_diagnostics_expiry", "chat_retrieval_diagnostics", ["expires_at"])


def downgrade() -> None:
    op.drop_table("chat_retrieval_diagnostics")
