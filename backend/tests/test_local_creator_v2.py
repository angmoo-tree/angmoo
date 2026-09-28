import asyncio
from datetime import UTC, datetime
from dataclasses import replace

import pytest
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session

from app.runtime.persistence.model_registration import register_models
from app.runtime.persistence.sqlite_schema import build_sqlite_v20_metadata, create_schema_version_table, sqlite_schema_contract_digest
from app.runtime.migrations.sqlite_versions.registry import load_sqlite_manifest
from app.runtime.migrations.sqlite_versions import creator_v21
from app.domains.identity.models import User, InstallationIdentity
from app.domains.characters.models import Character, AgentCreationDraft, CharacterRegistrationReceipt
from app.domains.characters.schemas import AgentCreationDraftCreate, AgentCreationDraftUpdate, AgentCreationDraftComplete
from app.domains.characters.service import drafts
from app.domains.world_characters.models import WorldCharacter, CharacterWorldBinding
from app.domains.world_characters.service.autonomous_setup import preflight_setup
from app.domains.world_characters.schemas.identity import MyProfilePatch
from app.domains.world_characters.service.owner_identity import OwnerControlledIdentityService
from app.domains.worlds.contracts import NO_SPECIFIC_ROLE_KEY
from app.domains.worlds.service.default_space import ensure_default_space
from app.runtime.characters.creator import build_creator_workflows


@pytest.fixture
def db(tmp_path):
    metadata = register_models()
    engine = create_engine(f"sqlite:///{tmp_path / 'isolated.sqlite3'}")
    event.listen(engine, "connect", lambda con, _: con.execute("PRAGMA foreign_keys=ON"))
    metadata.create_all(engine)
    with Session(engine) as session:
        owner = User(id="test-owner", display_name="Owner")
        session.add(owner)
        session.flush()
        session.add(InstallationIdentity(singleton_key="local-installation", installation_id="test-installation",
            owner_user_id=owner.id, bootstrap_state="claimed", local_label="Test", claimed_at=datetime.now(UTC)))
        session.commit()
        yield session, owner
    engine.dispose()


def test_default_and_same_profile_identity(db):
    session, owner = db
    world = ensure_default_space(session, owner_id=owner.id)
    assert world.name == "SNS"
    assert world.readiness_status == "publish_ready"
    assert ensure_default_space(session, owner_id=owner.id).id == world.id
    service = OwnerControlledIdentityService(session)
    first = service.ensure(world_id=world.id, current_user_id=owner.id)
    assert first.profile.display_name == "사용자"
    assert first.profile.avatar_url is None
    assert service.ensure(world_id=world.id, current_user_id=owner.id).character_id == first.character_id
    changed = service.patch(world_id=world.id, current_user_id=owner.id,
        data=MyProfilePatch(version=first.version, display_name="하루", handle="haru", intro=""))
    assert (changed.character_id, changed.world_character_id) == (first.character_id, first.world_character_id)
    assert changed.profile.handle == "haru"
    assert changed.profile.background == first.profile.background


def test_keyless_registration_is_atomic_off_and_replayed(db, monkeypatch):
    session, owner = db
    async def forbidden(**kwargs):
        raise AssertionError("Registration must not call AI")
    workflows = replace(build_creator_workflows(), run_llm=forbidden)
    draft = asyncio.run(drafts.create_draft(session, owner, AgentCreationDraftCreate(), workflows=workflows))
    assert draft.contract_version == 2
    assert session.get(AgentCreationDraft, draft.id).encrypted_api_key is None
    changed = drafts.update_draft(session, owner, draft.id,
        AgentCreationDraftUpdate(revision=draft.revision, name="하루", worldview="호기심 많은 기자", personality="호기심 많은 기자"), workflows=workflows)
    # Detail presentation is independent of the atomic persistence contract.
    monkeypatch.setattr("app.runtime.characters.management.get_agent", lambda db, user, cid: db.get(Character, cid))
    data = AgentCreationDraftComplete(revision=changed.revision)
    first = drafts.complete_draft(session, owner, draft.id, data, workflows=workflows)
    again = drafts.complete_draft(session, owner, draft.id, data, workflows=workflows)
    assert first.id == again.id
    binding = session.get(CharacterWorldBinding, first.id)
    row = session.scalar(select(WorldCharacter).where(WorldCharacter.character_id == first.id))
    assert binding.world_id == row.world_id == draft.target_world_id
    assert row.role_key == NO_SPECIFIC_ROLE_KEY
    preflight = preflight_setup(session, world_character_id=row.id, user=owner)
    assert preflight.safe_reason_code == "credential_required"
    assert row.autonomous_enabled is False
    assert first.credential is None
    assert first.activity_setting.auto_enabled is False
    assert session.get(CharacterRegistrationReceipt, draft.id).character_id == first.id


def test_upgrade_preserves_legacy_draft_and_matches_fresh(tmp_path):
    register_models()
    engine = create_engine(f"sqlite:///{tmp_path / 'upgrade.sqlite3'}")
    with engine.begin() as connection:
        legacy = build_sqlite_v20_metadata()
        legacy.create_all(connection)
        create_schema_version_table(connection)
        assert sqlite_schema_contract_digest(connection) == load_sqlite_manifest(20).schema_digest
        connection.exec_driver_sql("INSERT INTO users (id, display_name) VALUES ('legacy-owner', '보존 사용자')")
        connection.execute(legacy.tables["agent_creation_drafts"].insert().values(id="legacy-draft", user_id="legacy-owner", provider="google", model="gemini-3.1-flash-lite", encrypted_api_key="preserved-ciphertext", expires_at=datetime(2026, 10, 1)))
        before = creator_v21.capture_delta(connection)
        creator_v21.upgrade(connection)
        creator_v21.verify_delta(connection, before)
        row = connection.exec_driver_sql("SELECT encrypted_api_key, contract_version, revision FROM agent_creation_drafts WHERE id='legacy-draft'").one()
        assert tuple(row) == ("preserved-ciphertext", 1, 1)
        assert sqlite_schema_contract_digest(connection) == load_sqlite_manifest(21).schema_digest
        assert not list(connection.exec_driver_sql("PRAGMA foreign_key_check"))
    engine.dispose()


def test_registration_detail_is_readable_without_credential(db):
    session, owner = db
    workflows = build_creator_workflows()
    draft = asyncio.run(drafts.create_draft(session, owner, AgentCreationDraftCreate(), workflows=workflows))
    edited = drafts.update_draft(session, owner, draft.id,
        AgentCreationDraftUpdate(revision=1, name="검증 앵무", worldview="차분하고 꼼꼼한 앵무", personality="차분하고 꼼꼼하다"), workflows=workflows)
    result = drafts.complete_draft(session, owner, draft.id, AgentCreationDraftComplete(revision=edited.revision), workflows=workflows)
    assert result.credential is None
    assert result.settings.auto_enabled is False
    assert result.character.name == "검증 앵무"


def test_stale_edit_and_profile_revision_preserve_current_values(db):
    from app.domains.characters.exceptions import AgentCreationDraftHandleConflictError
    from app.domains.world_characters.contracts.owner_identity import OwnerControlledIdentityConflictError
    session, owner = db
    workflows = build_creator_workflows()
    draft = asyncio.run(drafts.create_draft(session, owner, AgentCreationDraftCreate(), workflows=workflows))
    drafts.update_draft(session, owner, draft.id, AgentCreationDraftUpdate(revision=1, name="먼저 저장"), workflows=workflows)
    with pytest.raises(AgentCreationDraftHandleConflictError):
        drafts.update_draft(session, owner, draft.id, AgentCreationDraftUpdate(revision=1, name="오래된 요청"), workflows=workflows)
    assert session.get(AgentCreationDraft, draft.id).name == "먼저 저장"
    identity = OwnerControlledIdentityService(session)
    first = identity.ensure(world_id=draft.target_world_id, current_user_id=owner.id)
    identity.patch(world_id=draft.target_world_id, current_user_id=owner.id, data=MyProfilePatch(version=first.version, display_name="하루"))
    with pytest.raises(OwnerControlledIdentityConflictError):
        identity.patch(world_id=draft.target_world_id, current_user_id=owner.id, data=MyProfilePatch(version=first.version, display_name="이전"))
    assert identity.get(world_id=draft.target_world_id, current_user_id=owner.id).profile.display_name == "하루"


def test_registration_failure_rolls_back_character_and_membership(db, monkeypatch):
    session, owner = db
    workflows = build_creator_workflows()
    draft = asyncio.run(drafts.create_draft(session, owner, AgentCreationDraftCreate(), workflows=workflows))
    edited = drafts.update_draft(session, owner, draft.id, AgentCreationDraftUpdate(revision=1, name="롤백", worldview="차분한 앵무", personality="차분함"), workflows=workflows)
    def fail(*args, **kwargs):
        raise RuntimeError("injected activity setting write failure")
    monkeypatch.setattr("app.runtime.characters.registration.ensure_setting", fail)
    with pytest.raises(RuntimeError):
        drafts.complete_draft(session, owner, draft.id, AgentCreationDraftComplete(revision=edited.revision), workflows=workflows)
    assert session.scalar(select(Character).where(Character.name == "롤백")) is None
    assert session.scalar(select(WorldCharacter)) is None
    assert session.get(CharacterRegistrationReceipt, draft.id) is None
    assert session.get(AgentCreationDraft, draft.id).status == "editing"


def test_default_space_cannot_be_archived(db):
    from app.domains.worlds.service.creator import archive_world
    from app.domains.worlds.schemas import WorldMutationRequest
    from app.domains.worlds.exceptions import WorldDefinitionValidationError
    session, owner = db
    world = ensure_default_space(session, owner_id=owner.id)
    with pytest.raises(WorldDefinitionValidationError):
        archive_world(session, world_id=world.id, user=owner, data=WorldMutationRequest(row_version=world.row_version))
    assert world.status == "published"


def test_two_independent_sessions_register_one_draft_once(db):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from sqlalchemy import func
    session, owner = db
    workflows = build_creator_workflows()
    draft = asyncio.run(drafts.create_draft(session, owner, AgentCreationDraftCreate(), workflows=workflows))
    edited = drafts.update_draft(session, owner, draft.id, AgentCreationDraftUpdate(
        revision=1, name="동시 등록", worldview="침착한 앵무", personality="침착함"), workflows=workflows)
    draft_id, owner_id, revision = draft.id, owner.id, edited.revision
    session.commit()
    barrier = Barrier(2)
    def submit(_):
        with Session(session.get_bind()) as worker:
            actor = worker.get(User, owner_id)
            barrier.wait(timeout=10)
            return drafts.complete_draft(worker, actor, draft_id,
                AgentCreationDraftComplete(revision=revision), workflows=workflows).character.id
    with ThreadPoolExecutor(2) as pool:
        identities = list(pool.map(submit, range(2)))
    assert identities[0] == identities[1]
    session.expire_all()
    assert session.scalar(select(func.count()).select_from(CharacterRegistrationReceipt)) == 1
    assert session.scalar(select(func.count()).select_from(WorldCharacter)) == 1


def test_two_independent_sessions_ensure_same_space_and_profile(db):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    session, owner = db
    owner_id = owner.id
    session.commit()
    barrier = Barrier(2)
    def ensure(_):
        with Session(session.get_bind()) as worker:
            barrier.wait(timeout=10)
            world = ensure_default_space(worker, owner_id=owner_id)
            profile = OwnerControlledIdentityService(worker).ensure(world_id=world.id, current_user_id=owner_id)
            return world.id, profile.character_id, profile.world_character_id
    with ThreadPoolExecutor(2) as pool:
        identities = list(pool.map(ensure, range(2)))
    assert identities[0] == identities[1]


def test_legacy_draft_explicit_adoption_preserves_fields_and_never_attaches_key(db):
    from datetime import timedelta
    from app.domains.characters.schemas import AgentCreationDraftAdopt
    from app.domains.characters.exceptions import AgentCreationDraftValidationError
    session, owner = db
    legacy = AgentCreationDraft(id="legacy-resume", user_id=owner.id, provider="google",
        model="gemini-3.1-flash-lite", encrypted_api_key="preserved-private-ciphertext",
        name="보존 초안", personality="친절함", expires_at=datetime.now(UTC)+timedelta(days=1))
    session.add(legacy); session.commit()
    workflows = build_creator_workflows()
    with pytest.raises(AgentCreationDraftValidationError, match="이전 초안"):
        drafts.complete_draft(session, owner, legacy.id, workflows=workflows)
    result = drafts.adopt_legacy_draft(session, owner, legacy.id,
        AgentCreationDraftAdopt(revision=legacy.revision), workflows=workflows)
    assert result.name == "보존 초안" and result.contract_version == 2
    assert legacy.encrypted_api_key == "preserved-private-ciphertext"
    with pytest.raises(AgentCreationDraftValidationError, match="캐릭터 설명"):
        drafts.complete_draft(session, owner, legacy.id,
            AgentCreationDraftComplete(revision=result.revision), workflows=workflows)
    completed = drafts.update_draft(session, owner, legacy.id,
        AgentCreationDraftUpdate(revision=result.revision, worldview="친절한 보존 앵무"), workflows=workflows)
    registered = drafts.complete_draft(session, owner, legacy.id,
        AgentCreationDraftComplete(revision=completed.revision), workflows=workflows)
    assert registered.credential is None
    assert registered.settings.auto_enabled is False
    assert session.get(CharacterWorldBinding, registered.character.id).world_id == result.target_world_id


def test_expired_draft_get_is_read_only(db):
    from datetime import timedelta
    from app.domains.characters.exceptions import AgentCreationDraftExpiredError
    session, owner = db
    expired = AgentCreationDraft(id="expired-read", user_id=owner.id, provider="google", model="fixture",
        encrypted_api_key="preserved", expires_at=datetime.now(UTC)-timedelta(days=1))
    session.add(expired); session.commit()
    with pytest.raises(AgentCreationDraftExpiredError):
        drafts.get_draft(session, owner, expired.id, workflows=build_creator_workflows())
    assert session.get(AgentCreationDraft, "expired-read") is not None
    assert not session.deleted and not session.dirty


def test_http_keyless_register_replay_and_detail_use_real_persistence(db):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.domains.characters import router, dependencies
    session, owner = db
    app = FastAPI()
    from app.api.v1.routes.agents import router as product_router
    app.include_router(product_router, prefix="/api/v1")
    app.dependency_overrides[dependencies.get_db] = lambda: session
    app.dependency_overrides[dependencies.get_current_user] = lambda: owner
    app.state.creator_workflows = build_creator_workflows
    with TestClient(app) as client:
        created = client.post("/api/v1/agents/drafts", json={})
        assert created.status_code == 201, created.text
        draft = created.json()
        saved = client.patch(f"/api/v1/agents/drafts/{draft['id']}", json={
            "revision": draft["revision"], "name": "HTTP 앵무", "worldview": "다정하고 신중한 앵무", "personality": "다정하고 신중함"})
        assert saved.status_code == 200, saved.text
        payload = {"revision": saved.json()["revision"]}
        done = client.post(f"/api/v1/agents/drafts/{draft['id']}/complete", json=payload)
        assert done.status_code == 200, done.text
        repeated = client.post(f"/api/v1/agents/drafts/{draft['id']}/complete", json=payload)
        assert repeated.status_code == 200, repeated.text
        assert repeated.json()["character"]["id"] == done.json()["character"]["id"]
        assert done.json()["credential"] is None
        assert done.json()["settings"]["auto_enabled"] is False
        # Exercise the production aggregator, not an otherwise-unmounted domain router.
        import base64, json
        card_draft = client.post("/api/v1/agents/drafts", json={}).json()
        raw = json.dumps({"name":"카드", "description":"배경", "personality":"다정함", "scenario":"", "first_mes":"", "mes_example":""}).encode()
        imported = client.post(f"/api/v1/agents/drafts/{card_draft['id']}/card", json={
            "revision":card_draft["revision"], "data_base64":base64.b64encode(raw).decode()})
        assert imported.status_code == 200, imported.text
        source = client.get(f"/api/v1/agents/drafts/{card_draft['id']}/card-source")
        assert source.status_code == 200 and source.headers["cache-control"] == "private, no-store"
        assert source.json()["document"]["name"] == "카드"
        cancelled = client.patch(f"/api/v1/agents/drafts/{card_draft['id']}", json={
            "revision": imported.json()["draft"]["revision"], "status": "cancelled"})
        assert cancelled.status_code == 200 and cancelled.json()["status"] == "cancelled"
        assert client.get(f"/api/v1/agents/drafts/{card_draft['id']}/card-source").status_code == 404
        cannot_register = client.post(f"/api/v1/agents/drafts/{card_draft['id']}/complete", json={
            "revision": cancelled.json()["revision"]})
        assert cannot_register.status_code == 409
        preserved = client.patch(f"/api/v1/agents/drafts/{draft['id']}", json={**payload, "status": "cancelled"})
        assert preserved.status_code == 200 and preserved.json()["status"] == "completed"
        assert session.get(CharacterRegistrationReceipt, draft["id"]).character_id == done.json()["character"]["id"]


def test_cancel_and_register_race_preserves_one_final_state(db):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from app.domains.characters.exceptions import AgentCreationDraftHandleConflictError
    session, owner = db
    workflows = build_creator_workflows()
    draft = asyncio.run(drafts.create_draft(session, owner, AgentCreationDraftCreate(), workflows=workflows))
    edited = drafts.update_draft(session, owner, draft.id, AgentCreationDraftUpdate(
        revision=draft.revision, name="취소 경합", worldview="침착한 앵무", personality="침착함"), workflows=workflows)
    draft_id, owner_id, revision = draft.id, owner.id, edited.revision
    session.commit()
    barrier = Barrier(2)
    def request(cancel):
        with Session(session.get_bind()) as worker:
            actor = worker.get(User, owner_id)
            barrier.wait(timeout=10)
            if cancel:
                return drafts.update_draft(worker, actor, draft_id,
                    AgentCreationDraftUpdate(revision=revision, status="cancelled"), workflows=workflows).status
            try:
                drafts.complete_draft(worker, actor, draft_id,
                    AgentCreationDraftComplete(revision=revision), workflows=workflows)
                return "completed"
            except AgentCreationDraftHandleConflictError:
                return "registration_rejected"
    with ThreadPoolExecutor(2) as pool:
        cancelled, registered = list(pool.map(request, [True, False]))
    session.expire_all()
    final = session.get(AgentCreationDraft, draft_id)
    receipt = session.get(CharacterRegistrationReceipt, draft_id)
    if final.status == "completed":
        assert (cancelled, registered) == ("completed", "completed")
        assert receipt is not None and session.get(Character, receipt.character_id) is not None
    else:
        assert (final.status, cancelled, registered) == ("cancelled", "cancelled", "registration_rejected")
        assert receipt is None
        assert session.scalar(select(Character).where(Character.name == "취소 경합")) is None


def test_cancel_commit_failure_preserves_card_and_media(db, monkeypatch):
    from app.domains.characters.service.card_import import import_card
    from app.domains.characters.models import CharacterCardSource
    import json
    session, owner = db
    deleted = []
    workflows = replace(build_creator_workflows(), delete_draft_media=deleted.append)
    draft = asyncio.run(drafts.create_draft(session, owner, AgentCreationDraftCreate(), workflows=workflows))
    card = json.dumps({"name":"보존", "description":"배경", "personality":"친절함",
        "scenario":"", "first_mes":"", "mes_example":""}).encode()
    imported = import_card(session, owner, draft.id, revision=draft.revision, content=card, workflows=workflows)
    def fail_commit():
        raise RuntimeError("commit failed")
    monkeypatch.setattr(session, "commit", fail_commit)
    with pytest.raises(RuntimeError, match="commit failed"):
        drafts.update_draft(session, owner, draft.id, AgentCreationDraftUpdate(
            revision=imported["draft"].revision, status="cancelled"), workflows=workflows)
    assert not deleted
    assert session.get(AgentCreationDraft, draft.id).status == "editing"
    assert session.scalar(select(CharacterCardSource).where(CharacterCardSource.draft_id == draft.id)) is not None
