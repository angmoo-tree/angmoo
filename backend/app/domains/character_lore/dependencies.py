"""Keep authentication/session dependency identity and explicit Lore composition."""

from fastapi import Request

from app.api.identity_dependencies import get_current_user
from app.database import get_db
from app.domains.character_lore.contracts import LoreWorkflows


def get_lore_workflows(request: Request) -> LoreWorkflows:
    factory = getattr(request.app.state, "lore_workflows", None)
    if not callable(factory):
        raise RuntimeError("lore workflows are not configured")
    return factory()
