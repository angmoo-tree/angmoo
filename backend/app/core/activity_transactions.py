"""Short, replayable SNS database units; never wrap model or filesystem work."""
from app.core.database_transactions import (
    POSTGRES_UNIT_RETRY as POSTGRES_ACTIVITY_RETRY,
    database_write,
)


def activity_write(db, operation, **kwargs):
    """Re-read authorization/current state inside operation on every attempt."""
    return database_write(db, operation, **kwargs)
