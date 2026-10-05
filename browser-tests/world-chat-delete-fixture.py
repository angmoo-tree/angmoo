"""File SQLite and the real World Chat routers; no user DB or provider calls."""
from pathlib import Path
import os
import sys
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend"), str(ROOT / "backend/tests")]

from fastapi import FastAPI
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import Session
import uvicorn
from model_fixture_support import models
from chat.test_p8_l_d_world_chat_api import _seed
from app.database import get_db
from app.domains.identity.dependencies import get_current_user
from app.config import settings
from app.models import Base
from app.domains.chat import schemas
from app.domains.chat.router.world_chat import router as thread_router
from app.domains.chat.router.world_chat_response import router as response_router
from app.runtime.chat.message_composition import configure_chat_services

PORT = int(os.environ.get("ANGMOO_CHAT_DELETE_FIXTURE_PORT", "3354"))
settings.BROWSER_SESSION_ALLOWED_ORIGINS = "http://127.0.0.1:3000,http://127.0.0.1:3336,http://127.0.0.1:3337,http://127.0.0.1:3338,http://127.0.0.1:3340,http://127.0.0.1:3353,http://127.0.0.1:3355"
temporary = TemporaryDirectory(prefix="angmoo-chat-delete-")
engine = create_engine(f"sqlite:///{Path(temporary.name) / 'chat.sqlite3'}", connect_args={"check_same_thread": False})

@event.listens_for(engine, "connect")
def foreign_keys(connection, _):
    connection.execute("PRAGMA foreign_keys=ON")

Base.metadata.create_all(engine)
principal = {"user": None}
owner, _outsider, responding_id = _seed(engine, principal)
app = FastAPI()
configure_chat_services(app)
app.include_router(thread_router, prefix="/api/v1")
app.include_router(response_router, prefix="/api/v1")

def database():
    with Session(engine) as db:
        yield db

app.dependency_overrides[get_db] = database
app.dependency_overrides[get_current_user] = lambda: owner
with Session(engine) as db:
    initial = app.state.chat_thread_service.create_or_get_world_thread(db, owner, "world-a",
        schemas.WorldChatThreadCreate(responding_world_character_id=responding_id)).thread
    db.add(models.MessageMessage(thread_id=initial.id, role="user", status="ok", content="Synthetic retained original message"))
    db.commit()
initial_id = initial.id
requests = []

@app.middleware("http")
async def audit(request, call_next):
    response = await call_next(request)
    if "/chat/" in request.url.path:
        requests.append({"method": request.method, "path": request.url.path, "status": response.status_code})
    return response

@app.get("/fixture/evidence")
def evidence():
    with Session(engine) as db:
        return {"world_id": "world-a", "thread_id": initial_id, "responding_id": responding_id,
            "requests": requests, "db_kind": "isolated_file_sqlite_with_foreign_keys", "provider_calls": 0,
            "threads": [{"id": row.id, "deleted": row.deleted_at is not None} for row in db.scalars(select(models.MessageThread))],
            "messages": [{"id": row.id, "thread_id": row.thread_id} for row in db.scalars(select(models.MessageMessage))],
            "response_count": db.scalar(select(func.count(models.ChatResponseRequest.request_id))),
            "foreign_key_violations": [list(row) for row in db.connection().exec_driver_sql("PRAGMA foreign_key_check")],
        }

if __name__ == "__main__":
    try:
        uvicorn.run(app, host="127.0.0.1", port=PORT, log_level="warning")
    finally:
        engine.dispose()
        temporary.cleanup()
