"""Search-index adapters composed by the current or embedded runtime."""

from app.runtime.search.callback_index import CallbackSearchIndexAdapter
from app.runtime.search.sqlite_fts5 import (
    SqliteFts5Error,
    SqliteFts5SchemaError,
    SqliteFts5SearchIndex,
    SqliteFts5Settings,
)

__all__ = [
    "CallbackSearchIndexAdapter",
    "SqliteFts5Error",
    "SqliteFts5SchemaError",
    "SqliteFts5SearchIndex",
    "SqliteFts5Settings",
]
