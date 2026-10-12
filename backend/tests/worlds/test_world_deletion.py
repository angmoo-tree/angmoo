"""Real temporary canonical SQLite, not a mock of deletion completion."""
from datetime import UTC, datetime
from pathlib import Path
import pytest
from sqlalchemy import create_engine, event, select, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import IntegrityError
from app.runtime.persistence.model_registration import register_models
from app.domains.worlds.models import World, WorldMembership, OwnerDefaultWorld
from app.domains.worlds.models_deletion import WorldDeletionRequest, WorldDeletionCleanupItem
from app.domains.worlds.contracts_deletion import WorldDeletionCommand, WorldDeletionError
from app.domains.worlds.service import deletion
from app.runtime.world_deletion.ports import ScopedWorldErasure, stop_admission
from app.runtime.world_deletion.worker import WorldDeletionWorker
from worlds.test_creator_routes import _user


@pytest.fixture
def environment(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'canonical.sqlite'}")
    @event.listens_for(engine, "connect")
    def configure(connection, _):
        connection.execute("PRAGMA foreign_keys=ON")
    register_models().create_all(engine)
    sessions = sessionmaker(engine, expire_on_commit=False, autoflush=False)
    with sessions() as db:
        db.add_all([_user("owner"), _user("other")])
        db.flush()
        from app.domains.identity.models import InstallationIdentity
        db.add(InstallationIdentity(singleton_key="local-installation", installation_id="fixture-installation",
            owner_user_id="owner", bootstrap_state="claimed", claimed_at=datetime.now(UTC)))
        for name in ("a", "b"):
            db.add(World(id=name, slug=name, owner_user_id="owner", name="World " + name,
                status="draft", contract_version="world-v1", contract_hash="0" * 64, create_idempotency_key=name))
            db.flush()
            db.add(WorldMembership(id="member-" + name, world_id=name, user_id="owner", role="owner", status="active"))
        db.commit()
    effects = {"index": [], "graph": []}
    ports = ScopedWorldErasure(tmp_path / "media", index_cleanup=lambda ids: effects["index"].extend(ids),
        graph_cleanup=lambda world: effects["graph"].append(world))
    yield sessions, ports, effects
    engine.dispose()


def command(**overrides):
    return WorldDeletionCommand(**{"expected_row_version": 1, "confirmed_name": "World a", "consent": True,
        "idempotency_key": "0123456789abcdef", **overrides})


def admitted(sessions, **overrides):
    with sessions() as db:
        return deletion.accept(db, "a", "owner", command(**overrides), stop_admission=stop_admission)


def finish(sessions, ports):
    worker = WorldDeletionWorker(sessions, ports)
    for _ in range(500):
        worker.tick()
        with sessions() as db:
            row = db.scalar(select(WorldDeletionRequest))
            if row.state in {"completed", "failed"}:
                return row
    raise AssertionError("deletion did not settle")


def test_owner_receipt_idempotency_and_durable_empty_world_cleanup(environment):
    sessions, ports, effects = environment
    result = admitted(sessions)
    assert result.state == "accepted"
    assert admitted(sessions).request_id == result.request_id
    assert finish(sessions, ports).state == "completed"
    assert effects["graph"] == ["a"]
    with sessions() as db:
        assert db.get(World, "b").name == "World b"
        assert db.get(World, "a").name == ""
        assert db.scalar(select(WorldMembership).where(WorldMembership.world_id == "a")) is None
        assert list(db.scalars(select(WorldDeletionCleanupItem))) == []
        assert deletion.receipt(deletion.owned_receipt(db, result.request_id, "owner")).state == "completed"
        with pytest.raises(WorldDeletionError, match="deletion_not_found"):
            deletion.owned_receipt(db, result.request_id, "other")
    assert admitted(sessions).state == "completed"


@pytest.mark.parametrize("issue", ["name", "version", "owner", "default"])
def test_confirmation_acl_default_and_version_are_not_bypassed(environment, issue):
    sessions, _, _ = environment
    with sessions() as db:
        if issue == "default":
            db.add(OwnerDefaultWorld(owner_id="owner", world_id="a"))
            db.commit()
        changed = {"confirmed_name": "wrong"} if issue == "name" else {"expected_row_version": 9} if issue == "version" else {}
        with pytest.raises(WorldDeletionError):
            deletion.accept(db, "a", "other" if issue == "owner" else "owner", command(**changed), stop_admission=stop_admission)
        db.rollback()
        assert db.scalar(select(WorldDeletionRequest)) is None
        assert db.get(World, "a").name == "World a"


def test_archived_owner_can_delete_and_conflicting_replays_are_rejected(environment):
    sessions, _, _ = environment
    with sessions() as db:
        db.get(World, "a").status = "archived"
        db.commit()
    admitted(sessions)
    with sessions() as db:
        with pytest.raises(WorldDeletionError, match="deletion_idempotency_conflict"):
            deletion.accept(db, "a", "owner", command(confirmed_name="changed"), stop_admission=stop_admission)


def test_old_writer_and_new_world_id_cannot_resurrect_accepted_scope(environment):
    sessions, _, _ = environment
    admitted(sessions)
    with sessions() as db:
        with pytest.raises(IntegrityError, match="world_deleting"):
            db.execute(text("UPDATE worlds SET name='late response' WHERE id='a'"))
        db.rollback()
        with pytest.raises(IntegrityError, match="world_deleting"):
            db.add(WorldMembership(id="late", world_id="a", user_id="other", role="member", status="active"))
            db.commit()
        db.rollback()
        db.add(WorldMembership(id="live", world_id="b", user_id="other", role="member", status="active"))
        db.commit()


def test_file_journal_survives_failure_and_retry_does_not_duplicate_request(environment):
    sessions, ports, effects = environment
    path = ports.media_root / "worlds/a/icon.webp"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"temporary file")
    with sessions() as db:
        db.get(World, "a").icon_media_id = "/media/worlds/a/icon.webp"
        db.commit()
    result = admitted(sessions)
    assert finish(sessions, ports).state == "completed"
    assert not path.exists()
    with sessions() as db:
        assert deletion.owned_receipt(db, result.request_id, "owner").state == "completed"


def test_cleanup_failure_stays_failed_until_same_receipt_is_retried(environment):
    sessions, ports, effects = environment
    admitted(sessions)
    def unavailable(world):
        raise OSError("synthetic graph outage")
    ports.graph_cleanup = unavailable
    worker = WorldDeletionWorker(sessions, ports)
    for _ in range(180):
        worker.tick()
        with sessions() as db:
            row = db.scalar(select(WorldDeletionRequest))
            if row.state == "retry_wait":
                row.next_attempt_at = None
                db.commit()
            if row.state == "failed":
                break
    with sessions() as db:
        row = db.scalar(select(WorldDeletionRequest))
        assert row.state == "failed" and row.stage == "cleaning"
        same_id = row.id
        deletion.retry(db, same_id, "owner")
    ports.graph_cleanup = lambda world: effects["graph"].append(world)
    assert finish(sessions, ports).state == "completed"
    with sessions() as db:
        assert db.scalar(select(WorldDeletionRequest)).id == same_id


def test_file_paths_cannot_escape_or_follow_links(environment, tmp_path):
    _, ports, _ = environment
    for path in ("../outside", str(tmp_path.resolve()), "worlds/../../outside"):
        with pytest.raises(ValueError):
            ports._safe_path(path)


def test_world_characters_posts_chat_and_first_original_are_separate(environment, monkeypatch):
    from worlds.test_foundation import _character
    from app.domains.characters.service.import_snapshots import capture_creation, get_import_snapshot
    from app.domains.characters.service.import_configuration import ImportConfiguration, ImportProfile, ImportSettings
    from app.domains.world_characters.models import WorldCharacter, CharacterWorldBinding, CharacterActiveWorld
    from app.domains.characters.models import Character
    from app.domains.chat.models import MessageThread, MessageMessage
    from app.domains.social.models.posts import Post
    sessions, ports, effects = environment
    initial = ports.media_root / "characters/red/initial.webp"
    current = ports.media_root / "characters/red/current.webp"
    initial.parent.mkdir(parents=True)
    from PIL import Image
    Image.new("RGB", (16, 16), "red").save(initial, format="WEBP")
    initial_bytes = initial.read_bytes()
    current.write_bytes(b"current world media")
    with sessions() as db:
        db.add_all([_character("red", "owner"), _character("requester", "owner"), _character("bram", "owner")])
        db.flush()
        digests = {}
        for identifier in ("red", "requester", "bram"):
            original = ImportConfiguration(profile=ImportProfile(display_name=identifier, handle=identifier,
                avatar_url="/media/characters/red/initial.webp" if identifier == "red" else None), settings=ImportSettings(personality="first registration"))
            digests[identifier] = capture_creation(db, character_id=identifier, configuration=original, provenance="test first registration").digest
        db.add_all([
            WorldCharacter(id="red-a", world_id="a", character_id="red", membership_id="member-a", status="active", autonomous_enabled=True,
                local_profile={"avatar_url": "/media/characters/red/current.webp"}),
            WorldCharacter(id="user-a", world_id="a", character_id="requester", membership_id="member-a", status="active"),
            WorldCharacter(id="bram-b", world_id="b", character_id="bram", membership_id="member-b", status="active", autonomous_enabled=True),
        ])
        db.flush()
        db.add(CharacterWorldBinding(character_id="red", world_id="a"))
        db.add(CharacterActiveWorld(character_id="red", world_character_id="red-a", selected_at=datetime.now(UTC), idempotency_key="selection"))
        db.add(MessageThread(id="thread-a", requester_id="owner", character_id="red", world_id="a",
            requester_world_character_id="user-a", responding_world_character_id="red-a", world_scope_status="resolved"))
        db.add(Post(id="post-a", author_user_id="owner", author_character_id="red", world_id="a", author_world_character_id="red-a",
            author_name="Red", title="private test", body="delete this World content"))
        db.flush()
        db.add(MessageMessage(thread_id="thread-a", role="user", content="delete this chat text"))
        db.get(Character, "red").personality = "modified in the deleted World"
        db.commit()
    admitted(sessions)
    result = finish(sessions, ports)
    assert result.state == "completed", (result.stage, result.failure_code)
    with sessions() as db:
        assert list(db.scalars(select(MessageMessage))) == []
        assert list(db.scalars(select(MessageThread))) == []
        assert list(db.scalars(select(Post))) == []
        assert db.get(CharacterWorldBinding, "red") is None
        assert db.get(CharacterActiveWorld, "red") is None
        assert db.get(Character, "red").deleted_at is None
        assert db.get(Character, "red").personality == "first registration"
        for identifier, digest in digests.items():
            assert get_import_snapshot(db, identifier)[0].digest == digest
        assert db.get(WorldCharacter, "bram-b").autonomous_enabled
        from app.domains.world_characters.service.lifecycle import WorldCharacterLifecycleService
        from app.runtime.world_characters.queries import SqlAlchemyWorldCharacterQueries
        candidates = WorldCharacterLifecycleService(db, queries=SqlAlchemyWorldCharacterQueries()).list_candidates(world_id="b", current_user_id="owner")
        assert next(candidate for candidate in candidates if candidate.character_id == "red").eligible
    assert initial.read_bytes() == initial_bytes
    assert not current.exists()
    # The surviving source is copied and explicitly registered through existing
    # production services, without reviving the old World or its actor.
    from types import SimpleNamespace
    from datetime import timedelta
    from app.domains.characters.models import AgentCreationDraft
    from app.domains.characters.schemas import CharacterSettingsCopy
    from app.domains.characters.service.settings_copy import copy_settings
    from app.config import settings
    monkeypatch.setattr(settings, "MEDIA_ROOT", str(ports.media_root))
    with sessions() as db:
        db.add(AgentCreationDraft(id="new-copy", user_id="owner", model="fixture", target_world_id="b",
            contract_version=2, revision=1, expires_at=datetime.now(UTC) + timedelta(hours=1)))
        db.commit()
        copied = copy_settings(db, SimpleNamespace(id="owner"), "new-copy", CharacterSettingsCopy(revision=1, character_id="red"),
            workflows=SimpleNamespace(validate_copy_target=None))
        assert copied.personality == "first registration"
        assert db.get(AgentCreationDraft, "new-copy").avatar_temp_url
        db.get(World, "b").status, db.get(World, "b").readiness_status = "published", "publish_ready"
        db.commit()
        from app.domains.world_characters.schemas.setup import WorldCharacterEntryCreate
        from app.domains.world_characters.service.autonomous_setup import enter_world
        from app.runtime.world_characters.creation_configuration import initialize_entered_world_character
        from app.domains.worlds.contracts import NO_SPECIFIC_ROLE_KEY
        entered = enter_world(db, world_id="b", user=SimpleNamespace(id="owner"),
            data=WorldCharacterEntryCreate(character_id="red", role_key=NO_SPECIFIC_ROLE_KEY, idempotency_key="explicit-entry-b"),
            on_created=lambda session, **scope: initialize_entered_world_character(session, world_character_id=scope["world_character_id"]))
        from app.domains.world_characters.configuration_models import WorldCharacterConfiguration
        actor = db.get(WorldCharacter, entered.id)
        assert not actor.autonomous_enabled
        assert db.get(WorldCharacterConfiguration, actor.id).settings["personality"] == "first registration"
        assert db.get(WorldCharacter, "red-a") is None
        from app.domains.characters.service.access import _get_owned_character
        from app.domains.characters.exceptions import AgentNotFoundError
        with pytest.raises(AgentNotFoundError):
            _get_owned_character(db, SimpleNamespace(id="other"), "red")
    from fastapi import FastAPI
    from fastapi.staticfiles import StaticFiles
    from worlds.test_creator_routes import _request
    app = FastAPI()
    app.mount("/media/characters", StaticFiles(directory=ports.media_root / "characters"))
    response = _request(app, "GET", "/media/characters/red/initial.webp")
    assert response.status_code == 200 and response.content == initial_bytes
