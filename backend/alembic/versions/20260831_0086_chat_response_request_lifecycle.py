"""add canonical Chat response request lifecycle

Revision ID: 20260831_0086
Revises: 20260831_0085
Create Date: 2026-08-31
"""

from collections.abc import Sequence

from alembic import op

from app.domains.chat.infrastructure.sqlalchemy_models import (
    create_response_request_schema,
    drop_response_request_schema,
)


revision: str = "20260831_0086"
down_revision: str | None = "20260831_0085"
branch_labels: str | Sequence[str] | None = None
depends_on: str | None = None


def upgrade() -> None:
    create_response_request_schema(op.get_bind())


def downgrade() -> None:
    drop_response_request_schema(op.get_bind())
