"""Real Social/World HTTP on isolated file SQLite. Auth only is synthetic."""
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import socket
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend"), str(ROOT / "backend/tests")]
import uvicorn
from fastapi import FastAPI
from sqlalchemy import func, select, update
from model_fixture_support import models
from social.test_world_user_notifications import USER, clone_world_profiles, seed_world_activity, _session_factory
from social.test_l4_social_write_uow import _user
from app.config import settings
from app.database import get_db
from app.domains.identity.dependencies import get_current_user
from app.domains.social.router import router as social_router, manual_router
from app.domains.world_characters.router.profile import router as profile_router
from app.domains.device_home.router import router as home_router
from app.runtime.social.composition import configure_social_runtime

settings.BROWSER_SESSION_ALLOWED_ORIGINS = ",".join(f"http://127.0.0.1:{port}" for port in (3000, 3393, 3394, 3395))
temporary = TemporaryDirectory(prefix="angmoo-world-notifications-")
factory = _session_factory(Path(temporary.name))
with factory() as db:
    db.add(_user("unrelated-user"))
    db.commit()
selected = {}
for world_id in ("world-feed-alpha", "world-feed-beta"):
    clone_world_profiles(factory, world_id)
    selected[world_id] = seed_world_activity(factory, world_id, key=world_id)
app = FastAPI()
configure_social_runtime(app)
for router in (social_router, manual_router, profile_router, home_router):
    app.include_router(router, prefix="/api/v1")
principal = {"id": USER}
requests, outbound = [], []

def database():
    with factory() as db:
        yield db

app.dependency_overrides[get_db] = database
app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=principal["id"])
connect = socket.socket.connect
def loopback_only(sock, address):
    if isinstance(address, tuple) and address[0] not in {"127.0.0.1", "::1", "localhost"}:
        outbound.append("external_connection_rejected")
        raise RuntimeError("fixture_external_network_forbidden")
    return connect(sock, address)
socket.socket.connect = loopback_only

@app.middleware("http")
async def audit(request, call_next):
    response = await call_next(request)
    if request.url.path.startswith("/api/v1/"):
        requests.append({"method": request.method, "path": request.url.path, "status": response.status_code})
    return response

@app.post("/fixture/principal/{identity}")
def change_principal(identity: str):
    principal["id"] = USER if identity == "owner" else "unrelated-user"
    return {"id": principal["id"]}

@app.post("/fixture/reset")
def reset_synthetic_reads():
    with factory() as db:
        db.execute(update(models.Notification).values(read_at=None))
        db.commit()
    requests.clear()
    return {"reset": True}

@app.get("/fixture/evidence")
def evidence():
    with factory() as db:
        return {"selected": selected, "requests": requests, "outbound": outbound,
            "db_kind": "isolated_file_sqlite_with_foreign_keys", "provider_calls": 0,
            "notifications": [{"id": n.id, "world": n.world_id, "recipient": n.recipient_world_character_id,
                "read": n.read_at is not None, "handled": n.handled_at is not None} for n in db.scalars(select(models.Notification))],
            "foreign_key_violations": [list(row) for row in db.connection().exec_driver_sql("PRAGMA foreign_key_check")],
            "relationship_count": db.scalar(select(func.count(models.RelationshipState.id)))}

if __name__ == "__main__":
    try:
        uvicorn.run(app, host="127.0.0.1", port=3394, log_level="warning")
    finally:
        factory.kw["bind"].dispose()
        temporary.cleanup()
