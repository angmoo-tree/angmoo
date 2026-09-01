"""add canonical World-scoped Memory schema v1

Revision ID: 20260831_0085
Revises: 20260831_0084
Create Date: 2026-08-31
"""

from collections.abc import Sequence

from alembic import op

from app.domains.memory.infrastructure.sqlalchemy_models import (
    create_memory_schema_v1,
    drop_memory_schema_v1,
)


revision: str = "20260831_0085"
down_revision: str | None = "20260831_0084"
branch_labels: str | Sequence[str] | None = None
depends_on: str | None = None


def upgrade() -> None:
    create_memory_schema_v1(op.get_bind())


def downgrade() -> None:
    drop_memory_schema_v1(op.get_bind())
