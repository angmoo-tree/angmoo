"""Request-bound canonical readers supplied by the application's runtime."""
from fastapi import Depends, Request
from sqlalchemy.orm import Session
from app.api.identity_dependencies import get_current_user
from app.core.db import get_db
from app.config import settings
from app.domains.relationships.contracts.diagnostics import DiagnosticsReferences


def get_read_references(request: Request, db: Session = Depends(get_db)) -> DiagnosticsReferences:
    factory = getattr(request.app.state, "relationships_read_references_factory", None)
    if factory is None:
        raise RuntimeError("relationships read references are not configured")
    runtime_settings = getattr(request.app.state, "runtime_settings", settings)
    return factory(db, runtime_settings)
