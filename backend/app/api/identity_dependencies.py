"""Common HTTP identity dependencies shared by domain routers.

These exports retain the exact FastAPI override callables and cookie implementation.
Business services use identity service/contracts instead of this HTTP connection.
"""
from app.domains.identity import browser_session
from app.domains.identity.dependencies import (
    AuthenticatedSessionContext,
    get_current_user,
    get_current_user_allow_incomplete,
    get_current_session_for_logout,
    get_optional_current_user,
    resolve_authenticated_session_context,
)
