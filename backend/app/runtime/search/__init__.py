"""Search-index adapters composed by the current or embedded runtime."""

from app.runtime.search.callback_index import CallbackSearchIndexAdapter
from app.runtime.search.sqlite_fts5 import (
    SqliteFts5Error,
    SqliteFts5SchemaError,
    SqliteFts5SearchIndex,
    SqliteFts5Settings,
)
from app.runtime.search.social_projection import EmbeddedSocialSearchProjection

__all__ = [
    "CallbackSearchIndexAdapter",
    "EmbeddedSocialSearchProjection",
    "SqliteFts5Error",
    "SqliteFts5SchemaError",
    "SqliteFts5SearchIndex",
    "SqliteFts5Settings",
]
