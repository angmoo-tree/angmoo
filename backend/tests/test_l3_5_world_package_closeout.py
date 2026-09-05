from __future__ import annotations

from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
import sqlite3
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import Session, sessionmaker

from app import models
from app.domains.identity.dependencies import get_current_user
from app.core.db import Base, get_db
from app.domains.device_home.repository import (
    SqlAlchemyWorldSurfaceRepository,
)
from app.domains.world_packages.api.routes import router
from app.domains.world_packages.application.exclusion_scan import (
    WorldPackageExclusionError,
    scan_world_package_bytes,
)
from app.domains.world_packages.schemas.content import (
    AssetIndexDocument,
    CharactersDocument,
    PortableWorldDefinition,
    WorldCharactersDocument,
)
from app.domains.world_packages.contracts.export import (
    WorldPackageResolvedAssets,
    WorldPackageSourceIdentity,
)
from app.domains.world_packages.schemas.manifest import WorldPackageLicense
from app.domains.world_packages.infrastructure.filesystem_import_media import (
    FilesystemWorldPackageImportMedia,
)
from app.domains.world_packages.infrastructure.sqlalchemy_import_commit import (
    SqlAlchemyWorldPackageImportCommitter,
)
from app.domains.world_packages.infrastructure.zip_archive import (
    DeterministicWorldPackageZipArchive,
)


FIXTURE_ROOT = (
    Path(__file__).parent / "fixtures" / "world_packages" / "v1" / "valid"
)
FRONTEND_HEADERS = {"Origin": "http://127.0.0.1:3000"}
TARGET_OWNER_ID = "round-trip-target-owner"
PRIVATE_SENTINELS = (
    "source-owner-019ff9d5-private",
    "source-world-db-id-private",
    "source-character-db-id-private",
    "source-world-character-db-id-private",
    "synthetic-api-key-never-export",
    "app-secret-synthetic-never-export",
    "private-post-body-never-export",
    "private-comment-body-never-export",
    "private-memory-never-export",
    "private-p2-candidate-never-export",
    "private-p3-plan-never-export",
    "private-p4-result-never-export",
    "private-relationship-evidence-never-export",
    "private-ladybug-projection-never-export",
)


def _fixture(relative: str) -> dict:
    return json.loads((FIXTURE_ROOT / relative).read_text(encoding="utf-8"))


def _portable_archive() -> bytes:
    world = PortableWorldDefinition.model_validate(_fixture("content/world.json"))
    world = world.model_copy(
        update={
            "setting_description": (
                "달빛과 비늘등이 비치는 항구에서 주민들은 시장과 "
                "푸른 부두를 오가며 서로의 소식을 나눕니다. "
            )
            * 5,
            "daily_life_description": (
                "아침에는 상인들이 물건을 정리하고 안내인은 방문객의 "
                "질문에 답하며 저녁에는 하루의 사건을 돌아봅니다. "
            )
            * 5,
        }
    )
    return DeterministicWorldPackageZipArchive().build(
        identity=WorldPackageSourceIdentity(
            package_id="019ff9d5-559d-7452-b0f5-68f4964a2d46",
            next_version=1,
            created_at=datetime(2026, 8, 26, tzinfo=UTC),
        ),
        package_version=1,
        world=world,
        characters=CharactersDocument.model_validate(
            _fixture("content/characters.json")
        ),
        world_characters=WorldCharactersDocument.model_validate(
            _fixture("content/world-characters.json")
        ),
        asset_index=AssetIndexDocument(
            schema_version="assets-index-v1",
            assets=[],
        ),
        resolved_assets=WorldPackageResolvedAssets(assets=()),
        license=WorldPackageLicense(
            expression="CC-BY-4.0",
            attribution="round-trip fixture creator",
        ),
        license_text=None,
    ).content


def _write_source_private_runtime(source_root: Path) -> Path:
    for relative in ("canonical", "graph", "media", "secrets", "runtime", "logs"):
        (source_root / relative).mkdir(parents=True, exist_ok=True)
    database = source_root / "canonical" / "source.sqlite3"
    with sqlite3.connect(database) as connection:
        connection.execute(
            "CREATE TABLE private_runtime_state (kind TEXT, value TEXT)"
        )
        connection.executemany(
            "INSERT INTO private_runtime_state(kind, value) VALUES (?, ?)",
            [
                (f"private-{index}", value)
                for index, value in enumerate(PRIVATE_SENTINELS)
            ],
        )
        connection.commit()
    (source_root / "secrets" / "APP_SECRET").write_text(
        PRIVATE_SENTINELS[5], encoding="utf-8"
    )
    (source_root / "graph" / "ladybug-private.marker").write_text(
        PRIVATE_SENTINELS[-1], encoding="utf-8"
    )
    (source_root / "runtime" / "scheduler-private.marker").write_text(
        PRIVATE_SENTINELS[-3], encoding="utf-8"
    )
    return database


def _database_digest(engine) -> str:
    with engine.connect() as connection:
        dbapi_connection = connection.connection.driver_connection
        payload = "\n".join(dbapi_connection.iterdump()).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _count(db: Session, model) -> int:
    return int(db.scalar(select(func.count()).select_from(model)) or 0)


def _runtime_rows_are_zero(db: Session) -> None:
    for model in (
        models.CharacterState,
        models.CharacterActiveWorld,
        models.LlmCredential,
        models.AgentActivitySetting,
        models.AgentImageGenerationSetting,
        models.WorldActivityCandidate,
        models.WorldActivityRepertoire,
        models.WorldCharacterSetupAttempt,
        models.WorldCommunityProfile,
        models.DailyActivityPlan,
        models.DailyActivityPlanItem,
        models.Post,
        models.Comment,
        models.SocialEvent,
        models.SocialEventEvidence,
        models.RelationshipState,
        models.RelationshipStateChange,
        models.GraphProjectionOutbox,
    ):
        assert _count(db, model) == 0, model.__name__


def _target_runtime(target_root: Path) -> SimpleNamespace:
    canonical_root = target_root / "canonical"
    media_root = target_root / "media"
    runtime_root = target_root / "runtime"
    graph_root = target_root / "graph"
    for root in (canonical_root, media_root, runtime_root, graph_root):
        root.mkdir(parents=True, exist_ok=True)
    engine = create_engine(
        f"sqlite:///{canonical_root / 'target.sqlite3'}",
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(engine, "connect")
    def _sqlite_contract(dbapi_connection, _connection_record) -> None:
        dbapi_connection.execute("PRAGMA foreign_keys=ON")
        dbapi_connection.execute("PRAGMA busy_timeout=5000")
        dbapi_connection.execute("PRAGMA journal_mode=WAL")

    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    owner = models.User(
        id=TARGET_OWNER_ID,
        email="round-trip-target@example.test",
        display_name="Round Trip Target",
        display_name_normalized="round trip target",
        privacy_policy_version="test",
        terms_version="test",
        profile_setup_completed=True,
    )
    with factory() as db:
        db.add(owner)
        db.commit()

    media = FilesystemWorldPackageImportMedia(
        media_root=media_root,
        runtime_root=runtime_root,
        media_url_path="/media",
    )
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    app.state.runtime_settings = SimpleNamespace(
        media_root_path=media_root,
        media_url_path="/media",
    )
    app.state.runtime_config = None
    app.state.runtime_composition = None
    app.state.world_package_import_committer = (
        SqlAlchemyWorldPackageImportCommitter(factory, media=media)
    )

    def db_dependency():
        with factory() as db:
            yield db

    app.dependency_overrides[get_db] = db_dependency
    app.dependency_overrides[get_current_user] = lambda: owner
    return SimpleNamespace(
        client=TestClient(app, base_url="http://127.0.0.1:3000"),
        engine=engine,
        factory=factory,
        graph_root=graph_root,
        runtime_root=runtime_root,
    )


def _stage(client: TestClient, package: bytes) -> dict:
    response = client.post(
        "/api/v1/world-package-imports/stage",
        headers=FRONTEND_HEADERS,
        files={
            "package": (
                "round-trip.angmoo-world",
                package,
                "application/vnd.angmoo.world+zip",
            )
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _commit(client: TestClient, prepared: dict):
    preview = prepared["preview"]
    return client.post(
        f"/api/v1/world-package-imports/{preview['operation_id']}/commit",
        headers={
            **FRONTEND_HEADERS,
            "X-World-Package-Preview-Token": prepared["preview_token"],
            "Idempotency-Key": "clean-clone-round-trip",
        },
        json={
            "expected_content_digest": preview["content_digest"],
            "duplicate_strategy": "reject",
        },
    )


def test_two_data_root_round_trip_excludes_private_runtime_and_evolves_independently(
    tmp_path: Path,
) -> None:
    source_root = tmp_path / "source-runtime"
    source_database = _write_source_private_runtime(source_root)
    package = _portable_archive()
    export_path = source_root / "exports" / "round-trip.angmoo-world"
    export_path.parent.mkdir()
    export_path.write_bytes(package)
    package_digest = hashlib.sha256(package).hexdigest()

    report = scan_world_package_bytes(
        package,
        forbidden_values=PRIVATE_SENTINELS,
    )
    assert report.json_document_count == 5

    target = _target_runtime(tmp_path / "target-runtime")
    prepared = _stage(target.client, package)
    preview = prepared["preview"]
    assert preview["world_name"]
    assert len(preview["character_names"]) == 1
    assert preview["excluded_owner_controlled_characters"] == 0
    assert preview["excluded_runtime_records"] == 0
    assert preview["blocking_issues"] == []

    committed = _commit(target.client, prepared)
    assert committed.status_code == 201, committed.text
    result = committed.json()
    assert result["device_home_world_id"] == result["imported_world_id"]

    with target.factory() as db:
        assert _count(db, models.World) == 1
        assert _count(db, models.Character) == 1
        assert _count(db, models.WorldCharacter) == 1
        _runtime_rows_are_zero(db)
        home = SqlAlchemyWorldSurfaceRepository(db).list_worlds(
            owner_user_id=TARGET_OWNER_ID,
            surface="device_home",
            limit=20,
            cursor=None,
        )
        assert [item.world_id for item in home.items] == [
            result["imported_world_id"]
        ]
        imported_world = db.get(models.World, result["imported_world_id"])
        assert imported_world is not None
        imported_world.tagline = "target-only independent evolution"
        db.commit()

    target_digest_after_local_change = _database_digest(target.engine)
    target.engine.dispose()
    restarted = create_engine(
        f"sqlite:///{tmp_path / 'target-runtime' / 'canonical' / 'target.sqlite3'}"
    )
    restarted_factory = sessionmaker(bind=restarted, expire_on_commit=False)
    with restarted_factory() as db:
        imported_world = db.get(models.World, result["imported_world_id"])
        assert imported_world is not None
        assert imported_world.tagline == "target-only independent evolution"
    assert _database_digest(restarted) == target_digest_after_local_change
    restarted.dispose()

    assert hashlib.sha256(export_path.read_bytes()).hexdigest() == package_digest
    with sqlite3.connect(source_database) as connection:
        stored = {
            row[0]
            for row in connection.execute(
                "SELECT value FROM private_runtime_state"
            ).fetchall()
        }
    assert stored == set(PRIVATE_SENTINELS)
    assert not any(target.graph_root.iterdir())


def test_exclusion_scanner_rejects_private_value_and_forbidden_field() -> None:
    package = _portable_archive()
    private_marker = "synthetic-private-closeout-marker"
    try:
        scan_world_package_bytes(package, forbidden_values=(private_marker,))
    except WorldPackageExclusionError as exc:  # pragma: no cover - guard
        raise AssertionError("valid package rejected") from exc

    from io import BytesIO
    from zipfile import ZIP_STORED, ZipFile

    source = BytesIO(package)
    output = BytesIO()
    with ZipFile(source) as archive, ZipFile(output, "w", ZIP_STORED) as rewritten:
        for info in archive.infolist():
            payload = archive.read(info.filename)
            if info.filename == "content/world.json":
                document = json.loads(payload)
                document["app_secret"] = private_marker
                payload = json.dumps(document).encode("utf-8")
            rewritten.writestr(info, payload)

    for forbidden_values in ((), (private_marker,)):
        try:
            scan_world_package_bytes(
                output.getvalue(),
                forbidden_values=forbidden_values,
            )
        except WorldPackageExclusionError as exc:
            assert str(exc) in {
                "world_package_forbidden_field_detected",
                "world_package_private_value_detected",
            }
        else:  # pragma: no cover - guard
            raise AssertionError("private package passed exclusion scanner")
