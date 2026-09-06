"""Connect Memory HTTP to the application's configured runtime collaborators."""
from fastapi import Request

from app.database import get_db
from app.api.identity_dependencies import get_current_user
from app.domains.memory.contracts.management import MemoryWorkflows


def get_memory_workflows(request: Request) -> MemoryWorkflows:
    factory = getattr(request.app.state, "memory_workflows", None)
    if not callable(factory):
        raise RuntimeError("memory workflows are not configured")
    return factory()
