"""Supported authentication and local mutation fences for domain HTTP routes."""
from app.domains.identity.dependencies import get_current_user
from fastapi import Request
from app.domains.identity.browser_session import require_local_frontend_request as _require_frontend


def require_local_frontend_request(request: Request) -> None:
    _require_frontend(request, mutation=True)
