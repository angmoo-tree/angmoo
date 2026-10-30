"""Bounded transactional epoch counters without one writer row per World.

The bucket layout is part of PostgreSQL schema version 2. Concurrent source
transactions usually write different rows. Summing every bucket in one MVCC
snapshot preserves the existing proof: commit increases the epoch, rollback
does not. The pre-upgrade counter remains included and is never reset.

Bucket collisions still use normal SERIALIZABLE retry; this is not a claim of
lock-free writes. At most 64 additional rows are retained per owner/World.
"""

BUCKET_COUNT = 64
SUFFIX = ":pg-tx-v1:"


def write_key(expression):
    # A trigger already owns a writing transaction. The top-level XID remains
    # the same across savepoints, and is used only to select a bucket, never as
    # a visibility/commit-order token.
    return f"({expression}) || '{SUFFIX}' || mod(pg_current_xact_id()::text::numeric,{BUCKET_COUNT})::text"


def read_keys(scope_key):
    return [scope_key, *(f"{scope_key}{SUFFIX}{i}" for i in range(BUCKET_COUNT))]
