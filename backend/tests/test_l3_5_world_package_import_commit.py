from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
import hashlib
from io import BytesIO
import json
from pathlib import Path
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image
import pytest
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import Session, sessionmaker

from app import models
from app.api.v1.deps import get_current_user
from app.core.db import Base, get_db
from app.domains.device_home.infrastructure.sqlalchemy_world_surface_repository import (
    SqlAlchemyWorldSurfaceRepository,
)
from app.domains.world_packages.api.routes import router
from app.domains.world_packages.domain.content import (
    AssetIndexDocument,
    CharactersDocument,
    ManagedImageAsset,
    PortableWorldDefinition,
    WorldCharactersDocument,
)
from app.domains.world_packages.domain.errors import (
    WorldPackageContractError,
    WorldPackageReasonCode,
)
from app.domains.world_packages.domain.export import (
    WorldPackageResolvedAsset,
    WorldPackageResolvedAssets,
    WorldPackageSourceIdentity,
)
from app.domains.world_packages.domain.manifest import WorldPackageLicense
from app.domains.world_packages.domain.preview import (
    WorldPackageNormalizedAsset,
    WorldPackageNormalizedAssetPayload,
)
from app.domains.world_packages.infrastructure.filesystem_import_media import (
    FilesystemWorldPackageImportMedia,
)
from app.domains.world_packages.infrastructure.sqlalchemy_import_commit import (
    SqlAlchemyWorldPackageImportCommitter,
)
from app.domains.world_packages.infrastructure.sqlalchemy_destination_seed import (
    SqlAlchemyWorldPackageDestinationSeed,
)
from app.domains.world_packages.infrastructure.zip_archive import (
    DeterministicWorldPackageZipArchive,
)


FIXTURE_ROOT = (
    Path(__file__).parent / "fixtures" / "world_packages" / "v1" / "valid"
)
FRONTEND_HEADERS = {"Origin": "http://127.0.0.1:3000"}
OWNER_ID = "package-import-owner"


def _fixture(relative: str) -> dict:
    return json.loads((FIXTURE_ROOT / relative).read_text(encoding="utf-8"))


def _archive(*, with_image: bool = False, no_specific_role: bool = False) -> bytes:
    world_payload = _fixture("content/world.json")
    world_characters_payload = _fixture("content/world-characters.json")
    if no_specific_role:
        world_payload["roles"].append(
            {
                "allowed_activity_scope": [],
                "autonomous_allowed": True,
                "description": "별도의 World 역할을 지정하지 않은 캐릭터",
                "name": "역할 없음",
                "ref": "roles/no-specific-role",
                "responsibilities": [],
            }
        )
        world_characters_payload["characters"][0]["role_ref"] = (
            "roles/no-specific-role"
        )
    world = PortableWorldDefinition.model_validate(world_payload)
    world = world.model_copy(
        update={
            "setting_description": (
                "달빛과 비늘등이 물결에 비치는 항구에서 주민들은 "
                "푸른 부두와 시장을 오가며 서로의 소식을 나눕니다. "
            )
            * 5,
            "daily_life_description": (
                "아침에는 상인들이 물건을 정리하고 안내인은 방문객의 "
                "질문에 답하며, 저녁에는 비늘등을 밝히고 하루의 작은 "
                "사건과 관계의 변화를 함께 돌아봅니다. "
            )
            * 5,
        }
    )
    characters = CharactersDocument.model_validate(
        _fixture("content/characters.json")
    )
    world_characters = WorldCharactersDocument.model_validate(
        world_characters_payload
    )
    assets = AssetIndexDocument(schema_version="assets-index-v1", assets=[])
    resolved = WorldPackageResolvedAssets(assets=())
    if with_image:
        source = Image.new("RGB", (12, 8), (12, 34, 56))
        exif = Image.Exif()
        exif[0x010E] = "private metadata must be stripped"
        stream = BytesIO()
        source.save(stream, format="WEBP", lossless=True, exif=exif)
        content = stream.getvalue()
        digest = hashlib.sha256(content).hexdigest()
        reference = f"assets/sha256-{digest}.webp"
        asset = ManagedImageAsset(
            ref=reference,
            sha256=digest,
            bytes=len(content),
            media_type="image/webp",
            width=12,
            height=8,
            alt_text="fixture banner",
        )
        world = world.model_copy(update={"banner_asset_ref": reference})
        assets = AssetIndexDocument(
            schema_version="assets-index-v1",
            assets=[asset],
        )
        resolved = WorldPackageResolvedAssets(
            assets=(
                WorldPackageResolvedAsset(
                    candidate_key="world:banner",
                    asset=asset,
                    content=content,
                ),
            )
        )
    return DeterministicWorldPackageZipArchive().build(
        identity=WorldPackageSourceIdentity(
            package_id="019ff9d5-559d-7452-b0f5-68f4964a2d46",
            next_version=1,
            created_at=datetime(2026, 8, 25, tzinfo=UTC),
        ),
        package_version=1,
        world=world,
        characters=characters,
        world_characters=world_characters,
        asset_index=assets,
        resolved_assets=resolved,
        license=WorldPackageLicense(
            expression="CC-BY-4.0",
            attribution="fixture creator",
        ),
        license_text=None,
    ).content


@pytest.fixture
def import_runtime(tmp_path: Path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'package-import.sqlite3'}",
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
        id=OWNER_ID,
        email="package-import-owner@example.test",
        display_name="Package Import Owner",
        display_name_normalized="package import owner",
        privacy_policy_version="test",
        terms_version="test",
        profile_setup_completed=True,
    )
    with factory() as db:
        db.add(owner)
        db.commit()

    media_root = tmp_path / "media"
    runtime_root = tmp_path / "runtime"
    media_root.mkdir()
    runtime_root.mkdir()
    media = FilesystemWorldPackageImportMedia(
        media_root=media_root,
        runtime_root=runtime_root,
        media_url_path="/media",
    )
    committer = SqlAlchemyWorldPackageImportCommitter(
        factory,
        media=media,
    )
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    app.state.runtime_settings = SimpleNamespace(
        media_root_path=media_root,
        media_url_path="/media",
    )
    app.state.runtime_config = None
    app.state.runtime_composition = None
    app.state.world_package_import_committer = committer

    def db_dependency():
        with factory() as db:
            yield db

    app.dependency_overrides[get_db] = db_dependency
    app.dependency_overrides[get_current_user] = lambda: owner
    client = TestClient(app, base_url="http://127.0.0.1:3000")
    yield SimpleNamespace(
        app=app,
        client=client,
        committer=committer,
        engine=engine,
        factory=factory,
        media=media,
        media_root=media_root,
        runtime_root=runtime_root,
    )
    engine.dispose()


def _stage(client: TestClient, content: bytes) -> dict:
    response = client.post(
        "/api/v1/world-package-imports/stage",
        headers=FRONTEND_HEADERS,
        files={
            "package": (
                "world.angmoo-world",
                content,
                "application/vnd.angmoo.world+zip",
            )
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _commit(
    client: TestClient,
    prepared: dict,
    *,
    idempotency_key: str,
    strategy: str = "reject",
    digest: str | None = None,
):
    preview = prepared["preview"]
    return client.post(
        f"/api/v1/world-package-imports/{preview['operation_id']}/commit",
        headers={
            **FRONTEND_HEADERS,
            "X-World-Package-Preview-Token": prepared["preview_token"],
            "Idempotency-Key": idempotency_key,
        },
        json={
            "expected_content_digest": digest or preview["content_digest"],
            "duplicate_strategy": strategy,
        },
    )


def _count(db: Session, model) -> int:
    return int(db.scalar(select(func.count()).select_from(model)) or 0)


def _database_digest(engine) -> str:
    with engine.connect() as connection:
        dbapi_connection = connection.connection.driver_connection
        payload = "\n".join(dbapi_connection.iterdump()).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


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


def test_commit_is_atomic_registers_one_home_world_and_replays_without_writes(
    import_runtime,
) -> None:
    prepared = _stage(import_runtime.client, _archive(with_image=True))
    with import_runtime.factory() as db:
        owner_before = (
            db.get(models.User, OWNER_ID).display_name,
            db.get(models.User, OWNER_ID).email,
        )

    first = _commit(
        import_runtime.client,
        prepared,
        idempotency_key="package-import-success",
    )
    assert first.status_code == 201, first.text
    result = first.json()
    assert result["replayed"] is False
    assert result["device_home_world_id"] == result["imported_world_id"]

    with import_runtime.factory() as db:
        assert _count(db, models.World) == 1
        assert _count(db, models.WorldMembership) == 1
        assert _count(db, models.Character) == 1
        assert _count(db, models.WorldCharacter) == 1
        assert _count(db, models.WorldPackageImport) == 1
        assert _count(db, models.WorldPackageImportIdMap) == 4
        membership = db.scalar(select(models.WorldMembership))
        assert membership is not None and membership.role == "owner"
        character = db.scalar(select(models.Character))
        world_character = db.scalar(select(models.WorldCharacter))
        assert character is not None and character.owner_id == OWNER_ID
        assert world_character is not None
        assert world_character.control_mode == "autonomous"
        assert world_character.owner_user_id is None
        assert world_character.autonomous_enabled is False
        _runtime_rows_are_zero(db)
        home = SqlAlchemyWorldSurfaceRepository(db).list_worlds(
            owner_user_id=OWNER_ID,
            surface="device_home",
            limit=20,
            cursor=None,
        )
        assert [item.world_id for item in home.items] == [
            result["imported_world_id"]
        ]
        owner_after = (
            db.get(models.User, OWNER_ID).display_name,
            db.get(models.User, OWNER_ID).email,
        )
        assert owner_after == owner_before

    final_root = (
        import_runtime.media_root
        / "world-package-imports"
        / result["import_id"]
    )
    imported_files = tuple(final_root.glob("sha256-*.webp"))
    assert len(imported_files) == 1
    with Image.open(imported_files[0]) as image:
        assert image.format == "WEBP"
        assert not image.getexif()

    replay = _commit(
        import_runtime.client,
        prepared,
        idempotency_key="package-import-success",
    )
    assert replay.status_code == 201, replay.text
    assert replay.json() == {**result, "replayed": True}
    with import_runtime.factory() as db:
        assert _count(db, models.World) == 1
        assert _count(db, models.WorldPackageImport) == 1
        assert _count(db, models.WorldPackageImportIdMap) == 4


def test_commit_maps_portable_no_role_to_canonical_reserved_role(
    import_runtime,
) -> None:
    prepared = _stage(
        import_runtime.client,
        _archive(no_specific_role=True),
    )
    committed = _commit(
        import_runtime.client,
        prepared,
        idempotency_key="package-import-no-specific-role",
    )
    assert committed.status_code == 201, committed.text

    with import_runtime.factory() as db:
        world_character = db.scalar(select(models.WorldCharacter))
        reserved = db.scalar(
            select(models.WorldRole).where(
                models.WorldRole.role_key == "no_specific_role"
            )
        )
        assert world_character is not None
        assert world_character.role_key == "no_specific_role"
        assert reserved is not None
        assert reserved.name == "역할 없음"
        assert reserved.description == "별도의 World 역할을 지정하지 않은 캐릭터"
        assert reserved.responsibilities == []
        assert reserved.allowed_activity_scope == []
        assert reserved.autonomous_allowed is True


def test_media_promotion_failure_rolls_back_all_rows_and_is_retryable(
    import_runtime,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sentinel = import_runtime.media_root / "existing-user-media.bin"
    sentinel.write_bytes(b"preserve-existing-user-media")
    sentinel_digest = hashlib.sha256(sentinel.read_bytes()).hexdigest()
    prepared = _stage(import_runtime.client, _archive(with_image=True))
    database_digest = _database_digest(import_runtime.engine)
    original_promote = import_runtime.media.promote

    def fail_promotion(*, import_id: str) -> None:
        del import_id
        raise WorldPackageContractError(WorldPackageReasonCode.COMMIT_FAILED)

    monkeypatch.setattr(import_runtime.media, "promote", fail_promotion)
    failed = _commit(
        import_runtime.client,
        prepared,
        idempotency_key="package-import-retry",
    )
    assert failed.status_code == 409
    assert failed.json()["detail"] == "world_package_commit_failed"
    with import_runtime.factory() as db:
        for model in (
            models.World,
            models.WorldMembership,
            models.Character,
            models.WorldCharacter,
            models.WorldPackageImport,
            models.WorldPackageImportIdMap,
        ):
            assert _count(db, model) == 0
    assert hashlib.sha256(sentinel.read_bytes()).hexdigest() == sentinel_digest
    assert _database_digest(import_runtime.engine) == database_digest
    assert not any(
        (import_runtime.media_root / "world-package-imports").iterdir()
    )

    monkeypatch.setattr(import_runtime.media, "promote", original_promote)
    retried = _commit(
        import_runtime.client,
        prepared,
        idempotency_key="package-import-retry",
    )
    assert retried.status_code == 201, retried.text


def test_seed_failure_after_partial_flush_preserves_existing_data(
    import_runtime,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepared = _stage(import_runtime.client, _archive(with_image=True))
    database_digest = _database_digest(import_runtime.engine)
    original_seed = SqlAlchemyWorldPackageDestinationSeed.seed

    def fail_after_seed(self, request):
        original_seed(self, request)
        raise WorldPackageContractError(WorldPackageReasonCode.COMMIT_FAILED)

    monkeypatch.setattr(
        SqlAlchemyWorldPackageDestinationSeed,
        "seed",
        fail_after_seed,
    )
    failed = _commit(
        import_runtime.client,
        prepared,
        idempotency_key="package-import-seed-failure",
    )
    assert failed.status_code == 409
    assert failed.json()["detail"] == "world_package_commit_failed"
    assert _database_digest(import_runtime.engine) == database_digest
    assert not any(
        (import_runtime.media_root / "world-package-imports").iterdir()
    )
    assert not any(
        (
            import_runtime.runtime_root
            / "world-packages"
            / "import-media-journal"
        ).iterdir()
    )

    monkeypatch.setattr(
        SqlAlchemyWorldPackageDestinationSeed,
        "seed",
        original_seed,
    )
    retried = _commit(
        import_runtime.client,
        prepared,
        idempotency_key="package-import-seed-failure",
    )
    assert retried.status_code == 201, retried.text


def test_commit_revalidates_owner_digest_and_collision_preview(
    import_runtime,
) -> None:
    stale = _stage(import_runtime.client, _archive())

    import_runtime.app.dependency_overrides[get_current_user] = lambda: (
        SimpleNamespace(id="different-local-owner")
    )
    forbidden = _commit(
        import_runtime.client,
        stale,
        idempotency_key="package-import-owner-check",
    )
    assert forbidden.status_code == 403
    assert forbidden.json()["detail"] == "world_package_stage_forbidden"
    import_runtime.app.dependency_overrides[get_current_user] = lambda: (
        SimpleNamespace(id=OWNER_ID)
    )

    changed_digest = _commit(
        import_runtime.client,
        stale,
        idempotency_key="package-import-digest-check",
        digest="0" * 64,
    )
    assert changed_digest.status_code == 409
    assert changed_digest.json()["detail"] == "world_package_preview_changed"

    winner = _stage(import_runtime.client, _archive())
    committed = _commit(
        import_runtime.client,
        winner,
        idempotency_key="package-import-preview-winner",
    )
    assert committed.status_code == 201, committed.text
    database_digest = _database_digest(import_runtime.engine)

    stale_commit = _commit(
        import_runtime.client,
        stale,
        idempotency_key="package-import-stale-preview",
    )
    assert stale_commit.status_code == 409
    assert stale_commit.json()["detail"] == "world_package_preview_changed"
    assert _database_digest(import_runtime.engine) == database_digest

    refreshed = _stage(import_runtime.client, _archive())
    copied = _commit(
        import_runtime.client,
        refreshed,
        idempotency_key="package-import-refreshed-copy",
        strategy="independent_copy",
    )
    assert copied.status_code == 201, copied.text
    assert copied.json()["imported_world_id"] != committed.json()[
        "imported_world_id"
    ]


def test_duplicate_requires_explicit_independent_copy(import_runtime) -> None:
    first = _stage(import_runtime.client, _archive())
    committed = _commit(
        import_runtime.client,
        first,
        idempotency_key="package-import-original",
    )
    assert committed.status_code == 201, committed.text

    duplicate = _stage(import_runtime.client, _archive())
    assert duplicate["preview"]["collision_plan"]["duplicate_state"] == (
        "already_imported"
    )
    rejected = _commit(
        import_runtime.client,
        duplicate,
        idempotency_key="package-import-copy",
    )
    assert rejected.status_code == 409
    assert rejected.json()["detail"] == "world_package_duplicate"

    copied = _commit(
        import_runtime.client,
        duplicate,
        idempotency_key="package-import-copy",
        strategy="independent_copy",
    )
    assert copied.status_code == 201, copied.text
    assert copied.json()["imported_world_id"] != committed.json()[
        "imported_world_id"
    ]
    with import_runtime.factory() as db:
        assert _count(db, models.World) == 2
        assert _count(db, models.WorldPackageImport) == 2


def test_concurrent_idempotency_commits_once(import_runtime) -> None:
    prepared = [
        _stage(import_runtime.client, _archive()),
        _stage(import_runtime.client, _archive()),
    ]

    def commit(index: int):
        return _commit(
            import_runtime.client,
            prepared[index],
            idempotency_key="package-import-concurrent",
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        responses = list(executor.map(commit, range(2)))
    assert [item.status_code for item in responses] == [201, 201]
    payloads = [item.json() for item in responses]
    assert len({item["import_id"] for item in payloads}) == 1
    assert len({item["imported_world_id"] for item in payloads}) == 1
    assert sorted(item["replayed"] for item in payloads) == [False, True]
    with import_runtime.factory() as db:
        assert _count(db, models.World) == 1
        assert _count(db, models.WorldPackageImport) == 1


def test_ambiguous_commit_result_recovers_promoted_media(
    import_runtime,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepared = _stage(import_runtime.client, _archive(with_image=True))
    session_type = import_runtime.factory.class_
    original_commit = session_type.commit
    raised = False

    def commit_then_report_transport_failure(self) -> None:
        nonlocal raised
        original_commit(self)
        if not raised:
            raised = True
            raise RuntimeError("synthetic post-commit transport failure")

    monkeypatch.setattr(
        session_type,
        "commit",
        commit_then_report_transport_failure,
    )
    response = _commit(
        import_runtime.client,
        prepared,
        idempotency_key="package-import-ambiguous-commit",
    )
    assert response.status_code == 201, response.text
    result = response.json()
    assert result["replayed"] is False
    assert (
        import_runtime.media_root
        / "world-package-imports"
        / result["import_id"]
    ).is_dir()
    assert not any(
        (
            import_runtime.runtime_root
            / "world-packages"
            / "import-media-journal"
        ).iterdir()
    )
    with import_runtime.factory() as db:
        assert _count(db, models.World) == 1
        assert _count(db, models.WorldPackageImport) == 1


def test_media_journal_recovery_keeps_only_canonical_commits(
    tmp_path: Path,
) -> None:
    media = FilesystemWorldPackageImportMedia(
        media_root=tmp_path / "media",
        runtime_root=tmp_path / "runtime",
        media_url_path="/media",
    )
    content = b"verified-normalized-payload"
    digest = hashlib.sha256(content).hexdigest()
    source_ref = f"assets/sha256-{digest}.webp"
    metadata = (
        WorldPackageNormalizedAsset(
            source_ref=source_ref,
            normalized_ref=source_ref,
            normalized_sha256=digest,
            normalized_bytes=len(content),
            width=1,
            height=1,
            alt_text="fixture",
        ),
    )
    payloads = (
        WorldPackageNormalizedAssetPayload(
            source_ref=source_ref,
            normalized_ref=source_ref,
            normalized_sha256=digest,
            content=content,
        ),
    )
    orphan_id = "019ff9d5-559d-7452-b0f5-68f4964a2d80"
    media.prepare(import_id=orphan_id, metadata=metadata, payloads=payloads)
    media.promote(import_id=orphan_id)
    media.recover(import_exists=lambda _import_id: False)
    assert not (tmp_path / "media" / "world-package-imports" / orphan_id).exists()

    committed_id = "019ff9d5-559d-7452-b0f5-68f4964a2d81"
    media.prepare(import_id=committed_id, metadata=metadata, payloads=payloads)
    media.promote(import_id=committed_id)
    media.recover(import_exists=lambda value: value == committed_id)
    assert (tmp_path / "media" / "world-package-imports" / committed_id).is_dir()
    assert not (
        tmp_path
        / "runtime"
        / "world-packages"
        / "import-media-journal"
        / f"{committed_id}.json"
    ).exists()
