"""Real local identity/environment/World HTTP paths; disposable SQLite, no workers/AI."""
from datetime import UTC, datetime, timedelta
import asyncio
from pathlib import Path
from dataclasses import replace
import base64
import io
import json
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))
from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import SecretStr
from sqlalchemy import create_engine, select, update
from sqlalchemy.orm import Session
from app.config import settings
from app.database import get_db
from app.domains.identity.models import User, AuthSession, LocalClientConnection, InstallationIdentity
from app.domains.identity.models_world_credentials import WorldCredential
from app.domains.routines.models import AgentActivitySetting
from app.domains.identity.models_environment import LocalEnvironment
from app.domains.identity.router.local import router as local_router
from app.domains.identity.router.auth import public_router
from app.domains.worlds.router import router as worlds_router
from app.domains.device_home.router import router as home_router
from app.domains.world_characters.router.profile import router as profile_router
from app.domains.world_characters.router.management import router as management_router
from app.domains.characters.router import router as character_router
from app.runtime.characters.creator import build_creator_workflows
from app.domains.characters.models import CharacterRegistrationReceipt
from app.domains.worlds.models import World
from app.domains.world_characters.models import WorldCharacter
from app.domains.world_characters.configuration_models import WorldCharacterConfiguration
from app.runtime.persistence.model_registration import register_models

workspace = tempfile.TemporaryDirectory(prefix="angmoo-entry-browser-")
settings.APP_ENV = "test"
settings.APP_SECRET = SecretStr("synthetic-browser-entry-secret")
settings.APP_SECRET_FILE = None
settings.MEDIA_ROOT = str(Path(workspace.name) / "media")
settings.BROWSER_SESSION_ALLOWED_ORIGINS = "http://127.0.0.1:3490,http://127.0.0.1:3491"
settings.DESKTOP_ALLOWED_ORIGIN = "http://127.0.0.1:3491"
settings.DESKTOP_LAUNCH_TOKEN = SecretStr("synthetic-desktop-launch-token-000000000000")
engine = create_engine(f"sqlite:///{Path(workspace.name) / 'entry.sqlite'}", connect_args={"check_same_thread": False})
metadata = register_models()
metadata.create_all(engine)
app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["http://127.0.0.1:3491"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
for router in (local_router, public_router, home_router, worlds_router, profile_router, character_router, management_router):
    app.include_router(router, prefix="/api/v1")
def forbidden_ai(**kwargs):
    raise AssertionError("Local entry/registration must not invoke AI")
app.state.creator_workflows = lambda: replace(build_creator_workflows(), run_llm=forbidden_ai)

def database():
    with Session(engine) as db:
        yield db
app.dependency_overrides[get_db] = database
requests = []
gate = {"path": None, "entered": False, "release": None}

@app.middleware("http")
async def record(request, call_next):
    response = await call_next(request)
    if request.url.path.startswith("/api/"):
        requests.append({"method": request.method, "path": request.url.path, "status": response.status_code})
    if gate["path"] == request.url.path and request.method == "POST":
        gate["path"] = None
        gate["entered"] = True
        await asyncio.wait_for(gate["release"].wait(), timeout=20)
    return response

@app.get("/_test/health")
def health():
    return {"ready": True}

@app.get("/_test/card")
def card():
    from PIL import Image, PngImagePlugin
    metadata = PngImagePlugin.PngInfo()
    metadata.add_text("chara", base64.b64encode(json.dumps({"spec": "chara_card_v2", "spec_version": "2.0", "data": {
        "name": "Synthetic Ian", "description": "A quiet writer who shares stories about trail walks.", "personality": "Calm",
        "scenario": "", "first_mes": "Hello", "mes_example": "", "system_prompt": "", "character_book": {"entries": []},
    }}).encode()).decode())
    output = io.BytesIO(); Image.new("RGB", (32, 32), "skyblue").save(output, "PNG", pnginfo=metadata)
    return Response(output.getvalue(), media_type="image/png")

@app.post("/_test/reset")
def reset():
    metadata.drop_all(engine)
    metadata.create_all(engine)
    requests.clear()
    return {"ready": True}

@app.post("/_test/expire")
def expire():
    with Session(engine) as db:
        db.execute(update(AuthSession).values(expires_at=datetime.now(UTC) - timedelta(seconds=1)))
        db.commit()
    return {"ready": True}

@app.post("/_test/hold/{operation}")
async def hold(operation: str):
    assert operation in {"issue", "stop"}
    gate.update(path="/api/v1/auth/local/" + ("session" if operation == "issue" else "client/stop"), entered=False, release=asyncio.Event())
    return {"ready": True}

@app.post("/_test/release")
async def release():
    gate["release"].set()
    return {"ready": True}

@app.get("/_test/state")
def state():
    with Session(engine) as db:
        return {
            "users": [{"id": x.id, "name": x.display_name} for x in db.scalars(select(User))],
            "worlds": [{"id": x.id, "language": x.language, "timezone": x.timezone} for x in db.scalars(select(World))],
            "profiles": [{"id": x.world_character_id, "name": x.profile["display_name"]} for x in db.scalars(select(WorldCharacterConfiguration).join(WorldCharacter, WorldCharacter.id == WorldCharacterConfiguration.world_character_id).where(WorldCharacter.control_mode == "owner_controlled"))],
            "clients": [{"state": x.state, "generation": x.generation} for x in db.scalars(select(LocalClientConnection))],
            "client_request": next(({"protocol": 2, "installation_id": x.installation_id, "client_instance_id": x.client_instance_id, "expected_generation": x.generation} for x in db.scalars(select(LocalClientConnection))), None),
            "installation_label": db.scalar(select(InstallationIdentity.local_label)),
            "gate_entered": gate["entered"],
            "registrations": [{"character_id": x.character_id, "world_id": db.get(WorldCharacter, x.world_character_id).world_id, "world_character_id": x.world_character_id,
                "autonomous_enabled": bool(db.scalar(select(AgentActivitySetting.auto_enabled).where(AgentActivitySetting.character_id == x.character_id)))} for x in db.scalars(select(CharacterRegistrationReceipt))],
            "credentials": [{"purpose": x.purpose, "revision": x.revision, "has_key": bool(x.encrypted_secret)} for x in db.scalars(select(WorldCredential))],
            "requests": list(requests),
        }

if __name__ == "__main__":
    import uvicorn
    try:
        uvicorn.run(app, host="127.0.0.1", port=3492, log_level="warning")
    finally:
        engine.dispose()
        workspace.cleanup()
