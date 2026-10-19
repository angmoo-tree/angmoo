from concurrent.futures import ThreadPoolExecutor
import asyncio
from datetime import UTC, datetime, timedelta

import pytest
import httpx
from fastapi import FastAPI
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import Session

from app.core import security
from app.domains.identity.models import AuthSession, InstallationIdentity, LocalClientConnection, User
from app.domains.identity.schemas_local_entry import LocalClientRequest, LocalPrepareRequest
from app.domains.identity.service.auth import get_session_for_token
from app.domains.identity.service.local_entry import LocalEntryError, LocalEntryService
from app.domains.identity.service.local_owner import LocalIdentityService
from app.runtime.persistence.model_registration import register_models
from app.runtime.persistence.sqlite_schema import build_sqlite_baseline_metadata, build_sqlite_v39_metadata, create_schema_version_table, sqlite_schema_contract_digest
from app.runtime.migrations.sqlite_versions.registry import load_sqlite_manifest
from app.runtime.migrations.sqlite_versions import local_client_v40


@pytest.fixture
def engine(tmp_path):
    register_models()
    engine = create_engine(f"sqlite:///{tmp_path / 'entry.sqlite'}", connect_args={"check_same_thread": False})
    build_sqlite_baseline_metadata().create_all(engine)
    yield engine
    engine.dispose()


def setup_request(engine, language="en-US"):
    with Session(engine) as db:
        service = LocalIdentityService(db)
        installation = service.ensure_local_installation_identity()
        challenge = service.create_bootstrap_challenge().token
    return LocalPrepareRequest(protocol=2, installation_id=installation, client_instance_id="synthetic-client-01",
        expected_generation=0, preferred_language=language), challenge


@pytest.mark.parametrize(("language", "name"), [("en-US", "User"), ("en-GB", "User"), ("ko-KR", "사용자"), ("ja-JP", "User")])
def test_prepare_stop_resume_preserves_owner_and_other_client(engine, language, name):
    data, challenge = setup_request(engine, language)
    with Session(engine) as db:
        issued = LocalEntryService(db).prepare(data, challenge_token=challenge, secret_ready=True)
        assert issued.user.display_name == name
        other = data.model_copy(update={"client_instance_id": "synthetic-client-02"})
        second = LocalEntryService(db).issue(other, secret_ready=True)
        stopped = LocalEntryService(db).stop(data, current_token=issued.token)
        assert (stopped.state, stopped.generation) == ("stopped", 1)
        assert get_session_for_token(db, issued.token) is None
        assert get_session_for_token(db, second.token) is not None
        db.rollback()
        assert LocalEntryService(db).stop(data).generation == 1
        with pytest.raises(LocalEntryError, match="local_client_stopped"):
            LocalEntryService(db).issue(data, secret_ready=True)
        resumed = LocalEntryService(db).resume(data.model_copy(update={"expected_generation": 1}), secret_ready=True)
        assert resumed.user.user_id == issued.user.user_id
        with pytest.raises(LocalEntryError, match="local_client_revision_conflict"):
            LocalEntryService(db).stop(data)
        assert get_session_for_token(db, resumed.token) is not None
        assert db.scalar(select(func.count()).select_from(User)) == 1


def test_stop_before_prepare_blocks_delayed_creation(engine):
    data, challenge = setup_request(engine)
    with Session(engine) as db:
        LocalEntryService(db).stop(data)
        with pytest.raises(LocalEntryError, match="local_client_stopped"):
            LocalEntryService(db).prepare(data, challenge_token=challenge, secret_ready=True)
        assert db.scalar(select(func.count()).select_from(User)) == 0


def test_parallel_prepare_creates_one_owner(engine):
    data, challenge = setup_request(engine)
    def prepare(_):
        with Session(engine) as db:
            return LocalEntryService(db).prepare(data, challenge_token=challenge, secret_ready=True).user.user_id
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert len(set(pool.map(prepare, range(2)))) == 1
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(User)) == 1
        assert db.scalar(select(func.count()).select_from(LocalClientConnection)) == 1


def test_existing_deleted_user_is_not_fresh(engine):
    data, challenge = setup_request(engine)
    with Session(engine) as db:
        db.add(User(id="old-user", display_name="Old", display_name_normalized="old", deleted_at=datetime.now(UTC)))
        db.commit()
        with pytest.raises(LocalEntryError, match="legacy_owner_selection_required"):
            LocalEntryService(db).prepare(data, challenge_token=challenge, secret_ready=True)
        assert db.scalar(select(func.count()).select_from(User)) == 1


def test_expiry_and_legacy_adoption_do_not_extend_ttl(engine):
    data, challenge = setup_request(engine)
    with Session(engine) as db:
        issued = LocalEntryService(db).prepare(data, challenge_token=challenge, secret_ready=True)
        legacy = AuthSession(token_hash=security.hash_token("legacy-token"), user_id=issued.user.user_id,
            auth_method="local_owner", created_at=datetime.now(UTC), expires_at=datetime.now(UTC) + timedelta(days=1))
        expires = legacy.expires_at
        db.add(legacy); db.commit()
        adopted = LocalEntryService(db).issue(data, secret_ready=True, current_token="legacy-token")
        assert adopted.token == "legacy-token"
        assert adopted.expires_at.replace(tzinfo=UTC) == expires
        db.expire_all()
        session = db.get(AuthSession, legacy.token_hash)
        assert session.local_client_id is not None
        session.expires_at = datetime.now(UTC) - timedelta(seconds=1); db.commit()
        assert get_session_for_token(db, "legacy-token") is None


def test_writer_refuses_caller_transaction(engine):
    data, challenge = setup_request(engine)
    with Session(engine) as db:
        db.add(User(id="pending", display_name="Pending", display_name_normalized="pending"))
        db.flush()
        with pytest.raises(RuntimeError, match="requires_clean"):
            LocalEntryService(db).prepare(data, challenge_token=challenge, secret_ready=True)
        assert db.get(User, "pending") is not None


@pytest.mark.parametrize("phase", ["user_flush", "binding", "session", "commit"])
def test_prepare_failure_rolls_back_entire_owner_and_session(engine, monkeypatch, phase):
    data, challenge = setup_request(engine)
    with Session(engine) as db:
        service = LocalEntryService(db)
        if phase == "user_flush":
            original = LocalIdentityService._select_or_create_owner
            def fail_owner(self, **kwargs):
                original(self, **kwargs)
                raise RuntimeError("synthetic_prepare_failure")
            monkeypatch.setattr(LocalIdentityService, "_select_or_create_owner", fail_owner)
        elif phase == "commit":
            def fail_commit():
                db.flush()
                raise RuntimeError("synthetic_prepare_failure")
            monkeypatch.setattr(db, "commit", fail_commit)
        else:
            original_issue = service._issue
            def fail_issue(owner, client, now):
                if phase == "session":
                    original_issue(owner, client, now)
                raise RuntimeError("synthetic_prepare_failure")
            monkeypatch.setattr(service, "_issue", fail_issue)
        with pytest.raises(RuntimeError, match="synthetic_prepare_failure"):
            service.prepare(data, challenge_token=challenge, secret_ready=True)
    with Session(engine) as check:
        assert check.scalar(select(func.count()).select_from(User)) == 0
        assert check.scalar(select(func.count()).select_from(AuthSession)) == 0
        assert check.scalar(select(func.count()).select_from(LocalClientConnection)) == 0
        identity = check.scalar(select(InstallationIdentity))
        assert identity.owner_user_id is None and identity.bootstrap_state == "unclaimed"


def test_authenticated_reads_are_bounded_and_never_write(engine):
    data, challenge = setup_request(engine)
    with Session(engine) as db:
        token = LocalEntryService(db).prepare(data, challenge_token=challenge, secret_ready=True).token
    statements = []
    def record(_conn, _cursor, sql, _params, _context, _many):
        statements.append(sql.split()[0].upper())
    event.listen(engine, "before_cursor_execute", record)
    try:
        for _ in range(10):
            with Session(engine) as db:
                assert get_session_for_token(db, token) is not None
        assert statements and set(statements) == {"SELECT"}
        assert len(statements) <= 30
        print(f"authenticated_read_measurements=requests:10,selects:{len(statements)},writes:0")
    finally:
        event.remove(engine, "before_cursor_execute", record)


def test_v39_upgrade_matches_new_schema_and_preserves_sessions():
    register_models()
    engine = create_engine("sqlite://")
    with engine.begin() as db:
        build_sqlite_v39_metadata().create_all(db)
        create_schema_version_table(db)
        assert sqlite_schema_contract_digest(db) == load_sqlite_manifest(39).schema_digest
        db.exec_driver_sql("INSERT INTO users(id,display_name,display_name_normalized,profile_setup_completed,is_admin,feed_content_filter) VALUES ('owner','Old','old',1,0,'all')")
        db.exec_driver_sql("INSERT INTO auth_sessions(token_hash,user_id,auth_method) VALUES ('old-token-hash','owner','local_owner')")
        before = local_client_v40.capture_delta(db)
        local_client_v40.upgrade(db)
        local_client_v40.verify_delta(db, before)
        assert sqlite_schema_contract_digest(db) == load_sqlite_manifest(40).schema_digest
        assert not db.exec_driver_sql("PRAGMA foreign_key_check").fetchall()
        assert db.exec_driver_sql("SELECT user_id FROM auth_sessions").scalar_one() == "owner"
    engine.dispose()


def test_local_http_protocol_cookies_and_origin_protection(engine, monkeypatch):
    from app.database import get_db
    from app.config import settings
    from app.domains.identity.router.local import router
    from app.domains.identity.router.auth import public_router
    from app.domains.identity.browser_session import SESSION_COOKIE_NAME
    from pydantic import SecretStr
    monkeypatch.setattr(settings, "APP_SECRET", SecretStr("synthetic-local-test-secret"))
    monkeypatch.setattr(settings, "APP_SECRET_FILE", None)
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    app.include_router(public_router, prefix="/api/v1")
    def session():
        with Session(engine) as db:
            yield db
    app.dependency_overrides[get_db] = session
    origin = "http://127.0.0.1:3000"
    headers = {"Origin": origin, "Host": "127.0.0.1:3000", "X-Angmoo-Frontend-Origin": origin}
    async def scenario():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=origin, headers=headers) as client:
            assert (await client.post("/api/v1/auth/local/session")).status_code == 409
            assert (await client.post("/api/v1/auth/local/bootstrap/challenge", headers={"Origin": "https://untrusted.invalid"})).status_code == 403
            challenge = await client.post("/api/v1/auth/local/bootstrap/challenge")
            assert challenge.status_code == 201
            assert "HttpOnly" in challenge.headers["set-cookie"]
            boot = (await client.get("/api/v1/auth/local/bootstrap")).json()
            assert boot["protocol"] == 2 and boot["automatic_prepare_allowed"]
            data = dict(protocol=2, installation_id=boot["installation_id"], client_instance_id="synthetic-http-client", expected_generation=0)
            client_state = await client.get("/api/v1/auth/local/client", params=data)
            assert client_state.status_code == 200, client_state.text
            assert client_state.json()["state"] == "active"
            assert (await client.get("/api/v1/auth/local/client", params={**data, "protocol": 1})).status_code == 422
            prepared = await client.post("/api/v1/auth/local/bootstrap/prepare", json={**data, "preferred_language": "en-US"})
            assert prepared.status_code == 200, prepared.text
            assert prepared.json()["user"]["display_name"] == "User"
            token = client.cookies[SESSION_COOKIE_NAME]
            assert token not in prepared.text
            assert "HttpOnly" in prepared.headers["set-cookie"]
            bound = (await client.get("/api/v1/auth/local/bootstrap")).json()["client_connection"]
            assert bound["generation"] == 0
            stopped = await client.post("/api/v1/auth/local/client/stop", json=data)
            assert stopped.json()["state"] == "stopped"
            assert (await client.post("/api/v1/auth/local/session", json=data)).status_code == 409
            resumed = await client.post("/api/v1/auth/local/client/resume", json={**data, "expected_generation": 1})
            assert resumed.status_code == 200
            assert (await client.get("/api/v1/auth/me")).status_code == 200
            client.cookies.set(SESSION_COOKIE_NAME, token, domain="127.0.0.1", path="/api")
            assert (await client.get("/api/v1/auth/me")).status_code == 401
    asyncio.run(scenario())
