from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import importlib.util
import json
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import Session, sessionmaker

from app import models
from app.core.db import Base
from app.domains.world_packages.domain.errors import WorldPackageContractError
from app.domains.world_packages.infrastructure.sqlalchemy_destination_seed import (
    SqlAlchemyWorldPackageDestinationSeed,
)
from app.domains.world_packages.infrastructure.sqlalchemy_unit_of_work import (
    SqlAlchemyWorldPackageSeedUnitOfWork,
)
from app.domains.world_packages.public import (
    CharactersDocument,
    PortableWorldDefinition,
    WorldCharactersDocument,
    WorldPackageDestinationSeedRequest,
)
from app.domains.world_packages.ports import (
    WorldPackageDestinationSeedPort,
    WorldPackageSeedUnitOfWorkPort,
)


FIXTURE_ROOT = (
    Path(__file__).parent / "fixtures" / "world_packages" / "v1" / "valid"
)


def _json(relative: str) -> dict:
    return json.loads((FIXTURE_ROOT / relative).read_text(encoding="utf-8"))


def _request(**overrides) -> WorldPackageDestinationSeedRequest:
    world = PortableWorldDefinition.model_validate(_json("content/world.json"))
    characters = CharactersDocument.model_validate(
        _json("content/characters.json")
    )
    world_characters = WorldCharactersDocument.model_validate(
        _json("content/world-characters.json")
    )
    values = {
        "local_owner_id": "owner-package",
        "idempotency_key": "import-valid-fixture",
        "package_id": "019ff9d5-559d-7452-b0f5-68f4964a2d46",
        "package_version": 1,
        "content_digest": "a" * 64,
        "trust_state": "checksum_verified_unsigned",
        "license_expression": "CC-BY-4.0",
        "world": world,
        "characters": tuple(characters.characters),
        "world_characters": tuple(world_characters.characters),
    }
    values.update(overrides)
    return WorldPackageDestinationSeedRequest(**values)


def _session_factory(tmp_path: Path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'package-uow.sqlite3'}",
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(engine, "connect")
    def _sqlite_contract(dbapi_connection, _connection_record) -> None:
        dbapi_connection.execute("PRAGMA foreign_keys=ON")
        dbapi_connection.execute("PRAGMA busy_timeout=5000")
        dbapi_connection.execute("PRAGMA journal_mode=WAL")

    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as db:
        db.add(
            models.User(
                id="owner-package",
                email="owner-package@example.test",
                display_name="Package Owner",
                display_name_normalized="package owner",
                privacy_policy_version="test",
                terms_version="test",
                profile_setup_completed=True,
            )
        )
        db.commit()
    return engine, factory


def _count(db: Session, model) -> int:
    return int(db.scalar(select(func.count()).select_from(model)) or 0)


def test_destination_seed_is_a_caller_owned_port_and_commit_is_atomic(
    tmp_path: Path,
) -> None:
    engine, factory = _session_factory(tmp_path)
    with factory() as caller:
        adapter = SqlAlchemyWorldPackageDestinationSeed(caller)
        assert isinstance(adapter, WorldPackageDestinationSeedPort)
        result = adapter.seed(_request())

        with factory() as observer:
            assert _count(observer, models.WorldPackageImport) == 0
            assert _count(observer, models.World) == 0

        caller.commit()

    with factory() as db:
        assert _count(db, models.World) == 1
        assert _count(db, models.WorldMembership) == 1
        assert _count(db, models.Character) == 1
        assert _count(db, models.WorldCharacter) == 1
        assert _count(db, models.WorldPackageImport) == 1
        assert _count(db, models.WorldPackageImportIdMap) == 3
        assert db.get(models.World, result.imported_world_id).status == "published"
        assert db.get(models.World, result.imported_world_id).visibility == "unlisted"
        membership = db.scalar(select(models.WorldMembership))
        assert membership is not None and membership.reason == "world_package_import"
        character = db.scalar(select(models.Character))
        assert character is not None
        assert character.execution_mode == "llm"
        assert character.promotion_usage_allowed is False
        world_character = db.scalar(select(models.WorldCharacter))
        assert world_character is not None
        assert world_character.control_mode == "autonomous"
        assert world_character.status == "pending"
        assert world_character.owner_user_id is None
        assert world_character.autonomous_enabled is False
        assert world_character.activity_runtime_mode == "routine_resident_v1"
        assert world_character.feed_runtime_mode == "keyword_search_v1"
        assert _count(db, models.CharacterState) == 0
        assert _count(db, models.CharacterActiveWorld) == 0
        assert _count(db, models.LlmCredential) == 0
        assert _count(db, models.AgentActivitySetting) == 0
    engine.dispose()


def test_caller_rollback_removes_every_seeded_domain_row(tmp_path: Path) -> None:
    engine, factory = _session_factory(tmp_path)
    with factory() as db:
        SqlAlchemyWorldPackageDestinationSeed(db).seed(_request())
        db.rollback()

    with factory() as db:
        for model in (
            models.World,
            models.WorldMembership,
            models.WorldRole,
            models.Character,
            models.WorldCharacter,
            models.WorldPackageImport,
            models.WorldPackageImportIdMap,
        ):
            assert _count(db, model) == 0
    engine.dispose()


def test_committed_idempotency_replays_without_duplicate_rows(tmp_path: Path) -> None:
    engine, factory = _session_factory(tmp_path)
    with factory() as db:
        first = SqlAlchemyWorldPackageDestinationSeed(db).seed(_request())
        db.commit()
    with factory() as db:
        replay = SqlAlchemyWorldPackageDestinationSeed(db).seed(_request())
        db.commit()
        assert replay.replayed is True
        assert replay.import_id == first.import_id
        assert replay.imported_world_id == first.imported_world_id
        assert replay.id_mappings == first.id_mappings
    with factory() as db:
        assert _count(db, models.World) == 1
        assert _count(db, models.Character) == 1
        assert _count(db, models.WorldCharacter) == 1
        assert _count(db, models.WorldPackageImport) == 1
    engine.dispose()


def test_replay_resolves_when_registry_becomes_visible_after_world_lookup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Cover SQLite's deferred-BEGIN visibility window deterministically."""

    engine, factory = _session_factory(tmp_path)
    with factory() as db:
        first = SqlAlchemyWorldPackageDestinationSeed(db).seed(_request())
        db.commit()

    with factory() as db:
        adapter = SqlAlchemyWorldPackageDestinationSeed(db)
        find_import = adapter._registry.find_import
        lookup_count = 0

        def stale_once(*, local_owner_id: str, idempotency_key: str):
            nonlocal lookup_count
            lookup_count += 1
            if lookup_count == 1:
                return None
            return find_import(
                local_owner_id=local_owner_id,
                idempotency_key=idempotency_key,
            )

        monkeypatch.setattr(adapter._registry, "find_import", stale_once)
        replay = adapter.seed(_request())

        assert lookup_count == 2
        assert replay.replayed is True
        assert replay.import_id == first.import_id
        assert replay.imported_world_id == first.imported_world_id
        db.rollback()

    with factory() as db:
        assert _count(db, models.World) == 1
        assert _count(db, models.WorldPackageImport) == 1
    engine.dispose()


def test_idempotency_key_cannot_replay_different_package_content(
    tmp_path: Path,
) -> None:
    engine, factory = _session_factory(tmp_path)
    uow = SqlAlchemyWorldPackageSeedUnitOfWork(factory)
    uow.execute(_request())

    with pytest.raises(
        WorldPackageContractError, match="world_package_commit_conflict"
    ):
        uow.execute(_request(content_digest="b" * 64))

    with factory() as db:
        assert _count(db, models.World) == 1
        assert _count(db, models.WorldPackageImport) == 1
    engine.dispose()


def test_concurrent_same_idempotency_key_commits_one_import(tmp_path: Path) -> None:
    engine, factory = _session_factory(tmp_path)
    uow = SqlAlchemyWorldPackageSeedUnitOfWork(factory, max_attempts=8)
    assert isinstance(uow, WorldPackageSeedUnitOfWorkPort)
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _index: uow.execute(_request()), range(2)))

    assert len({result.import_id for result in results}) == 1
    assert len({result.imported_world_id for result in results}) == 1
    assert any(result.replayed for result in results)
    with factory() as db:
        assert _count(db, models.World) == 1
        assert _count(db, models.Character) == 1
        assert _count(db, models.WorldCharacter) == 1
        assert _count(db, models.WorldPackageImport) == 1
    engine.dispose()


def test_unknown_world_character_reference_rolls_back_without_partial_rows(
    tmp_path: Path,
) -> None:
    engine, factory = _session_factory(tmp_path)
    request = _request(characters=())
    with factory() as db:
        with pytest.raises(
            ValueError, match="world_character_references_unknown_character"
        ):
            SqlAlchemyWorldPackageDestinationSeed(db).seed(request)
        db.rollback()
    with factory() as db:
        assert _count(db, models.World) == 0
        assert _count(db, models.WorldPackageImport) == 0
    engine.dispose()


def test_registry_schema_freezes_fk_check_unique_and_guarded_downgrade() -> None:
    imports = models.WorldPackageImport.__table__
    maps = models.WorldPackageImportIdMap.__table__
    assert {fk.column.table.name for fk in imports.foreign_keys} == {"users", "worlds"}
    assert {
        constraint.name for constraint in imports.constraints if constraint.name
    } >= {
        "ck_world_package_imports_mode",
        "ck_world_package_imports_trust",
        "ck_world_package_imports_version",
        "uq_world_package_imports_owner_request",
    }
    assert {
        constraint.name for constraint in maps.constraints if constraint.name
    } >= {
        "ck_world_package_import_id_maps_kind",
        "uq_world_package_import_id_maps_local",
        "uq_world_package_import_id_maps_source",
    }

    migration = (
        Path(__file__).resolve().parents[1]
        / "app/alembic/versions/20260825_0083_world_package_registry.py"
    ).read_text(encoding="utf-8")
    assert 'down_revision: str | None = "20260819_0082"' in migration
    assert "cannot downgrade 0083 while" in migration


def test_alembic_0082_upgrade_downgrade_upgrade_on_sqlite(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "alembic-registry.sqlite3"
    url = f"sqlite+pysqlite:///{db_path.as_posix()}"
    engine = create_engine(url)
    Base.metadata.create_all(engine)
    for table in (
        models.WorldPackageImportIdMap.__table__,
        models.WorldPackageImport.__table__,
        models.WorldPackageExport.__table__,
        models.WorldPackageSource.__table__,
    ):
        table.drop(engine)
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "CREATE TABLE alembic_version (version_num VARCHAR(32) PRIMARY KEY)"
        )
        connection.exec_driver_sql(
            "INSERT INTO alembic_version(version_num) VALUES ('20260819_0082')"
        )
    engine.dispose()

    migration_path = (
        Path(__file__).resolve().parents[1]
        / "app/alembic/versions/20260825_0083_world_package_registry.py"
    )
    spec = importlib.util.spec_from_file_location(
        "world_package_registry_migration_0083",
        migration_path,
    )
    assert spec is not None and spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    def apply(operation: str) -> None:
        with create_engine(url).begin() as connection:
            context = MigrationContext.configure(connection)
            migration.op = Operations(context)
            getattr(migration, operation)()

    apply("upgrade")
    with create_engine(url).connect() as connection:
        tables = {
            row[0]
            for row in connection.exec_driver_sql(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        assert {
            "world_package_sources",
            "world_package_exports",
            "world_package_imports",
            "world_package_import_id_maps",
        } <= tables

    apply("downgrade")
    with create_engine(url).connect() as connection:
        tables = {
            row[0]
            for row in connection.exec_driver_sql(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        assert not {
            "world_package_sources",
            "world_package_exports",
            "world_package_imports",
            "world_package_import_id_maps",
        } & tables

    apply("upgrade")
    with create_engine(url).connect() as connection:
        tables = {
            row[0]
            for row in connection.exec_driver_sql(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        assert {
            "world_package_sources",
            "world_package_exports",
            "world_package_imports",
            "world_package_import_id_maps",
        } <= tables


def test_package_routes_do_not_reenter_the_legacy_api_route_folder() -> None:
    route_root = Path(__file__).resolve().parents[1] / "app/api/v1/routes"
    assert not any("world_package" in path.name for path in route_root.glob("*.py"))
    domain_route = (
        Path(__file__).resolve().parents[1]
        / "app/domains/world_packages/api/routes.py"
    )
    assert domain_route.is_file()
