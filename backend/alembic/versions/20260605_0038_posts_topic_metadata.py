"""add posts topic metadata

Revision ID: 20260605_0038
Revises: 20260604_0037
Create Date: 2026-06-05
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "20260605_0038"
down_revision: Union[str, None] = "20260604_0037"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("posts", sa.Column("topic_signature", sa.Text(), nullable=True))
    op.add_column("posts", sa.Column("novelty_basis", sa.Text(), nullable=True))
    op.execute(
        """
        DO $$
        DECLARE
            rec RECORD;
            payload JSONB;
            created_post_id TEXT;
            topic TEXT;
            novelty TEXT;
        BEGIN
            FOR rec IN
                SELECT id, target_post_id, result
                FROM agent_activity_logs
                WHERE action_type = 'post_created'
                  AND result IS NOT NULL
                  AND result LIKE '{%'
                ORDER BY created_at DESC, id DESC
            LOOP
                BEGIN
                    payload := rec.result::jsonb;
                EXCEPTION WHEN others THEN
                    CONTINUE;
                END;

                created_post_id := COALESCE(NULLIF(payload->>'created_post_id', ''), rec.target_post_id);
                topic := NULLIF(BTRIM(payload->>'topic_signature'), '');
                novelty := NULLIF(BTRIM(payload->>'novelty_basis'), '');

                IF created_post_id IS NULL OR (topic IS NULL AND novelty IS NULL) THEN
                    CONTINUE;
                END IF;

                UPDATE posts
                SET
                    topic_signature = COALESCE(posts.topic_signature, topic),
                    novelty_basis = COALESCE(posts.novelty_basis, novelty)
                WHERE posts.id = created_post_id
                  AND (posts.topic_signature IS NULL OR posts.novelty_basis IS NULL);
            END LOOP;
        END $$;
        """
    )


def downgrade() -> None:
    op.drop_column("posts", "novelty_basis")
    op.drop_column("posts", "topic_signature")
