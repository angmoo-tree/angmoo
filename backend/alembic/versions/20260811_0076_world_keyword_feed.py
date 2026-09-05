"""add world scoped keyword feed runtime

Revision ID: 20260811_0076
Revises: 20260810_0075
Create Date: 2026-08-11
"""

from collections.abc import Sequence
import re
import unicodedata

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20260811_0076"
down_revision: str | None = "20260810_0075"
branch_labels: str | Sequence[str] | None = None
depends_on: str | None = None


JSON_DOCUMENT = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")
_WHITESPACE_RE = re.compile(r"\s+")


def _normalize(value: object, *, max_chars: int) -> str:
    text = unicodedata.normalize("NFKC", str(value or ""))
    text = "".join(
        " " if unicodedata.category(character) in {"Cc", "Cf"} else character
        for character in text
    )
    return _WHITESPACE_RE.sub(" ", text).strip().casefold()[:max_chars]


def _document(title: object, body: object, topic_signature: object) -> str:
    values = (
        _normalize(title, max_chars=160),
        _normalize(body, max_chars=4_000),
        _normalize(topic_signature, max_chars=300),
    )
    return "\n".join(value for value in values if value)


def _backfill_search_document() -> None:
    bind = op.get_bind()
    rows = bind.execute(
        sa.text("SELECT id, title, body, topic_signature FROM posts")
    ).mappings()
    updates = [
        {
            "post_id": row["id"],
            "search_document": _document(
                row["title"], row["body"], row["topic_signature"]
            ),
        }
        for row in rows
    ]
    if updates:
        bind.execute(
            sa.text(
                "UPDATE posts SET search_document = :search_document WHERE id = :post_id"
            ),
            updates,
        )


def upgrade() -> None:
    op.add_column(
        "world_characters",
        sa.Column(
            "feed_runtime_mode",
            sa.String(length=32),
            server_default="legacy_latest_v1",
            nullable=False,
        ),
    )
    op.create_check_constraint(
        "ck_world_characters_feed_runtime_mode",
        "world_characters",
        "feed_runtime_mode IN ('legacy_latest_v1','keyword_search_v1')",
    )

    op.add_column(
        "posts",
        sa.Column("search_document", sa.Text(), server_default="", nullable=False),
    )
    _backfill_search_document()
    op.create_unique_constraint("uq_posts_id_world", "posts", ["id", "world_id"])

    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
        op.create_index(
            "ix_posts_world_feed_search_document_trgm",
            "posts",
            ["search_document"],
            postgresql_using="gin",
            postgresql_ops={"search_document": "gin_trgm_ops"},
            postgresql_where=sa.text(
                "world_id IS NOT NULL AND visibility = 'public' "
                "AND deleted_at IS NULL AND report_hidden_at IS NULL "
                "AND reply_to_post_id IS NULL AND post_type <> 'repost' "
                "AND repost_of_post_id IS NULL"
            ),
        )

    op.create_table(
        "world_character_feed_cursors",
        sa.Column("world_character_id", sa.String(length=64), nullable=False),
        sa.Column("world_id", sa.String(length=64), nullable=False),
        sa.Column("next_keyword_offset", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("last_cycle_key", sa.String(length=128), nullable=True),
        sa.Column("last_run_id", sa.String(length=64), nullable=True),
        sa.Column("last_cycle_summary", JSON_DOCUMENT, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "next_keyword_offset IN (0,2,4,6)",
            name="ck_world_character_feed_cursors_offset",
        ),
        sa.CheckConstraint(
            "version >= 1", name="ck_world_character_feed_cursors_version"
        ),
        sa.ForeignKeyConstraint(
            ["world_character_id", "world_id"],
            ["world_characters.id", "world_characters.world_id"],
            name="fk_world_character_feed_cursors_character_scope",
        ),
        sa.PrimaryKeyConstraint("world_character_id"),
    )

    op.create_table(
        "world_character_blocks",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("world_id", sa.String(length=64), nullable=False),
        sa.Column("blocker_world_character_id", sa.String(length=64), nullable=False),
        sa.Column("blocked_world_character_id", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "blocker_world_character_id != blocked_world_character_id",
            name="ck_world_character_blocks_not_self",
        ),
        sa.ForeignKeyConstraint(
            ["blocker_world_character_id", "world_id"],
            ["world_characters.id", "world_characters.world_id"],
            name="fk_world_character_blocks_blocker_scope",
        ),
        sa.ForeignKeyConstraint(
            ["blocked_world_character_id", "world_id"],
            ["world_characters.id", "world_characters.world_id"],
            name="fk_world_character_blocks_blocked_scope",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "blocker_world_character_id",
            "blocked_world_character_id",
            name="uq_world_character_blocks_direction",
        ),
    )
    op.create_index(
        "ix_world_character_blocks_world", "world_character_blocks", ["world_id"]
    )

    op.create_table(
        "world_character_feed_observations",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("world_id", sa.String(length=64), nullable=False),
        sa.Column("observer_world_character_id", sa.String(length=64), nullable=False),
        sa.Column("post_id", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("claim_token", sa.String(length=128), nullable=False),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("cycle_key", sa.String(length=128), nullable=False),
        sa.Column("run_id", sa.String(length=64), nullable=False),
        sa.Column("matched_keywords", JSON_DOCUMENT, nullable=False),
        sa.Column("matched_fields", JSON_DOCUMENT, nullable=False),
        sa.Column("rank_score", sa.Float(), nullable=False),
        sa.Column("post_created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("decision_outcome", sa.String(length=24), nullable=True),
        sa.Column("reason_code", sa.String(length=64), nullable=True),
        sa.Column("selected_action", sa.String(length=24), nullable=True),
        sa.Column("interaction_intent", sa.String(length=40), nullable=True),
        sa.Column("comment_purpose", sa.String(length=40), nullable=True),
        sa.Column("public_action_execution_id", sa.Integer(), nullable=True),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('claimed','observed','retryable_failed')",
            name="ck_world_character_feed_observations_status",
        ),
        sa.CheckConstraint(
            "decision_outcome IS NULL OR decision_outcome IN "
            "('not_selected','action_selected','no_action')",
            name="ck_world_character_feed_observations_outcome",
        ),
        sa.CheckConstraint(
            "selected_action IS NULL OR selected_action IN "
            "('like','comment','repost','follow')",
            name="ck_world_character_feed_observations_action",
        ),
        sa.CheckConstraint(
            "interaction_intent IS NULL OR interaction_intent IN "
            "('ordinary_comment','joint_activity_proposal','proposal_response')",
            name="ck_world_character_feed_observations_intent",
        ),
        sa.CheckConstraint(
            "comment_purpose IS NULL OR comment_purpose IN "
            "('question','advice','empathy','encouragement','information',"
            "'humor','disagreement','competition','observation')",
            name="ck_world_character_feed_observations_purpose",
        ),
        sa.CheckConstraint(
            "reason_code IS NULL OR reason_code IN "
            "('no_searchable_keyword','no_candidate','no_allowed_action',"
            "'model_abstained','proposal_ineligible','proposal_apply_not_ready',"
            "'target_stale','writer_invalid')",
            name="ck_world_character_feed_observations_reason",
        ),
        sa.ForeignKeyConstraint(
            ["observer_world_character_id", "world_id"],
            ["world_characters.id", "world_characters.world_id"],
            name="fk_world_character_feed_observations_observer_scope",
        ),
        sa.ForeignKeyConstraint(
            ["post_id", "world_id"],
            ["posts.id", "posts.world_id"],
            name="fk_world_character_feed_observations_post_scope",
        ),
        sa.ForeignKeyConstraint(
            ["public_action_execution_id"],
            ["agent_public_action_executions.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "observer_world_character_id",
            "post_id",
            name="uq_world_character_feed_observations_post",
        ),
    )
    op.create_index(
        "ix_world_character_feed_observations_claim_expiry",
        "world_character_feed_observations",
        ["status", "lease_expires_at"],
    )
    op.create_index(
        "ix_world_character_feed_observations_character_created",
        "world_character_feed_observations",
        ["observer_world_character_id", "created_at"],
    )

    for name, type_ in (
        ("world_id", sa.String(length=64)),
        ("actor_world_character_id", sa.String(length=64)),
        ("feed_observation_id", sa.String(length=64)),
        ("interaction_intent", sa.String(length=40)),
        ("comment_purpose", sa.String(length=40)),
    ):
        op.add_column(
            "agent_public_action_executions", sa.Column(name, type_, nullable=True)
        )
    op.create_foreign_key(
        "fk_agent_public_action_executions_world",
        "agent_public_action_executions",
        "worlds",
        ["world_id"],
        ["id"],
    )
    op.create_foreign_key(
        "fk_agent_public_action_executions_actor_world_character",
        "agent_public_action_executions",
        "world_characters",
        ["actor_world_character_id"],
        ["id"],
    )
    op.create_foreign_key(
        "fk_agent_public_action_executions_feed_observation",
        "agent_public_action_executions",
        "world_character_feed_observations",
        ["feed_observation_id"],
        ["id"],
    )
    op.create_index(
        "ix_agent_public_action_executions_world_id",
        "agent_public_action_executions",
        ["world_id"],
    )
    op.create_index(
        "ix_agent_public_action_executions_actor_world_character_id",
        "agent_public_action_executions",
        ["actor_world_character_id"],
    )
    op.create_index(
        "ix_agent_public_action_executions_feed_observation_id",
        "agent_public_action_executions",
        ["feed_observation_id"],
    )


def downgrade() -> None:
    bind = op.get_bind()
    keyword_modes = bind.scalar(
        sa.text(
            "SELECT count(*) FROM world_characters "
            "WHERE feed_runtime_mode != 'legacy_latest_v1'"
        )
    )
    if int(keyword_modes or 0) > 0:
        raise RuntimeError(
            "cannot downgrade 0076 while keyword feed runtime modes are active"
        )

    for index_name in (
        "ix_agent_public_action_executions_feed_observation_id",
        "ix_agent_public_action_executions_actor_world_character_id",
        "ix_agent_public_action_executions_world_id",
    ):
        op.drop_index(index_name, table_name="agent_public_action_executions")
    for constraint_name in (
        "fk_agent_public_action_executions_feed_observation",
        "fk_agent_public_action_executions_actor_world_character",
        "fk_agent_public_action_executions_world",
    ):
        op.drop_constraint(
            constraint_name, "agent_public_action_executions", type_="foreignkey"
        )
    for column_name in (
        "comment_purpose",
        "interaction_intent",
        "feed_observation_id",
        "actor_world_character_id",
        "world_id",
    ):
        op.drop_column("agent_public_action_executions", column_name)

    op.drop_index(
        "ix_world_character_feed_observations_character_created",
        table_name="world_character_feed_observations",
    )
    op.drop_index(
        "ix_world_character_feed_observations_claim_expiry",
        table_name="world_character_feed_observations",
    )
    op.drop_table("world_character_feed_observations")
    op.drop_index(
        "ix_world_character_blocks_world", table_name="world_character_blocks"
    )
    op.drop_table("world_character_blocks")
    op.drop_table("world_character_feed_cursors")

    if bind.dialect.name == "postgresql":
        op.drop_index(
            "ix_posts_world_feed_search_document_trgm", table_name="posts"
        )
    op.drop_constraint("uq_posts_id_world", "posts", type_="unique")
    op.drop_column("posts", "search_document")

    op.drop_constraint(
        "ck_world_characters_feed_runtime_mode",
        "world_characters",
        type_="check",
    )
    op.drop_column("world_characters", "feed_runtime_mode")
