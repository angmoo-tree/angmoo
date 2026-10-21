"""Bounded Chat history and root feed ordering indexes."""
from alembic import op

revision = "20261022_0118"
down_revision = "20261019_0117"
branch_labels = depends_on = None


def upgrade():
    op.create_index("ix_message_messages_thread_created_id", "message_messages", ["thread_id", "created_at", "id"])
    op.create_index("ix_posts_world_root_page", "posts", ["world_id", "reply_to_post_id", "visibility", "deleted_at", "report_hidden_at", "created_at", "id"])


def downgrade():
    raise RuntimeError("forward_only_migration")
