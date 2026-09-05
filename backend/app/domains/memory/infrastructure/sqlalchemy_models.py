"""Exact imports retained for immutable historical SQLite/Alembic revisions.

All ORM classes and schema builder implementations are owned by memory.models.
New runtime consumers import that owner directly.
"""

from app.domains.memory.models.items import (
    MEMORY_SCHEMA_V1_TABLES,
    create_memory_schema_v1,
    drop_memory_schema_v1,
)

__all__ = ['MEMORY_SCHEMA_V1_TABLES', 'create_memory_schema_v1', 'drop_memory_schema_v1']
