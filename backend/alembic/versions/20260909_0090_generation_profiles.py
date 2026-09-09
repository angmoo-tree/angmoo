"""Persist generation thinking choices and Memory execution snapshots.

Revision ID: 20260909_0090
Revises: 20260904_0089
"""

from alembic import op
import sqlalchemy as sa

revision = "20260909_0090"
down_revision = "20260904_0089"
branch_labels = None
depends_on = None

_THINKING_COLUMNS = {
    "llm_credentials": "thinking_level",
    "agent_creation_drafts": "thinking_level",
    "user_message_preferences": "default_thinking_level",
    "message_threads": "selected_thinking_level",
    "chat_response_requests": "selected_thinking_level",
    "memory_batch_profiles": "thinking_level",
    "memory_batch_runs": "thinking_level",
}


def upgrade() -> None:
    for table, name in _THINKING_COLUMNS.items():
        op.add_column(table, sa.Column(name, sa.String(8), nullable=False, server_default="high"))
    op.add_column("memory_batch_settings", sa.Column("execution_version", sa.Integer(), nullable=False, server_default="1"))
    op.add_column("memory_batch_settings", sa.Column("retry_request_key", sa.String(128)))


def downgrade() -> None:
    op.drop_column("memory_batch_settings", "retry_request_key")
    op.drop_column("memory_batch_settings", "execution_version")
    for table, name in reversed(tuple(_THINKING_COLUMNS.items())):
        op.drop_column(table, name)
