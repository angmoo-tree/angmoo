"""Tree HTTP uses the existing authentication and session dependency objects."""

from fastapi import Request
from app.api.identity_dependencies import get_current_user
from app.core.db import get_db
from app.domains.tree.contracts import TreeReferences


def get_tree_references(request: Request) -> TreeReferences:
    factory = getattr(request.app.state, "tree_references", None)
    if not callable(factory):
        raise RuntimeError("tree references are not configured")
    return factory()
