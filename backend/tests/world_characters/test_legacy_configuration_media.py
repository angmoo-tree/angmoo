"""Legacy public loopback media stays readable without rewriting World origins."""
from copy import deepcopy

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import update
from sqlalchemy.orm import Session

from app.api.identity_dependencies import get_current_user
from app.database import get_db
from app.domains.characters.models import Character
from app.domains.characters.models_import import CharacterImportSnapshot
from app.domains.characters.router import router as character_router
from app.domains.characters.service.import_configuration import ImportProfile, import_digest
from app.domains.characters.service.import_snapshots import get_import_snapshot
from app.domains.world_characters.configuration_models import WorldCharacterConfiguration
from app.domains.world_characters.router.management import router as world_router
from app.domains.world_characters.service.configuration import batch_effective_profiles, effective_configuration
from app.runtime.characters.management import build_character_management_workflows
from world_configuration_fixture_support import fixture_owner, seed_configuration_fixture


@pytest.mark.parametrize("url", [
    "http://localhost:3000/icon.svg",
    "http://localhost:3030/icon.svg",
    "http://127.0.0.1:3000/icon.svg",
    "http://[::1]:3000/icon.svg",
    "http://localhost:8080/media/characters/synthetic/avatar.webp",
    "http://127.0.0.1:8080/api/v1/media/assets/synthetic-asset/content",
])
def test_public_loopback_reference_is_read_verbatim(url):
    profile = ImportProfile(display_name="Legacy", handle="legacy", avatar_url=url)
    assert profile.avatar_url == url
    assert profile.model_dump()["avatar_url"] == url


@pytest.mark.parametrize("url", [
    "http://example.test/icon.svg",
    "http://192.168.1.1/icon.svg",
    "http://localhost.example.test/icon.svg",
    "http://localhost/api/v1/identity/me",
    "http://localhost/admin",
    "http://user:secret@localhost:3000/icon.svg",
    "http://localhost:3000/icon.svg?token=synthetic",
    "http://localhost:3000/icon.svg#synthetic",
    "http://localhost:3000/media/../private",
    "http://localhost:invalid/icon.svg",
    "http://localhost:99999/icon.svg",
    "http://localhost:0/icon.svg",
    "http://localhost:3000/\\private",
    "http://localhost:3000/icon.svg\n",
    "//localhost:3000/icon.svg",
    "javascript:alert(1)",
    "file:///private/icon.svg",
])
def test_legacy_compatibility_does_not_admit_private_or_credential_references(url):
    with pytest.raises(ValidationError):
        ImportProfile(display_name="Legacy", handle="legacy", avatar_url=url)


def test_legacy_origin_and_world_profile_are_readable_by_real_management_routes(tmp_path):
    engine = seed_configuration_fixture(tmp_path / "legacy-media.sqlite3", browser_ready=True)
    try:
        with Session(engine) as db:
            source = db.get(Character, "config-actor-a")
            source.avatar_url = "http://localhost:3030/icon.svg"
            stored = db.get(WorldCharacterConfiguration, "config-role-a")
            stored.profile = {**stored.profile, "avatar_url": source.avatar_url}
            origin, _ = get_import_snapshot(db, source.id)
            # Seed a historical database row before the read under test. Core
            # fixture setup keeps the application's immutable ORM guard intact.
            payload = {**origin.payload, "profile": deepcopy(stored.profile)}
            db.execute(update(CharacterImportSnapshot).where(
                CharacterImportSnapshot.id == origin.id
            ).values(kind="legacy_transition", payload=payload, digest=import_digest(payload)))
            db.commit()
            db.expire_all()
            expected_origin = (origin.id, origin.digest, deepcopy(origin.payload))
            expected_profile = deepcopy(stored.profile)
            origin_count = db.query(CharacterImportSnapshot).count()

        app = FastAPI()
        app.include_router(character_router, prefix="/api/v1")
        app.include_router(world_router, prefix="/api/v1")
        app.state.character_management_workflows = build_character_management_workflows

        def database():
            with Session(engine) as db:
                yield db

        def owner():
            with Session(engine) as db:
                user = fixture_owner(db)
                db.expunge(user)
                return user

        app.dependency_overrides[get_db] = database
        app.dependency_overrides[get_current_user] = owner
        with TestClient(app, base_url="http://127.0.0.1:3000", raise_server_exceptions=False) as client:
            listing = client.get("/api/v1/agents")
            assert listing.status_code == 200, listing.text
            assert {"config-actor-a", "config-actor-b"} <= {
                item["character"]["id"] for item in listing.json()
            }
            detail = client.get("/api/v1/agents/config-actor-a")
            assert detail.status_code == 200, detail.text
            assert detail.json()["character"]["avatar_url"] == expected_profile["avatar_url"]
            dashboard = client.get("/api/v1/worlds/config-world-a/character-dashboard")
            assert dashboard.status_code == 200, dashboard.text
            settings = client.get("/api/v1/worlds/config-world-a/world-characters/config-role-a/settings")
            assert settings.status_code == 200, settings.text

        with Session(engine) as db:
            origin, configuration = get_import_snapshot(db, "config-actor-a")
            assert configuration.profile.avatar_url == expected_profile["avatar_url"]
            assert (origin.id, origin.digest, origin.payload) == expected_origin
            assert db.query(CharacterImportSnapshot).count() == origin_count
            effective = effective_configuration(db, world_character_id="config-role-a")
            assert effective.profile.avatar_url == expected_profile["avatar_url"]
            profiles = batch_effective_profiles(db, world_id="config-world-a", world_character_ids=["config-role-a"])
            assert profiles["config-role-a"].avatar_url == expected_profile["avatar_url"]
            assert db.get(WorldCharacterConfiguration, "config-role-a").profile == expected_profile
    finally:
        engine.dispose()
