"""Bound transient serving connections outside the two application pools.

One backend process owns this admission limit. A slot remains held until the
connection has committed/rolled back and closed, including exception paths.
Provisioning and offline migration deliberately do not use this serving budget.
"""
from contextlib import contextmanager
from threading import BoundedSemaphore

import psycopg

from app.core.postgresql_capacity import DIRECT_CONNECTION_MAX

_slots = BoundedSemaphore(DIRECT_CONNECTION_MAX)


class PostgresDirectConnectionBusy(TimeoutError):
    pass


@contextmanager
def serving_connection(dsn, *, admission_timeout=0.25, **kwargs):
    if not _slots.acquire(timeout=admission_timeout):
        raise PostgresDirectConnectionBusy('postgresql_direct_connection_budget')
    try:
        with psycopg.connect(dsn, **kwargs) as connection:
            yield connection
    finally:
        _slots.release()
