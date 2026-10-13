"""Synthetic-only integration fixture for the real contributor application.

Requires its own marked root; never reads installed/Docker production data.
No provider credentials are seeded and every fixture actor has autonomy OFF.
"""
from pathlib import Path
from datetime import UTC, datetime, timedelta
import argparse
import hashlib
import json
import sys

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backend"))
OWNER = "lifecycle-fixture-owner"
TARGET = "019f1000-0000-7000-8000-000000000001"
SURVIVOR = "019f1000-0000-7000-8000-000000000002"
DEFAULT = "019f1000-0000-7000-8000-000000000003"
TOKEN = "synthetic-lifecycle-session-not-a-user-secret"


def seed(app, root):
    from sqlalchemy import select
    from app.core.security import hash_token
    from app.domains.identity.models import User, AuthSession, InstallationIdentity
    from app.domains.identity.models_environment import LocalEnvironment
    from app.domains.worlds.models import World, WorldMembership, OwnerDefaultWorld
    from app.domains.characters.models import Character, AgentCreationDraft
    from app.domains.characters.service.import_configuration import ImportConfiguration, ImportProfile, ImportSettings
    from app.domains.characters.service.import_snapshots import capture_creation
    from app.domains.world_characters.models import WorldCharacter, CharacterWorldBinding
    from app.domains.social.models.posts import Post
    from PIL import Image
    with app.state.runtime_composition.session_factory() as db:
        if db.get(User, OWNER):
            return
        db.add(User(id=OWNER, display_name="Integration Owner", display_name_normalized="integration owner",
            profile_setup_completed=True, ui_language="en", privacy_policy_version="fixture", terms_version="fixture"))
        db.flush()
        installation = db.get(InstallationIdentity, "local-installation")
        installation.owner_user_id, installation.bootstrap_state, installation.claimed_at = OWNER, "claimed", datetime.now(UTC)
        db.add(LocalEnvironment(owner_id=OWNER, installation_id=installation.installation_id,
            preferred_language="en-US", timezone="UTC", confirmed_at=datetime.now(UTC), environment_revision=1))
        db.add(AuthSession(token_hash=hash_token(TOKEN), user_id=OWNER, auth_method="local_owner", created_at=datetime.now(UTC)))
        for identifier, name in ((TARGET, "Integration target"), (SURVIVOR, "Integration survivor"), (DEFAULT, "Renamed default SNS")):
            db.add(World(id=identifier, slug="fixture-" + identifier, owner_user_id=OWNER, name=name, visibility="private",
                status="published", readiness_status="publish_ready", setting_description="Synthetic world setting. " * 15,
                daily_life_description="Synthetic ordinary daily life. " * 12, contract_version="world-v1",
                contract_hash="a" * 64, create_idempotency_key="fixture-" + identifier))
            db.flush()
            db.add(WorldMembership(id="membership-" + identifier, world_id=identifier, user_id=OWNER, role="owner", status="active"))
        db.add(OwnerDefaultWorld(owner_id=OWNER, world_id=DEFAULT))
        initial = root / "media/characters/fixture-red/initial.webp"
        initial.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (16, 16), "red").save(initial, format="WEBP")
        current = root / f"media/worlds/{TARGET}/icon-fixture.webp"
        current.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (16, 16), "blue").save(current, format="WEBP")
        db.get(World, TARGET).icon_media_id = f"/media/worlds/{TARGET}/icon-fixture.webp"
        character = Character(id="fixture-red", owner_id=OWNER, name="Red", handle="fixture_red", one_liner="First persona",
            personality="first registration persona", speech_style="calm", worldview="fixture", topic_preferences="fixture",
            safety_rules="safe", status="inactive", moderation_status="active", execution_mode="llm", persona_summary="fixture")
        db.add(character)
        db.flush()
        capture_creation(db, character_id=character.id, configuration=ImportConfiguration(
            profile=ImportProfile(display_name="Red", handle="fixture_red", avatar_url="/media/characters/fixture-red/initial.webp"),
            settings=ImportSettings(personality="first registration persona")), provenance="synthetic first registration")
        actor = WorldCharacter(id="fixture-red-a", world_id=TARGET, character_id=character.id,
            membership_id="membership-" + TARGET, status="active", autonomous_enabled=False)
        db.add(actor)
        db.add(CharacterWorldBinding(character_id=character.id, world_id=TARGET))
        db.flush()
        db.add(Post(id="fixture-post-a", author_user_id=OWNER, author_character_id=character.id,
            world_id=TARGET, author_world_character_id=actor.id, author_name="Red", title="Synthetic post", body="Erase this fixture body"))
        db.add(AgentCreationDraft(id="fixture-copy-draft", user_id=OWNER, model="fixture", target_world_id=SURVIVOR,
            contract_version=2, revision=1, expires_at=datetime.now(UTC) + timedelta(hours=1)))
        db.commit()


def report(app, root):
    from sqlalchemy import select, func
    from app.domains.worlds.models import World
    from app.domains.worlds.models_deletion import WorldDeletionRequest, WorldDeletionCleanupItem
    from app.domains.characters.service.import_snapshots import get_import_snapshot
    from app.domains.world_characters.models import WorldCharacter
    from app.domains.social.models.posts import Post
    from app.domains.device_home.repository import SqlAlchemyWorldSurfaceRepository
    with app.state.runtime_composition.session_factory() as db:
        receipt = db.scalar(select(WorldDeletionRequest).where(WorldDeletionRequest.world_id == TARGET))
        origin, configuration = get_import_snapshot(db, "fixture-red")
        data = {"state": receipt.state if receipt else None, "stage": receipt.stage if receipt else None,
            "request_id": receipt.id if receipt else None, "source_digest": origin.digest,
            "source_initial_image": (root / "media/characters/fixture-red/initial.webp").is_file(),
            "target_image": (root / f"media/worlds/{TARGET}/icon-fixture.webp").exists(),
            "target_posts": db.scalar(select(func.count()).select_from(Post).where(Post.world_id == TARGET)),
            "target_actors": db.scalar(select(func.count()).select_from(WorldCharacter).where(WorldCharacter.world_id == TARGET)),
            "survivor_live": db.get(World, SURVIVOR).name == "Integration survivor",
            "journal_count": db.scalar(select(func.count()).select_from(WorldDeletionCleanupItem)),
            "target_home": SqlAlchemyWorldSurfaceRepository(db).get_world(owner_user_id=OWNER, world_id=TARGET) is not None}
    return data


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--mode", choices=("serve", "stage", "finish", "report", "health"), default="serve")
    parser.add_argument("--origin", default="http://127.0.0.1:3419")
    parser.add_argument("--port", type=int, default=3420)
    args = parser.parse_args()
    root = args.root.resolve()
    marker = root / ".synthetic-chat-world-fixture"
    if root.exists() and any(root.iterdir()) and not marker.is_file():
        raise RuntimeError("unmarked_fixture_root_refused")
    root.mkdir(parents=True, exist_ok=True)
    marker.touch()
    from app.config import settings
    settings.APP_ENV = "development"
    settings.BROWSER_SESSION_ALLOWED_ORIGINS = args.origin
    settings.MEDIA_ROOT = str(root / "media")
    from app.runtime.contributor_backend import create_contributor_runtime_app
    app = create_contributor_runtime_app(data_root=root, frontend_origin=args.origin)
    seed(app, root)
    if args.mode == "serve":
        import uvicorn
        uvicorn.run(app, host="127.0.0.1", port=args.port)
        return
    try:
        if args.mode == "health":
            import asyncio
            import httpx
            from time import monotonic
            async def health_cycle():
                async with app.router.lifespan_context(app):
                    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url="http://fixture") as client:
                        for _ in range(100):
                            response=await client.get("/health")
                            if response.status_code==200:break
                            await asyncio.sleep(0.1)
                        assert response.status_code==200,response.json()
                        assert app.state.world_deletion_worker.task is not None
                    exiting=monotonic()
                assert monotonic()-exiting<10
                print(json.dumps({"health_status":response.status_code,"shutdown_seconds":round(monotonic()-exiting,3)}))
            asyncio.run(health_cycle())
            return
        if args.mode == "stage":
            from app.domains.worlds.service.deletion import accept
            from app.domains.worlds.contracts_deletion import WorldDeletionCommand
            from app.runtime.world_deletion.canonical_erasure import stop_admission
            with app.state.runtime_composition.session_factory() as db:
                accept(db, TARGET, OWNER, WorldDeletionCommand(expected_row_version=1, confirmed_name="Integration target",
                    consent=True, idempotency_key="synthetic-stage-request"), stop_admission=stop_admission)
            app.state.world_deletion_worker.tick()
            app.state.world_deletion_worker.tick()
        elif args.mode == "finish":
            app.state.runtime_composition.memory_recall_projection.start(background=False)
            for _ in range(600):
                app.state.world_deletion_worker.tick()
                observed = report(app, root)
                if observed["state"] in {"completed", "failed"}:
                    break
            assert observed["state"] == "completed", observed
            assert observed["target_posts"] == observed["target_actors"] == observed["journal_count"] == 0
            assert observed["source_initial_image"] and observed["survivor_live"]
            assert not observed["target_image"] and not observed["target_home"]
        print(json.dumps(report(app, root), sort_keys=True))
    finally:
        app.state.dispose_runtime()


if __name__ == "__main__":
    main()
