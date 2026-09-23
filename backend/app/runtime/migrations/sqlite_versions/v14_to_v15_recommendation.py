"""Add recommendation metadata without classifying or enrolling existing content."""
from sqlalchemy import Connection, text
from app.runtime.persistence.sqlite_schema import build_sqlite_baseline_metadata

TABLES = (
    "social_recommendation_catalogs", "social_recommendation_topics",
    "social_recommendation_topic_sources", "social_recommendation_posts",
    "social_recommendation_post_topics", "social_recommendation_preparations",
    "social_recommendation_deliveries",
)
MUTABLE_IDENTITY_TABLES = frozenset(TABLES)


def capture_delta(connection: Connection):
    inventory = set(connection.execute(text("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'" )).scalars())
    if inventory.intersection(TABLES):
        raise RuntimeError("recommendation_tables_already_exist")
    return inventory


def upgrade(connection: Connection):
    metadata = build_sqlite_baseline_metadata()
    metadata.create_all(connection, tables=[metadata.tables[name] for name in TABLES], checkfirst=False)


def verify_delta(connection: Connection, before):
    after = set(connection.execute(text("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'" )).scalars())
    if after != before | set(TABLES):
        raise RuntimeError("recommendation_inventory_mismatch")
    for name in TABLES:
        if connection.execute(text(f'SELECT count(*) FROM "{name}"')).scalar_one():
            raise RuntimeError("recommendation_automatic_backfill_forbidden")
