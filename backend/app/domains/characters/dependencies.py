"""HTTP connection to the application-composed Character runtime callbacks."""
from fastapi import Request
from app.api.identity_dependencies import get_current_user
from app.core.db import get_db
from app.domains.characters.contracts import CharacterManagementWorkflows


def get_character_management_workflows(request: Request) -> CharacterManagementWorkflows:
    factory = getattr(request.app.state, "character_management_workflows", None)
    if not callable(factory):
        raise RuntimeError("character management workflows are not configured")
    return factory()
