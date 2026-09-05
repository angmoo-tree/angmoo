"""Shared error identities; callers retain their own HTTP and retry contracts."""


class SqliteConcurrencyError(RuntimeError):
    reason_code = "sqlite_concurrency_error"


class SqliteBusyRetryExhausted(SqliteConcurrencyError):
    reason_code = "sqlite_busy_retry_exhausted"


class SqliteTaskQueueFull(SqliteConcurrencyError):
    reason_code = "sqlite_task_queue_full"


class RequestBodyTooLargeError(Exception):
    pass
