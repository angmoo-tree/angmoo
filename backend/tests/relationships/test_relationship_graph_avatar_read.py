"""World profile pictures enrich canonical nodes without changing edges or reads."""
import pytest
from sqlalchemy import event, select
from sqlalchemy.orm import Session
from app.config import Settings, settings
from app.domains.world_characters.configuration_models import WorldCharacterConfiguration
from app.runtime.graph_projection.relationship_graph_read import (
    SqlAlchemyRelationshipGraphReadGateway, get_owner_relationship_graph, _public_avatar,
)
from p7_graph_support import seed_projection_fixture, sqlite_engine


def test_t82_t86_world_photos_names_and_direction_are_read_only():
    engine = sqlite_engine()
    with Session(engine, expire_on_commit=False) as db:
        fixture = seed_projection_fixture(db, suffix="world-avatars")
        actor = db.get(WorldCharacterConfiguration, fixture.actor_world_character.id)
        target = db.get(WorldCharacterConfiguration, fixture.target_world_character.id)
        actor.profile = {**actor.profile, "display_name": "World Mango", "avatar_url": "/media/characters/mango/avatar.png"}
        target.profile = {**target.profile, "display_name": "World Sage", "avatar_url": None}
        fixture.actor.name = "Changed global name"
        fixture.actor.avatar_url = "https://example.test/global.png"
        db.commit()
        before = [(row.world_character_id, row.profile, row.settings) for row in db.scalars(select(WorldCharacterConfiguration))]
        statements = []
        def record(_conn, _cursor, statement, *_args):
            statements.append(statement)
        event.listen(engine, "before_cursor_execute", record)
        result = get_owner_relationship_graph(db, character_id=fixture.actor.id, world_id=fixture.world.id,
            user=fixture.owner, config=Settings(GRAPH_PROJECTION_ENABLED=False))
        event.remove(engine, "before_cursor_execute", record)
        nodes = {node.world_character_id: node for node in result.nodes}
        assert nodes[fixture.actor_world_character.id].display_name == "World Mango"
        assert nodes[fixture.actor_world_character.id].avatar_url == "/media/characters/mango/avatar.png"
        assert nodes[fixture.target_world_character.id].avatar_url is None
        assert result.edges[0].actor_world_character_id == fixture.actor_world_character.id
        assert result.edges[0].target_world_character_id == fixture.target_world_character.id
        assert not any(statement.lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE")) for statement in statements)
        assert before == [(row.world_character_id, row.profile, row.settings) for row in db.scalars(select(WorldCharacterConfiguration))]
        assert not any(key in result.model_dump_json() for key in ("personality", "credential", "source_revision"))
    engine.dispose()


def test_t83_t86_node_batch_scope_missing_config_and_query_count():
    engine = sqlite_engine()
    with Session(engine, expire_on_commit=False) as db:
        a = seed_projection_fixture(db, suffix="avatar-a")
        b = seed_projection_fixture(db, suffix="avatar-b")
        gateway = SqlAlchemyRelationshipGraphReadGateway(db, config=Settings(GRAPH_PROJECTION_ENABLED=False))
        statements = []
        def record(*_args):
            statements.append(1)
        event.listen(engine, "before_cursor_execute", record)
        one = gateway.node_candidates(world_id=a.world.id, world_character_ids={a.actor_world_character.id})
        first = len(statements)
        statements.clear()
        many = gateway.node_candidates(world_id=a.world.id, world_character_ids={a.actor_world_character.id,
            a.target_world_character.id, b.actor_world_character.id, b.target_world_character.id})
        assert {node.world_character_id for node in many} == {a.actor_world_character.id, a.target_world_character.id}
        assert len(statements) == first and len(one) == 1
        event.remove(engine, "before_cursor_execute", record)
        # Corrupt/incomplete configuration must not reveal the live global name.
        db.delete(db.get(WorldCharacterConfiguration, a.target_world_character.id))
        db.flush()
        assert gateway.node_candidates(world_id=a.world.id, world_character_ids={a.target_world_character.id}) == []
    engine.dispose()


def test_t83_avatar_projection_uses_constant_queries_at_one_eight_and_supported_limit():
    from app.domains.characters.models import Character
    from app.domains.world_characters.models import WorldCharacter
    from app.runtime.world_characters.creation_configuration import initialize_created_world_character
    engine = sqlite_engine()
    with Session(engine, expire_on_commit=False) as db:
        fixture = seed_projection_fixture(db, suffix="avatar-limit")
        ids = [fixture.actor_world_character.id, fixture.target_world_character.id]
        for index in range(18):
            character = Character(id=f"avatar-limit-character-{index}", owner_id=fixture.owner.id,
                name=f"Avatar {index}", handle=f"avatar_limit_{index}", personality="Fixture", speech_style="Fixture",
                worldview="Fixture", persona_summary="Fixture", moderation_status="active")
            db.add(character)
            db.flush()
            role = WorldCharacter(id=f"avatar-limit-role-{index}", world_id=fixture.world.id,
                character_id=character.id, membership_id=fixture.actor_world_character.membership_id,
                role_key="student", status="active", character_contract_hash="a" * 64,
                world_contract_hash=fixture.world.contract_hash)
            db.add(role)
            db.flush()
            initialize_created_world_character(db, character=character, world_character=role)
            ids.append(role.id)
        db.commit()
        gateway = SqlAlchemyRelationshipGraphReadGateway(db, config=Settings(GRAPH_PROJECTION_ENABLED=False))
        statements, counts = [], []
        def record(*_args):
            statements.append(1)
        event.listen(engine, "before_cursor_execute", record)
        for size in (1, 8, 20):
            statements.clear()
            nodes = gateway.node_candidates(world_id=fixture.world.id, world_character_ids=set(ids[:size]))
            assert {node.world_character_id for node in nodes} == set(ids[:size])
            assert all(node.world_id == fixture.world.id for node in nodes)
            counts.append(len(statements))
        event.remove(engine, "before_cursor_execute", record)
        assert counts[0] == counts[1] == counts[2]
        assert counts[0] <= 5
        assert not db.dirty and not db.new
    engine.dispose()


@pytest.mark.parametrize("value", ["javascript:alert(1)", "https://example.test/p.png?token=secret",
    "https://user:password@example.test/p.png", "/media/../private/key.png", "//example.test/p.png", "http://example.test/p.png"])
def test_t84_public_avatar_excludes_unsafe_or_credential_urls(value):
    assert _public_avatar(value) is None


def test_t98_t116_import_basis_media_survives_source_replacement_and_delete(tmp_path, monkeypatch):
    from app.domains.characters.models import Character
    from app.domains.characters.models_import import CharacterImportOrigin
    from app.domains.characters.contracts import ImportConfiguration, ImportProfile, ImportSettings
    from app.domains.characters.service.import_snapshots import capture_creation, get_import_snapshot
    from app.runtime.characters.management import _quarantine_agent_private_media
    from datetime import UTC, datetime
    engine = sqlite_engine()
    monkeypatch.setattr(settings, "MEDIA_ROOT", str(tmp_path / "managed-media"))
    root = settings.media_root_path / "characters" / "media-source"
    root.mkdir(parents=True)
    origin_file, private_file = root / "avatar.png", root / "private.png"
    origin_file.write_bytes(b"test-managed-avatar")
    private_file.write_bytes(b"test-unshared-private")
    with Session(engine) as db:
        fixture = seed_projection_fixture(db, suffix="retained-media")
        source = Character(id="media-source", owner_id=fixture.owner.id, name="Source", handle="media-source",
            personality="Initial", speech_style="Initial", worldview="Initial", persona_summary="Initial", moderation_status="active")
        copy = Character(id="media-copy", owner_id=fixture.owner.id, name="Copy", handle="media-copy",
            personality="Initial", speech_style="Initial", worldview="Initial", persona_summary="Initial", moderation_status="active")
        db.add_all([source, copy])
        db.flush()
        basis = capture_creation(db, character_id=source.id, provenance="media-fixture",
            configuration=ImportConfiguration(profile=ImportProfile(display_name="Source", handle="media-source",
                avatar_url="/media/characters/media-source/avatar.png"), settings=ImportSettings(personality="Initial")))
        db.add(CharacterImportOrigin(character_id=copy.id, snapshot_id=basis.id))
        db.commit()
        source.avatar_url = None
        db.commit()
        quarantine = _quarantine_agent_private_media(db, fixture.owner.id, source.id)
        assert origin_file.is_file() and not private_file.exists()
        quarantine.restore()
        assert origin_file.is_file() and private_file.is_file()
        quarantine = _quarantine_agent_private_media(db, fixture.owner.id, source.id)
        source.deleted_at = datetime.now(UTC)
        db.commit()
        quarantine.purge()
        assert origin_file.is_file() and not private_file.exists()
        row, payload = get_import_snapshot(db, copy.id)
        assert row.id == basis.id and payload.profile.avatar_url == "/media/characters/media-source/avatar.png"
        assert payload.settings.personality == "Initial"
        copy.deleted_at = datetime.now(UTC)
        db.commit()
        quarantine = _quarantine_agent_private_media(db, fixture.owner.id, source.id)
        quarantine.purge()
        assert not origin_file.exists()
    engine.dispose()
