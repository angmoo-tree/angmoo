"""add character handle and avatar url

Revision ID: 20260514_0008
Revises: 20260514_0007
Create Date: 2026-05-14
"""

from collections.abc import Sequence
import re

from alembic import op
import sqlalchemy as sa


revision: str = "20260514_0008"
down_revision: str | None = "20260514_0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("characters", sa.Column("handle", sa.String(length=40), nullable=True))
    op.add_column(
        "characters", sa.Column("avatar_url", sa.String(length=500), nullable=True)
    )

    bind = op.get_bind()
    rows = bind.execute(
        sa.text("select id, name from characters order by created_at asc, id asc")
    ).all()
    used: set[str] = set()
    for row in rows:
        mapping = row._mapping
        handle = _unique_handle(
            _handle_from_name(mapping["name"], mapping["id"]),
            used,
        )
        used.add(handle)
        bind.execute(
            sa.text("update characters set handle = :handle where id = :id"),
            {"handle": handle, "id": mapping["id"]},
        )

    op.alter_column("characters", "handle", existing_type=sa.String(length=40), nullable=False)
    op.create_unique_constraint("uq_characters_handle", "characters", ["handle"])


def downgrade() -> None:
    op.drop_constraint("uq_characters_handle", "characters", type_="unique")
    op.drop_column("characters", "avatar_url")
    op.drop_column("characters", "handle")


def _handle_from_name(name: str, character_id: str) -> str:
    special_handles = {
        "전복": "jeonbok",
        "망고": "mango",
        "芒果": "mango",
        "미도리야 이즈쿠": "midoriya_izuku",
    }
    if name in special_handles:
        return special_handles[name]

    normalized = re.sub(r"[\s-]+", "_", name.strip().lower())
    handle = re.sub(r"[^a-z0-9_]", "", normalized).strip("_")
    if len(handle) < 2:
        handle = f"angmoo_{character_id.replace('char-', '')[:8]}"
    return handle[:40].strip("_") or f"angmoo_{character_id[-8:]}"


def _unique_handle(handle: str, used: set[str]) -> str:
    candidate = handle
    suffix = 2
    while candidate in used:
        suffix_text = f"_{suffix}"
        candidate = f"{handle[: 40 - len(suffix_text)]}{suffix_text}"
        suffix += 1
    return candidate
