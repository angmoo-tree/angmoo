"""migrate legacy comments to reply posts

Revision ID: 20260514_0007
Revises: 20260513_0006
Create Date: 2026-05-14
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260514_0007"
down_revision: str | None = "20260513_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        sa.text(
            """
            insert into posts (
                id,
                author_user_id,
                author_character_id,
                reply_to_post_id,
                quote_post_id,
                repost_of_post_id,
                post_type,
                visibility,
                author_name,
                title,
                body,
                created_at,
                updated_at,
                deleted_at
            )
            select
                'reply-comment-' || c.id,
                null,
                c.author_character_id,
                c.post_id,
                null,
                null,
                'reply',
                'public',
                ch.name,
                case
                    when length(p.title) > 156 then 'RE: ' || substr(p.title, 1, 156)
                    else 'RE: ' || p.title
                end,
                c.content,
                c.created_at,
                c.created_at,
                null
            from comments c
            join posts p on p.id = c.post_id
            join characters ch on ch.id = c.author_character_id
            where not exists (
                select 1
                from posts existing
                where existing.id = 'reply-comment-' || c.id
            )
            """
        )
    )
    op.execute(sa.text("delete from comments"))


def downgrade() -> None:
    op.execute(
        sa.text(
            """
            insert into comments (id, post_id, author_character_id, content, created_at)
            select
                substring(id from length('reply-comment-') + 1)::integer,
                reply_to_post_id,
                author_character_id,
                body,
                created_at
            from posts
            where id like 'reply-comment-%'
                and post_type = 'reply'
                and reply_to_post_id is not null
                and author_character_id is not null
            on conflict (id) do nothing
            """
        )
    )
    op.execute(
        sa.text(
            """
            delete from posts
            where id like 'reply-comment-%'
                and post_type = 'reply'
            """
        )
    )
