"""Exact World erasure, public retention and late-writer fences; no network."""
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker
from app.domains.characters.models import Character
from app.domains.chat.models import MessageThread, MessageMessage
from app.domains.identity.models import User
from app.domains.identity.schemas import WorldCredentialWrite
from app.domains.identity.service import world_credentials
from app.domains.identity.exceptions import CredentialResolutionError
from app.domains.media.models import MediaAsset
from app.domains.media.models_world_policy import WorldImagePolicy
from app.domains.media.service.assets import AssetService
from app.domains.memory.models.items import MemoryItem, MemoryScopeSettingModel
from app.domains.social.models.posts import Post, PostMedia
from app.domains.world_characters.models import WorldCharacter
from app.domains.world_characters.configuration_models import WorldCharacterConfiguration
from app.domains.world_characters.schemas.deletion import WorldInstanceDelete
from app.domains.world_characters.service.management import WorldManagementError
from app.runtime.world_characters.management import management_service
from app.runtime.world_characters.instance_deletion import erase
from app.runtime.social.post_authors import batch_world_post_authors
from app.runtime.media.erasure import cleanup
from world_configuration_fixture_support import seed_configuration_fixture


@pytest.fixture
def state(tmp_path, deny_external_network):
    engine = seed_configuration_fixture(tmp_path / "erasure.sqlite3")
    yield engine, tmp_path
    engine.dispose()


def seed_private(db):
    owner_role = db.scalar(select(WorldCharacter).where(WorldCharacter.world_id == "config-world-a",
        WorldCharacter.control_mode == "owner_controlled"))
    db.add(MessageThread(id="private-thread", requester_id="fixture-owner", character_id="config-actor-a",
        world_id="config-world-a", requester_world_character_id=owner_role.id,
        responding_world_character_id="config-role-a", world_scope_status="resolved"))
    db.flush()
    db.add(MessageMessage(thread_id="private-thread", role="user", content="Synthetic private body"))
    for suffix in ("a", "b"):
        db.add(MemoryScopeSettingModel(id=f"scope-{suffix}", owner_id="fixture-owner", world_id=f"config-world-{suffix}",
            subject_world_character_id=f"config-role-{suffix}"))
        db.add(MemoryItem(id=f"memory-{suffix}", owner_id="fixture-owner", world_id=f"config-world-{suffix}",
            subject_world_character_id=f"config-role-{suffix}", memory_kind="AUTOBIOGRAPHICAL_EVENT", summary="Synthetic private memory",
            confidence=1, salience=.5, valid_from=datetime.now(UTC)))
    db.add(Post(id="public-post", author_character_id="config-actor-a", author_world_character_id="config-role-a",
        world_id="config-world-a", author_name="Bram", title="Synthetic public", body="Public body retained"))
    db.flush()
    for name in ("public", "private"):
        db.add(MediaAsset(id=f"asset-{name}", owner_id="fixture-owner", scope_kind="world_character", scope_id="config-role-a",
            storage_key=f"{name}.png", content_type="image/png", content_hash="a"*64, byte_size=3, width=1, height=1, revision=1, state="ready"))
    db.flush()
    db.add(PostMedia(post_id="public-post", asset_id="asset-public", url="/synthetic/public.png", byte_size=3, width=1, height=1))
    db.commit()


def request(db, **changes):
    actor = db.get(WorldCharacter, "config-role-a")
    name = db.get(WorldCharacterConfiguration, actor.id).profile["display_name"]
    return WorldInstanceDelete(**{"expected_revision": actor.version, "confirmed_name": name, "consent": True, **changes})


def test_exact_erasure_preserves_original_other_world_public_material_and_revokes_keys(state):
    engine, root = state
    with Session(engine) as db:
        seed_private(db)
        for purpose in ("sns", "chat", "vision", "consolidation"):
            world_credentials.save(db, owner_id="fixture-owner", world_id="config-world-a", world_character_id="config-role-a",
                purpose=purpose, data=WorldCredentialWrite(expected_revision=0, provider="google", model="gemini-3.1-flash-lite", thinking_level="high", api_key="synthetic-private-key"))
        db.commit()
        result = erase(management_service(db), world_id="config-world-a", world_character_id="config-role-a",
            user=db.get(User,"fixture-owner"), data=request(db))
        assert result["deleted"] and result["private_memory_count"] == 1
        db.expire_all()
        assert db.get(Character, "config-actor-a").deleted_at is None
        assert db.get(WorldCharacter, "config-role-b").status == "active"
        assert db.get(WorldCharacterConfiguration, "config-role-b") is not None
        assert db.get(MemoryItem, "memory-a") is None and db.get(MemoryItem, "memory-b") is not None
        assert db.scalar(select(MessageMessage).where(MessageMessage.thread_id=="private-thread")) is None
        assert db.get(MessageThread, "private-thread").deleted_at is not None
        assert db.get(Post, "public-post").body == "Public body retained"
        assert db.get(MediaAsset, "asset-public").state == "ready"
        assert db.get(MediaAsset, "asset-private").state == "deleted"
        assert db.get(WorldImagePolicy, "config-role-a") is None
        profile = batch_world_post_authors(db, world_id="config-world-a", author_ids={"config-role-a"})["config-role-a"]
        assert profile.deleted and profile.avatar_url is None
        with pytest.raises(CredentialResolutionError):
            world_credentials.resolve(db, owner_id="fixture-owner", world_id="config-world-a", world_character_id="config-role-a", purpose="chat")
    assets = AssetService(root, lambda *args: None)
    (root / "private.png").write_bytes(b"raw")
    (root / "public.png").write_bytes(b"raw")
    assert cleanup(SimpleNamespace(sessions=sessionmaker(engine), assets=assets))
    assert not (root / "private.png").exists() and (root / "public.png").exists()


@pytest.mark.parametrize("changes", [{"consent":False}, {"confirmed_name":"wrong"}, {"expected_revision":999}])
def test_confirmation_and_revision_rejection_leave_entire_scope_intact(state, changes):
    engine, _ = state
    with Session(engine) as db:
        with pytest.raises(WorldManagementError):
            erase(management_service(db), world_id="config-world-a", world_character_id="config-role-a",
                user=db.get(User,"fixture-owner"), data=request(db, **changes))
        assert db.get(WorldCharacter, "config-role-a").status == "active"
        assert db.get(WorldCharacterConfiguration, "config-role-a") is not None


def test_file_failure_is_post_commit_retryable_without_restoring_actor(state, monkeypatch):
    engine, root = state
    with Session(engine) as db:
        erase(management_service(db), world_id="config-world-a", world_character_id="config-role-a",
            user=db.get(User,"fixture-owner"), data=request(db))
        role = db.get(WorldCharacter,"config-role-a")
        role.local_profile={"deleted":True,"private_cleanup":{"interpretations":["opaque-job"],"generation_jobs":[]}}
        db.commit()
    folder=root/"received-interpretations"; folder.mkdir()
    target=folder/"opaque-job.json"; target.write_text("synthetic",encoding="utf-8")
    media=SimpleNamespace(sessions=sessionmaker(engine),assets=AssetService(root,lambda *args:None))
    unlink=Path.unlink
    def blocked(path,*args,**kwargs):
        if path==target: raise PermissionError("synthetic")
        return unlink(path,*args,**kwargs)
    with monkeypatch.context() as patch:
        patch.setattr(Path,"unlink",blocked)
        assert not cleanup(media)
    with Session(engine) as db:
        assert db.get(WorldCharacter,"config-role-a").local_profile.get("private_cleanup")
        assert db.get(WorldCharacter,"config-role-a").status == "left"
    assert cleanup(media) and not target.exists()
