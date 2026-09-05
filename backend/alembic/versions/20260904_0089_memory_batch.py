"""Add opt-in Memory batch settings, admission and audit (20260904_0089)."""

from alembic import op

from app.core.db import Base
from app.domains.memory.infrastructure.batch_models import (
    MEMORY_BATCH_TABLES,
    create_memory_batch_schema,
)

revision = "20260904_0089"
down_revision = "20260904_0088"
branch_labels = None
depends_on = None


def upgrade() -> None:
    create_memory_batch_schema(op.get_bind())


def downgrade() -> None:
    for name in reversed(MEMORY_BATCH_TABLES):
        Base.metadata.tables[name].drop(op.get_bind(), checkfirst=False)
