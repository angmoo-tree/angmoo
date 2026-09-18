"""Enable topic recommendation while retaining existing autonomy choices."""
from alembic import op
from app.runtime.persistence.sqlite_recommendation_modes import upgrade_modes

revision = "20260918_0096"
down_revision = "20260918_0095"
branch_labels = None
depends_on = None


def upgrade():
    if op.get_bind().dialect.name == "sqlite":
        upgrade_modes(op.get_bind())
    else:
        op.drop_constraint("ck_world_characters_feed_runtime_mode", "world_characters", type_="check")
        op.create_check_constraint("ck_world_characters_feed_runtime_mode", "world_characters", "feed_runtime_mode IN ('legacy_latest_v1','keyword_search_v1','topic_recommendation_v1')")
        op.execute("UPDATE world_characters SET feed_runtime_mode='topic_recommendation_v1' WHERE feed_runtime_mode='keyword_search_v1'")
        op.create_index("ix_posts_world_author_created", "posts", ["world_id", "author_world_character_id", "created_at", "id"])


def downgrade():
    raise RuntimeError("recommendation mode migration is forward only")
