"""Change feed mode without changing ownership, approvals or autonomy switches."""
from app.runtime.persistence.sqlite_recommendation_modes import upgrade_modes

MUTABLE_IDENTITY_TABLES = frozenset({"world_characters"})


def capture_delta(connection):
    return {r["id"]: dict(r) for r in connection.exec_driver_sql("SELECT * FROM world_characters").mappings()}


def upgrade(connection):
    upgrade_modes(connection)


def verify_delta(connection, before):
    after = capture_delta(connection)
    expected = {key: {**row, "feed_runtime_mode": "topic_recommendation_v1" if row["feed_runtime_mode"] == "keyword_search_v1" else row["feed_runtime_mode"]} for key, row in before.items()}
    if after != expected:
        raise RuntimeError("recommendation_mode_identity_changed")
