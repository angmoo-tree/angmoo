"""Loopback-only real environment API over disposable SQLite for browser tests."""
from datetime import UTC, datetime, timedelta
from pathlib import Path
import sys
import tempfile

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/"backend"))
from fastapi import FastAPI
from sqlalchemy import create_engine, delete
from sqlalchemy.orm import Session
from app.config import settings
from app.core.security import hash_token
from app.database import get_db
from app.domains.identity.models import User, AuthSession, InstallationIdentity
from app.domains.identity.models_environment import LocalEnvironment, EnvironmentTimezoneChange
from app.domains.identity.router.local import router
from app.domains.identity.service import environment as environment_service
from app.runtime.persistence.model_registration import register_models

settings.APP_ENV="test"
settings.BROWSER_SESSION_ALLOWED_ORIGINS="http://127.0.0.1:3000"
workspace=tempfile.TemporaryDirectory(prefix="angmoo-home-environment-")
engine=create_engine(f"sqlite:///{Path(workspace.name)/'environment.sqlite3'}")
register_models().create_all(engine)
with Session(engine) as db:
    db.add(User(id="local-owner",display_name="Local Owner",profile_setup_completed=True,ui_language="ko"))
    db.flush()
    db.add(InstallationIdentity(singleton_key="local-installation",installation_id="synthetic",owner_user_id="local-owner",bootstrap_state="claimed",claimed_at=datetime.now(UTC)))
    for number in (1,2):
        db.add(AuthSession(token_hash=hash_token(f"synthetic-browser-{number}"),user_id="local-owner",auth_method="local",created_at=datetime.now(UTC),expires_at=datetime.now(UTC)+timedelta(hours=1)))
    db.commit()
app=FastAPI()
app.include_router(router,prefix="/api/v1")

class FixtureClock(datetime):
    offset = timedelta()

    @classmethod
    def now(cls, tz=None):
        return super().now(tz) + cls.offset

environment_service.datetime = FixtureClock
def database():
    with Session(engine) as db:yield db
app.dependency_overrides[get_db]=database

@app.get("/_test/health")
def health():return {"ready":True}

@app.post("/_test/reset")
def reset():
    FixtureClock.offset = timedelta()
    with Session(engine) as db:
        db.execute(delete(EnvironmentTimezoneChange));db.execute(delete(LocalEnvironment));db.commit()
    return {"ready":True}

@app.post("/_test/advance-clock")
def advance_clock(seconds: int):
    assert 0 <= seconds <= 300
    FixtureClock.offset += timedelta(seconds=seconds)
    return {"ready": True}

if __name__=="__main__":
    import uvicorn
    try:uvicorn.run(app,host="127.0.0.1",port=3483,log_level="warning")
    finally:engine.dispose();workspace.cleanup()
