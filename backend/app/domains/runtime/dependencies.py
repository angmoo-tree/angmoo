"""Preserve HTTP override callables and read the configured diagnostics factory."""
from fastapi import Request
from app.api.identity_dependencies import get_current_user
from app.database import get_db
from app.domains.runtime.contracts.http import RuntimeStatusReaderFactory

def get_runtime_status_reader_factory(request: Request) -> RuntimeStatusReaderFactory:
    factory = getattr(request.app.state, "runtime_status_reader_factory", None)
    if not callable(factory):
        raise RuntimeError("runtime status reader factory is not configured")
    return factory
