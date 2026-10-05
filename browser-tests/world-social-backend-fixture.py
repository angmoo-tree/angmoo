"""Loopback-only product-router fixture. No user DB, worker, or credentials."""
from pathlib import Path
import socket
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend"), str(ROOT / "backend/tests")]

from sqlalchemy import func, select
from sqlalchemy.orm import Session
import uvicorn
from fastapi import FastAPI

from model_fixture_support import models
from social.test_world_selected_thread_and_reactions import setup
from app.domains.device_home.router import router as device_home_router
from app.config import settings

settings.BROWSER_SESSION_ALLOWED_ORIGINS = "http://127.0.0.1:3000,http://127.0.0.1:3340"
client, engine, principal = setup()
client.app.include_router(device_home_router, prefix="/api/v1")
with Session(engine) as db:
    db.get(models.World, "world-manual").readiness_status = "publish_ready"
    db.commit()
app = FastAPI()
requests = []
outbound = []
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
    if "manual-social" in request.url.path:
        requests.append({"method": request.method, "path": request.url.path,
                         "key": request.headers.get("idempotency-key"), "status": response.status_code})
    return response


@app.get("/fixture/evidence")
def evidence():
    with Session(engine) as db:
        owner = db.scalar(select(models.WorldCharacter.id).where(models.WorldCharacter.control_mode == "owner_controlled"))
        posts = list(db.scalars(select(models.Post)))
        events = list(db.scalars(select(models.SocialEvent)))
        inbox = list(db.scalars(select(models.OwnerManualInboxCandidate)))
        return {"owner": owner, "requests": requests,
                "posts": [{"id": row.id, "parent": row.reply_to_post_id, "body": row.body} for row in posts],
                "like_count": db.scalar(select(func.count(models.PostLike.id))),
                "events": [{"kind": row.event_type, "retrieval": row.retrieval_status} for row in events],
                "inbox": [{"target": row.target_post_id, "recipient": row.target_world_character_id} for row in inbox],
                "relationship_count": db.scalar(select(func.count(models.RelationshipState.id))),
                "projection_count": db.scalar(select(func.count(models.GraphProjectionOutbox.id))),
                "outbound": outbound, "db_kind": "isolated_sqlite_with_foreign_keys"}


app.mount("/", client.app)

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=3342, log_level="warning")
