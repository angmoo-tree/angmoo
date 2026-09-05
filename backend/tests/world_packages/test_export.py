from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from io import BytesIO
import json
from pathlib import Path
from types import SimpleNamespace
from zipfile import ZIP_STORED, ZipFile

from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app import models
from app.domains.identity.dependencies import get_current_user
from app.core.db import Base, get_db
from app.domains.world_packages.api.routes import (
    _stream_and_record_delivery,
    router,
)
from app.domains.world_packages.service.export import (
    ExportWorldPackage,
)
from app.domains.world_packages.utils.canonical import canonical_sha256
from app.domains.world_packages.schemas.content import (
    AssetIndexDocument,
    CharactersDocument,
    PortableWorldDefinition,
    WorldCharactersDocument,
)
from app.domains.world_packages.contracts.export import (
    WorldPackageExportRegistryRecord,
    WorldPackageResolvedAssets,
    WorldPackageSourceIdentity,
    WorldPackageVersionPreview,
)
from app.domains.world_packages.exceptions import (
    WorldPackageContractError,
    WorldPackageReasonCode,
)
from app.domains.world_packages.schemas.manifest import WorldPackageLicense
from app.domains.world_packages.contracts.seed import WorldPackageSourceSnapshot
from app.domains.world_packages.storage.exports import (
    FilesystemWorldPackageExportArtifacts,
)
from app.domains.world_packages.storage.export_assets import (
    ManagedMediaPackageAssets,
)
from app.domains.world_packages.models import (
    WorldPackageExport,
    WorldPackageSource,
)
from app.domains.world_packages.infrastructure.sqlalchemy_source_snapshot import (
    SqlAlchemyWorldPackageSourceSnapshot,
)
from app.domains.world_packages.archive.export import (
    DeterministicWorldPackageZipArchive,
)
from app.domains.worlds.domain.reserved_roles import (
    NO_SPECIFIC_ROLE_PORTABLE_REF,
)
from app.domains.worlds.infrastructure.sqlalchemy_reserved_roles import (
    ensure_no_specific_role,
)
from app.domains.worlds.public import world_contract_hash


FIXTURE_ROOT = (
    Path(__file__).parents[1] / "fixtures" / "world_packages" / "v1" / "valid"
)
FRONTEND_HEADERS = {"Origin": "http://127.0.0.1:3000"}
LICENSE_REQUEST = {
    "license_expression": "CC-BY-4.0",
    "attribution": "Angmoo fixture creator",
    "source_url": "https://example.test/worlds/fixture",
    "confirm_export_rights": True,
    "confirm_license": True,
    "confirm_exclusions": True,
}


def _json(relative: str) -> dict:
    return json.loads((FIXTURE_ROOT / relative).read_text(encoding="utf-8"))


def _portable_snapshot() -> WorldPackageSourceSnapshot:
    world = PortableWorldDefinition.model_validate(_json("content/world.json"))
    characters = CharactersDocument.model_validate(
        _json("content/characters.json")
    )
    world_characters = WorldCharactersDocument.model_validate(
        _json("content/world-characters.json")
    )
    return WorldPackageSourceSnapshot(
        source_world_id="private-source-world-id",
        source_fingerprint=canonical_sha256(
            {
                "world": world,
                "characters": characters,
                "world_characters": world_characters,
            }
        ),
        world=world,
        characters=tuple(characters.characters),
        world_characters=tuple(world_characters.characters),
        excluded_owner_controlled_characters=1,
    )


class _FakeSource:
    def __init__(self, snapshot: WorldPackageSourceSnapshot) -> None:
        self.value = snapshot
        self.runtime_noise = 0

    def snapshot(
        self, *, source_world_id: str, local_owner_id: str
    ) -> WorldPackageSourceSnapshot:
        assert source_world_id == self.value.source_world_id
        assert local_owner_id == "private-owner-id"
        return self.value


class _FakeAssets:
    def resolve_export_assets(self, *, candidates):
        del candidates
        return WorldPackageResolvedAssets(assets=())


class _FakeRegistry:
    def __init__(self) -> None:
        self.identity = WorldPackageSourceIdentity(
            package_id="019ff9d5-559d-7452-b0f5-68f4964a2d46",
            next_version=1,
            created_at=datetime(2026, 8, 25, 0, 0, tzinfo=UTC),
        )
        self.deliveries: list[WorldPackageExportRegistryRecord] = []

    def resolve_export_source(self, *, source_world_id: str):
        assert source_world_id == "private-source-world-id"
        return self.identity

    def preview_export_version(self, *, package_id: str, seed_digest: str):
        assert package_id == self.identity.package_id
        for record in self.deliveries:
            if record.seed_digest == seed_digest:
                return WorldPackageVersionPreview(
                    package_version=record.package_version,
                    replayed_seed=True,
                )
        return WorldPackageVersionPreview(
            package_version=len(self.deliveries) + 1,
            replayed_seed=False,
        )

    def record_export_delivery(self, record):
        self.deliveries.append(record)
        return record


def _exporter(source: _FakeSource, registry: _FakeRegistry) -> ExportWorldPackage:
    return ExportWorldPackage(
        source=source,
        assets=_FakeAssets(),
        registry=registry,
        archive=DeterministicWorldPackageZipArchive(),
    )


def test_same_seed_is_byte_reproducible_and_runtime_noise_is_excluded() -> None:
    source = _FakeSource(_portable_snapshot())
    registry = _FakeRegistry()
    exporter = _exporter(source, registry)
    license = WorldPackageLicense(
        expression="CC-BY-4.0",
        attribution="fixture creator",
        source_url="https://example.test/worlds/fixture",
    )

    first_preview, first = exporter.build(
        source_world_id=source.value.source_world_id,
        local_owner_id="private-owner-id",
        license=license,
        license_text=None,
    )
    source.runtime_noise += 1
    second_preview, second = exporter.build(
        source_world_id=source.value.source_world_id,
        local_owner_id="private-owner-id",
        license=license,
        license_text=None,
    )

    assert first_preview.seed_digest == second_preview.seed_digest
    assert first.archive_digest == second.archive_digest
    assert first.content == second.content
    assert first_preview.excluded_owner_controlled_characters == 1
    assert b"private-owner-id" not in first.content
    assert b"private-source-world-id" not in first.content

    with ZipFile(BytesIO(first.content)) as archive:
        assert archive.namelist() == sorted(archive.namelist())
        assert all(item.compress_type == ZIP_STORED for item in archive.infolist())
        assert all(item.date_time == (1980, 1, 1, 0, 0, 0) for item in archive.infolist())
        archive.testzip()


def test_successful_seed_then_seed_mutation_uses_the_next_version() -> None:
    source = _FakeSource(_portable_snapshot())
    registry = _FakeRegistry()
    exporter = _exporter(source, registry)
    license = WorldPackageLicense(expression="CC0-1.0")

    preview, archive = exporter.build(
        source_world_id=source.value.source_world_id,
        local_owner_id="private-owner-id",
        license=license,
        license_text=None,
    )
    registry.record_export_delivery(
        WorldPackageExportRegistryRecord(
            export_id="019ff9d5-559d-7452-b0f5-68f4964a2d47",
            package_id=preview.package_id,
            package_version=preview.package_version,
            source_world_id=source.value.source_world_id,
            seed_digest=preview.seed_digest,
            manifest_digest=archive.manifest_digest,
            license_expression=license.expression,
            delivery_mode="browser_download",
            delivered_at=datetime.now(UTC),
        )
    )
    replay_preview, replay = exporter.build(
        source_world_id=source.value.source_world_id,
        local_owner_id="private-owner-id",
        license=license,
        license_text=None,
    )
    assert replay_preview.package_version == 1
    assert replay.content == archive.content

    changed_world = source.value.world.model_copy(
        update={"tagline": "A changed portable seed"}
    )
    source.value = replace(
        source.value,
        source_fingerprint=canonical_sha256(changed_world),
        world=changed_world,
    )
    changed_preview, changed = exporter.build(
        source_world_id=source.value.source_world_id,
        local_owner_id="private-owner-id",
        license=license,
        license_text=None,
    )
    assert changed_preview.package_version == 2
    assert changed_preview.seed_digest != preview.seed_digest
    assert changed.content != archive.content


def test_managed_media_is_content_addressed_and_external_media_is_not_fetched(
    tmp_path: Path,
) -> None:
    media_root = tmp_path / "media"
    image_path = media_root / "characters" / "char-a" / "avatar.webp"
    image_path.parent.mkdir(parents=True)
    image = Image.new("RGB", (12, 8), (12, 34, 56))
    image.save(image_path, format="WEBP", lossless=True)

    from app.domains.world_packages.contracts.export import WorldPackageMediaCandidate

    candidates = (
        WorldPackageMediaCandidate(
            candidate_key="characters/char-0001:avatar",
            slot="character_avatar",
            source_url="/media/characters/char-a/avatar.webp",
            source_entity_id="char-a",
            alt_text="avatar",
        ),
        WorldPackageMediaCandidate(
            candidate_key="characters/char-0001:banner",
            slot="character_banner",
            source_url="https://example.test/external.webp",
            source_entity_id="char-a",
            alt_text="external",
        ),
    )
    resolved = ManagedMediaPackageAssets(media_root=media_root).resolve_export_assets(
        candidates=candidates
    )

    assert len(resolved.assets) == 1
    assert resolved.assets[0].asset.ref.startswith("assets/sha256-")
    assert resolved.assets[0].asset.ref.endswith(".webp")
    assert resolved.assets[0].asset.width == 12
    assert resolved.assets[0].asset.height == 8
    assert resolved.excluded_external_candidate_keys == (
        "characters/char-0001:banner",
    )


def _database_fixture(tmp_path: Path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'export.sqlite3'}",
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(engine, "connect")
    def _sqlite_contract(dbapi_connection, _connection_record) -> None:
        dbapi_connection.execute("PRAGMA foreign_keys=ON")
        dbapi_connection.execute("PRAGMA journal_mode=WAL")

    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    owner = models.User(
        id="private-owner-id",
        email="private-owner@example.test",
        display_name="Package Owner",
        display_name_normalized="package owner",
        privacy_policy_version="test",
        terms_version="test",
        profile_setup_completed=True,
    )
    world = models.World(
        id="private-source-world-id",
        slug="private-source-world",
        owner_user_id=owner.id,
        name="비늘항구의 밤",
        tagline="달빛 아래 앵무들이 함께 살아가는 항구 도시",
        setting_description="세계" * 100,
        daily_life_description="일상" * 75,
        genre_tags=["fantasy", "social"],
        tone_tags=["warm"],
        banner_alt_text="",
        timezone="Asia/Seoul",
        language="ko",
        visibility="unlisted",
        join_policy="approval_required",
        status="published",
        definition_version=1,
        row_version=1,
        contract_version="p0-contract-v1.1-world-creator",
        contract_hash="0" * 64,
        readiness_status="publish_ready",
        additional_generation_guidance="",
        create_idempotency_key="export-world-fixture",
    )
    membership = models.WorldMembership(
        id="membership-owner",
        world_id=world.id,
        user_id=owner.id,
        role="owner",
        status="active",
        joined_at=datetime.now(UTC),
    )
    role = models.WorldRole(
        id="role-guide",
        world_id=world.id,
        role_key="harbor_guide",
        name="항구 안내인",
        description="방문자를 안내합니다.",
        responsibilities=["안내"],
        allowed_activity_scope=["산책", "대화"],
        autonomous_allowed=True,
        status="enabled",
    )
    autonomous_character = models.Character(
        id="autonomous-character-id",
        owner_id=owner.id,
        name="망고",
        handle="export-mango",
        avatar_url="https://example.test/not-fetched.webp",
        banner_url=None,
        one_liner="항구를 산책하는 앵무",
        personality="밝고 다정합니다.",
        speech_style="따뜻하게 말합니다.",
        worldview="친구와 나누는 시간을 소중히 여깁니다.",
        topic_preferences="항구, 산책",
        safety_rules="비밀을 공개하지 않기",
        status="active",
        moderation_status="active",
        execution_mode="llm",
        promotion_usage_allowed=False,
        persona_summary="항구 안내인 망고",
    )
    owner_character = models.Character(
        id="owner-controlled-character-id",
        owner_id=owner.id,
        name="모모",
        handle="export-momo",
        avatar_url=None,
        banner_url=None,
        one_liner="owner controlled",
        personality="private owner persona",
        speech_style="private owner style",
        worldview="private owner worldview",
        topic_preferences="private",
        safety_rules="private",
        status="active",
        moderation_status="active",
        execution_mode="local",
        promotion_usage_allowed=False,
        persona_summary="must be excluded",
    )
    autonomous = models.WorldCharacter(
        id="autonomous-world-character-id",
        world_id=world.id,
        character_id=autonomous_character.id,
        membership_id=membership.id,
        role_key=role.role_key,
        status="active",
        control_mode="autonomous",
        owner_user_id=None,
        autonomous_enabled=False,
        activity_runtime_mode="routine_resident_v1",
        feed_runtime_mode="keyword_search_v1",
        local_profile={
            "role_description": "저녁 항구를 안내합니다.",
            "background": "오래전부터 항구에서 살았습니다.",
            "access_scope": ["docks", "market"],
            "runtime_cursor": "must-not-export",
        },
    )
    owner_controlled = models.WorldCharacter(
        id="owner-world-character-id",
        world_id=world.id,
        character_id=owner_character.id,
        membership_id=membership.id,
        role_key=role.role_key,
        status="active",
        control_mode="owner_controlled",
        owner_user_id=owner.id,
        autonomous_enabled=False,
        activity_runtime_mode="routine_resident_v1",
        feed_runtime_mode="keyword_search_v1",
        local_profile={"background": "must never export"},
    )
    with factory() as db:
        db.add(owner)
        db.add(world)
        db.flush()
        db.add_all([membership, role])
        db.flush()
        world.contract_hash = world_contract_hash(db, world)
        db.add_all(
            [
                autonomous_character,
                owner_character,
                autonomous,
                owner_controlled,
            ]
        )
        db.commit()
    return engine, factory, owner


def test_sqlalchemy_snapshot_filters_owner_controlled_and_runtime_state(
    tmp_path: Path,
) -> None:
    engine, factory, _owner = _database_fixture(tmp_path)
    with factory() as db:
        adapter = SqlAlchemyWorldPackageSourceSnapshot(db)
        first = adapter.snapshot(
            source_world_id="private-source-world-id",
            local_owner_id="private-owner-id",
        )
        assert len(first.characters) == 1
        assert len(first.world_characters) == 1
        assert first.characters[0].display_name == "망고"
        assert first.excluded_owner_controlled_characters == 1
        assert set(first.world_characters[0].access_scope) == {"docks", "market"}

        autonomous = db.get(models.WorldCharacter, "autonomous-world-character-id")
        assert autonomous is not None
        autonomous.autonomous_enabled = True
        db.flush()
        runtime_changed = adapter.snapshot(
            source_world_id="private-source-world-id",
            local_owner_id="private-owner-id",
        )
        assert runtime_changed.source_fingerprint == first.source_fingerprint

        character = db.get(models.Character, "autonomous-character-id")
        assert character is not None
        character.personality = "달라진 초기 페르소나"
        db.flush()
        seed_changed = adapter.snapshot(
            source_world_id="private-source-world-id",
            local_owner_id="private-owner-id",
        )
        assert seed_changed.source_fingerprint != first.source_fingerprint
    engine.dispose()


def test_sqlalchemy_snapshot_exports_explicit_no_role_portably_and_deterministically(
    tmp_path: Path,
) -> None:
    engine, factory, _owner = _database_fixture(tmp_path)
    with factory() as db:
        autonomous = db.get(models.WorldCharacter, "autonomous-world-character-id")
        world = db.get(models.World, "private-source-world-id")
        assert autonomous is not None
        assert world is not None
        ensure_no_specific_role(db, world_id=world.id)
        autonomous.role_key = "no_specific_role"
        db.flush()
        world.contract_hash = world_contract_hash(db, world)
        db.commit()

    with factory() as db:
        adapter = SqlAlchemyWorldPackageSourceSnapshot(db)
        first = adapter.snapshot(
            source_world_id="private-source-world-id",
            local_owner_id="private-owner-id",
        )
        second = adapter.snapshot(
            source_world_id="private-source-world-id",
            local_owner_id="private-owner-id",
        )

    reserved = next(
        role
        for role in first.world.roles
        if role.ref == NO_SPECIFIC_ROLE_PORTABLE_REF
    )
    assert reserved.name == "역할 없음"
    assert first.world_characters[0].role_ref == NO_SPECIFIC_ROLE_PORTABLE_REF
    assert first.source_fingerprint == second.source_fingerprint
    engine.dispose()


def test_sqlalchemy_snapshot_allows_world_with_only_owner_controlled_character(
    tmp_path: Path,
) -> None:
    engine, factory, _owner = _database_fixture(tmp_path)
    with factory() as db:
        autonomous = db.get(models.WorldCharacter, "autonomous-world-character-id")
        owner_controlled = db.get(models.WorldCharacter, "owner-world-character-id")
        role = db.scalar(
            select(models.WorldRole).where(
                models.WorldRole.world_id == "private-source-world-id"
            )
        )
        world = db.get(models.World, "private-source-world-id")
        assert autonomous is not None
        assert owner_controlled is not None
        assert role is not None
        assert world is not None
        db.delete(autonomous)
        owner_controlled.role_key = None
        db.delete(role)
        db.flush()
        world.contract_hash = world_contract_hash(db, world)
        db.commit()

    with factory() as db:
        snapshot = SqlAlchemyWorldPackageSourceSnapshot(db).snapshot(
            source_world_id="private-source-world-id",
            local_owner_id="private-owner-id",
        )

    assert snapshot.world.roles == []
    assert snapshot.characters == ()
    assert snapshot.world_characters == ()
    assert snapshot.excluded_owner_controlled_characters == 1
    engine.dispose()


def test_export_api_records_only_completed_download_and_replays_same_seed(
    tmp_path: Path,
) -> None:
    engine, factory, owner = _database_fixture(tmp_path)
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    media_root = tmp_path / "media"
    media_root.mkdir()
    app.state.runtime_settings = SimpleNamespace(
        media_root_path=media_root,
        media_url_path="/media",
    )
    app.state.runtime_config = None
    app.state.runtime_composition = None

    def db_dependency():
        with factory() as db:
            yield db

    app.dependency_overrides[get_db] = db_dependency
    app.dependency_overrides[get_current_user] = lambda: owner
    client = TestClient(app, base_url="http://127.0.0.1:3000")

    preview_response = client.post(
        "/api/v1/worlds/private-source-world-id/package-exports/preview",
        headers=FRONTEND_HEADERS,
        json=LICENSE_REQUEST,
    )
    assert preview_response.status_code == 200
    assert preview_response.json()["included_autonomous_characters"] == 1
    assert preview_response.json()["excluded_owner_controlled_characters"] == 1
    assert preview_response.json()["excluded_external_assets"] == 1

    prepared = client.post(
        "/api/v1/worlds/private-source-world-id/package-exports",
        headers={**FRONTEND_HEADERS, "Idempotency-Key": "export-fixture-1"},
        json=LICENSE_REQUEST,
    )
    assert prepared.status_code == 201
    payload = prepared.json()
    with factory() as db:
        assert int(db.scalar(select(func.count()).select_from(WorldPackageExport)) or 0) == 0
        assert db.scalar(select(WorldPackageSource.next_version)) == 1

    downloaded = client.get(
        payload["download_path"],
        headers={
            **FRONTEND_HEADERS,
            "X-World-Package-Download-Token": payload["download_token"],
        },
    )
    assert downloaded.status_code == 200
    assert downloaded.headers["content-type"].startswith(
        "application/vnd.angmoo.world+zip"
    )
    assert ".angmoo-world" in downloaded.headers["content-disposition"]
    with ZipFile(BytesIO(downloaded.content)) as archive:
        assert archive.testzip() is None
        portable_payload = b"\n".join(
            archive.read(path)
            for path in archive.namelist()
            if path.endswith((".json", ".txt"))
        )
        for forbidden in (
            b"private-owner-id",
            b"private-source-world-id",
            b"owner-controlled-character-id",
            b"owner-world-character-id",
            b"must never export",
            b"must-not-export",
            b"runtime_cursor",
            b"credential",
            b"app_secret",
        ):
            assert forbidden not in portable_payload.lower()

    with factory() as db:
        assert int(db.scalar(select(func.count()).select_from(WorldPackageExport)) or 0) == 1
        assert db.scalar(select(WorldPackageSource.next_version)) == 2

    replay = client.post(
        "/api/v1/worlds/private-source-world-id/package-exports",
        headers={**FRONTEND_HEADERS, "Idempotency-Key": "export-fixture-2"},
        json=LICENSE_REQUEST,
    )
    assert replay.status_code == 201
    replay_payload = replay.json()
    assert replay_payload["preview"]["package_version"] == 1
    replay_download = client.get(
        replay_payload["download_path"],
        headers={
            **FRONTEND_HEADERS,
            "X-World-Package-Download-Token": replay_payload["download_token"],
        },
    )
    assert replay_download.content == downloaded.content
    with factory() as db:
        assert int(db.scalar(select(func.count()).select_from(WorldPackageExport)) or 0) == 1
        assert db.scalar(select(WorldPackageSource.next_version)) == 2
    engine.dispose()


def test_cancelled_stream_removes_artifact_without_consuming_version(
    tmp_path: Path,
) -> None:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as db:
        db.add(
            WorldPackageSource(
                package_id="019ff9d5-559d-7452-b0f5-68f4964a2d46",
                source_world_id="source-world",
                next_version=1,
            )
        )
        db.commit()

    store = FilesystemWorldPackageExportArtifacts(tmp_path / "runtime")
    artifact, _token, _replayed = store.create(
        operation_id="019ff9d5-559d-7452-b0f5-68f4964a2d47",
        owner_id="owner",
        filename="world-v1.angmoo-world",
        content=b"package-content",
        package_id="019ff9d5-559d-7452-b0f5-68f4964a2d46",
        package_version=1,
        source_world_id="source-world",
        seed_digest="a" * 64,
        manifest_digest="b" * 64,
        license_expression="CC0-1.0",
        request_digest="c" * 64,
        idempotency_key="cancelled-export",
    )
    stream = _stream_and_record_delivery(
        artifact=artifact,
        artifact_store=store,
        session_factory=factory,
    )
    assert next(stream) == b"package-content"
    stream.close()
    assert not artifact.path.exists()
    retry, _retry_token, replayed = store.create(
        operation_id="019ff9d5-559d-7452-b0f5-68f4964a2d48",
        owner_id="owner",
        filename="world-v1.angmoo-world",
        content=b"package-content",
        package_id="019ff9d5-559d-7452-b0f5-68f4964a2d46",
        package_version=1,
        source_world_id="source-world",
        seed_digest="a" * 64,
        manifest_digest="b" * 64,
        license_expression="CC0-1.0",
        request_digest="c" * 64,
        idempotency_key="cancelled-export",
    )
    assert retry.operation_id != artifact.operation_id
    assert replayed is False
    store.discard(retry.operation_id)
    with factory() as db:
        assert int(db.scalar(select(func.count()).select_from(WorldPackageExport)) or 0) == 0
        assert db.get(WorldPackageSource, artifact.package_id).next_version == 1
    engine.dispose()


def test_native_save_as_requires_ack_and_cancel_does_not_consume_version(
    tmp_path: Path,
) -> None:
    engine, factory, owner = _database_fixture(tmp_path)
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    media_root = tmp_path / "media"
    media_root.mkdir()
    app.state.runtime_settings = SimpleNamespace(
        media_root_path=media_root,
        media_url_path="/media",
    )
    app.state.runtime_config = None
    app.state.runtime_composition = None

    def db_dependency():
        with factory() as db:
            yield db

    app.dependency_overrides[get_db] = db_dependency
    app.dependency_overrides[get_current_user] = lambda: owner
    client = TestClient(app, base_url="http://127.0.0.1:3000")

    first = client.post(
        "/api/v1/worlds/private-source-world-id/package-exports",
        headers={**FRONTEND_HEADERS, "Idempotency-Key": "native-export-1"},
        json=LICENSE_REQUEST,
    ).json()
    native_download = client.get(
        first["download_path"],
        headers={
            **FRONTEND_HEADERS,
            "X-World-Package-Download-Token": first["download_token"],
            "X-World-Package-Delivery-Mode": "tauri_save_as",
        },
    )
    assert native_download.status_code == 200
    with factory() as db:
        assert int(db.scalar(select(func.count()).select_from(WorldPackageExport)) or 0) == 0
        assert db.scalar(select(WorldPackageSource.next_version)) == 1

    acknowledgement = client.post(
        f"/api/v1/world-package-exports/{first['operation_id']}/delivery-ack",
        headers={
            **FRONTEND_HEADERS,
            "X-World-Package-Download-Token": first["download_token"],
        },
    )
    assert acknowledgement.status_code == 204
    with factory() as db:
        delivery = db.scalar(select(WorldPackageExport))
        assert delivery is not None
        assert delivery.delivery_mode == "tauri_save_as"
        assert db.scalar(select(WorldPackageSource.next_version)) == 2

    second = client.post(
        "/api/v1/worlds/private-source-world-id/package-exports",
        headers={**FRONTEND_HEADERS, "Idempotency-Key": "native-export-2"},
        json=LICENSE_REQUEST,
    ).json()
    cancelled = client.delete(
        f"/api/v1/world-package-exports/{second['operation_id']}",
        headers={
            **FRONTEND_HEADERS,
            "X-World-Package-Download-Token": second["download_token"],
        },
    )
    assert cancelled.status_code == 204
    expired = client.get(
        second["download_path"],
        headers={
            **FRONTEND_HEADERS,
            "X-World-Package-Download-Token": second["download_token"],
            "X-World-Package-Delivery-Mode": "tauri_save_as",
        },
    )
    assert expired.status_code == 410
    with factory() as db:
        assert int(db.scalar(select(func.count()).select_from(WorldPackageExport)) or 0) == 1
        assert db.scalar(select(WorldPackageSource.next_version)) == 2
    engine.dispose()


def test_pending_changed_seed_cannot_reuse_the_same_package_version(
    tmp_path: Path,
) -> None:
    store = FilesystemWorldPackageExportArtifacts(tmp_path / "runtime")
    first, _token, _replayed = store.create(
        operation_id="019ff9d5-559d-7452-b0f5-68f4964a2d47",
        owner_id="owner",
        filename="world-v1.angmoo-world",
        content=b"first-package",
        package_id="019ff9d5-559d-7452-b0f5-68f4964a2d46",
        package_version=1,
        source_world_id="source-world",
        seed_digest="a" * 64,
        manifest_digest="b" * 64,
        license_expression="CC0-1.0",
        request_digest="c" * 64,
        idempotency_key="first-export",
    )

    try:
        store.create(
            operation_id="019ff9d5-559d-7452-b0f5-68f4964a2d48",
            owner_id="owner",
            filename="world-v1.angmoo-world",
            content=b"changed-package",
            package_id=first.package_id,
            package_version=1,
            source_world_id="source-world",
            seed_digest="d" * 64,
            manifest_digest="e" * 64,
            license_expression="CC0-1.0",
            request_digest="f" * 64,
            idempotency_key="changed-export",
        )
    except WorldPackageContractError as exc:
        assert exc.reason_code is WorldPackageReasonCode.COMMIT_CONFLICT
    else:
        raise AssertionError("changed seed reused an active package version")

    store.discard(first.operation_id)
    retry, _retry_token, replayed = store.create(
        operation_id="019ff9d5-559d-7452-b0f5-68f4964a2d49",
        owner_id="owner",
        filename="world-v1.angmoo-world",
        content=b"changed-package",
        package_id=first.package_id,
        package_version=1,
        source_world_id="source-world",
        seed_digest="d" * 64,
        manifest_digest="e" * 64,
        license_expression="CC0-1.0",
        request_digest="f" * 64,
        idempotency_key="changed-export",
    )
    assert retry.package_version == 1
    assert replayed is False
    store.discard(retry.operation_id)


def test_export_artifact_store_removes_startup_orphans(
    tmp_path: Path,
) -> None:
    runtime_root = tmp_path / "runtime"
    orphan_directory = (
        runtime_root
        / "world-packages"
        / "exports"
        / "019ff9d5-559d-7452-b0f5-68f4964a2d50"
    )
    orphan_directory.mkdir(parents=True)
    (orphan_directory / "package.pending").write_bytes(b"interrupted-export")

    FilesystemWorldPackageExportArtifacts(runtime_root)

    assert not orphan_directory.exists()
