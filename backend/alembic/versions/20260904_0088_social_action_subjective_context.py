"""add declared subjective context for successful social actions

Revision ID: 20260904_0088
Revises: 20260903_0087
Create Date: 2026-09-04
"""

from collections.abc import Sequence

from alembic import op

from app.domains.social.infrastructure.sqlalchemy_subjective_context_models import (
    create_subjective_context_schema,
    drop_subjective_context_schema,
)


revision: str = "20260904_0088"
down_revision: str | None = "20260903_0087"
branch_labels: str | Sequence[str] | None = None
depends_on: str | None = None


def upgrade() -> None:
    create_subjective_context_schema(op.get_bind())


def downgrade() -> None:
    drop_subjective_context_schema(op.get_bind())
