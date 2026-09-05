from fastapi import Request
from app.api.identity_dependencies import get_current_user
from app.core.db import get_db
from app.domains.local_bot.contracts.key_management import LocalKeyWorkflows


def get_local_key_workflows(request: Request) -> LocalKeyWorkflows:
    factory = getattr(request.app.state, "local_key_workflows", None)
    if not callable(factory):
        raise RuntimeError("LocalBot key workflows are not configured")
    return factory()
