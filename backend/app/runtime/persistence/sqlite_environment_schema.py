"""Additive environment schema inventory shared with the frozen upgrader.

Persistence owns metadata construction. Migration execution depends on these
definitions; metadata builders must never import the migration registry.
"""

NEW_TABLES = frozenset({"local_environments", "environment_timezone_changes"})
ADDED_COLUMNS = {
    "users": ("ui_language", "ui_preference_revision"),
    "agent_slots": ("timezone_revision",),
    "local_bot_action_quota_buckets": ("period_state",),
    "memory_maintenance_jobs": ("environment_snapshot",),
}


def remove_environment_schema(metadata) -> None:
    """Restore the pre-v27 inventory without changing historical definitions."""
    for name in NEW_TABLES:
        if name in metadata.tables:
            metadata.remove(metadata.tables[name])
    for table_name, columns in ADDED_COLUMNS.items():
        if table_name not in metadata.tables:
            continue
        table = metadata.tables[table_name]
        for name in columns:
            if name in table.c:
                table._columns.remove(table.c[name])
