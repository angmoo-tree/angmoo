"""An accepted intent closes ordinary World HTTP entry points immediately."""
import re
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from app.domains.worlds.service.deletion import deletion_for_world
from app.domains.identity.dependencies import get_current_user
from fastapi import HTTPException


class WorldDeletionHttpGate(BaseHTTPMiddleware):
    def __init__(self, app, *, sessions):
        super().__init__(app)
        self.sessions = sessions

    async def dispatch(self, request, call_next):
        match = re.match(r"^(?:/api/v1/(?:media/)?worlds|/media/worlds)/([A-Za-z0-9_-]+)(?:/|$)", request.url.path)
        root_delete = match and request.method == "DELETE" and request.url.path.rstrip("/").endswith("/" + match.group(1))
        if match and not request.url.path.endswith("/deletion-preview") and not root_delete:
            # A short read runs off the event loop; no Session spans downstream IO.
            import asyncio
            def blocked():
                with self.sessions() as db:
                    deletion = deletion_for_world(db, match.group(1))
                    if deletion is None:
                        return None
                    try:
                        user = get_current_user(request, request.headers.get("Authorization"), db)
                    except HTTPException as exc:
                        if request.method in {"GET", "HEAD"}:
                            return 404, "world_not_found"
                        return exc.status_code, exc.detail
                    if deletion.owner_id != user.id:
                        return 404, "world_not_found"
                    return (410, "world_deleted") if deletion.state == "completed" else (409, "world_deleting")
            result = await asyncio.to_thread(blocked)
            if result:
                return JSONResponse({"detail": result[1]}, status_code=result[0])
        return await call_next(request)
