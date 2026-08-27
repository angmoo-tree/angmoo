from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
import hashlib
from io import BytesIO
import json
from pathlib import Path
from types import SimpleNamespace
from zipfile import ZIP_DEFLATED, ZIP_STORED, ZipFile, ZipInfo

from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image
import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import models
from app.api.v1.deps import get_current_user
from app.core.db import Base, get_db
from app.domains.world_packages.api.routes import router
from app.domains.world_packages.application.stage_world_package import (
    StageWorldPackage,
)
from app.domains.world_packages.domain.canonical import (
    canonical_entry_index_digest,
    canonical_json_bytes,
)
from app.domains.world_packages.domain.collision_policy import (
    WorldPackageDuplicateState,
    plan_world_package_collisions,
)
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
from app.domains.world_packages.domain.import_state import (
    WorldPackageImportState,
    WorldPackageTrustState,
)
from app.domains.world_packages.domain.manifest import WorldPackageLicense
from app.domains.world_packages.domain.preview import (
    WorldPackagePreviewAssessment,
)
from app.domains.world_packages.infrastructure.filesystem_staging import (
    FilesystemWorldPackageStaging,
)
from app.domains.world_packages.infrastructure.sqlalchemy_models import (
    WorldPackageExport,
    WorldPackageImport,
    WorldPackageSource,
)
from app.domains.world_packages.infrastructure.sqlalchemy_preview_probe import (
    SqlAlchemyWorldPackagePreviewProbe,
)
from app.domains.world_packages.infrastructure.zip_archive import (
    DeterministicWorldPackageZipArchive,
)
from app.domains.world_packages.infrastructure.zip_import_archive import (
    ZipWorldPackageImportValidator,
)


FIXTURE_ROOT = (
    Path(__file__).parent / "fixtures" / "world_packages" / "v1" / "valid"
)
FRONTEND_HEADERS = {"Origin": "http://127.0.0.1:3000"}
OPERATION_ID = "019ff9d5-559d-7452-b0f5-68f4964a2d47"
OWNER_ID = "preview-owner"


def _fixture(relative: str) -> dict:
    return json.loads((FIXTURE_ROOT / relative).read_text(encoding="utf-8"))


def _base_documents():
    return (
        PortableWorldDefinition.model_validate(_fixture("content/world.json")),
        CharactersDocument.model_validate(_fixture("content/characters.json")),
        WorldCharactersDocument.model_validate(
            _fixture("content/world-characters.json")
        ),
    )


def _archive(*, with_metadata_image: bool = False) -> bytes:
    world, characters, world_characters = _base_documents()
    assets = AssetIndexDocument(schema_version="assets-index-v1", assets=[])
    resolved = WorldPackageResolvedAssets(assets=())
    if with_metadata_image:
        image = Image.new("RGB", (12, 8), (12, 34, 56))
        exif = Image.Exif()
        exif[0x010E] = "private metadata must be stripped"
        stream = BytesIO()
        image.save(stream, format="WEBP", lossless=True, exif=exif)
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
    built = DeterministicWorldPackageZipArchive().build(
        identity=WorldPackageSourceIdentity(
            package_id="019ff9d5-559d-7452-b0f5-68f4964a2d46",
            next_version=1,
            created_at=datetime(2026, 8, 25, 0, 0, tzinfo=UTC),
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
    )
    return built.content


def _payloads(content: bytes) -> dict[str, bytes]:
    with ZipFile(BytesIO(content), "r") as archive:
        return {name: archive.read(name) for name in archive.namelist()}


def _zip(
    payloads: dict[str, bytes],
    *,
    compression: dict[str, int] | None = None,
    symlink: str | None = None,
) -> bytes:
    stream = BytesIO()
    with ZipFile(stream, "w", allowZip64=False) as archive:
        for path in sorted(payloads):
            info = ZipInfo(path, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = (compression or {}).get(path, ZIP_STORED)
            info.create_system = 3
            info.external_attr = (
                (0o120777 if path == symlink else 0o100644) << 16
            )
            archive.writestr(info, payloads[path])
    return stream.getvalue()


def _replace_indexed_payload(
    payloads: dict[str, bytes],
    *,
    path: str,
    content: bytes,
) -> bytes:
    payloads[path] = content
    manifest = json.loads(payloads["manifest.json"])
    entry = next(item for item in manifest["entries"] if item["path"] == path)
    entry["bytes"] = len(content)
    entry["sha256"] = hashlib.sha256(content).hexdigest()
    manifest["content_digest"] = canonical_entry_index_digest(
        manifest["entries"]
    )
    payloads["manifest.json"] = canonical_json_bytes(manifest)
    return _zip(payloads)


async def _chunks(content: bytes):
    for start in range(0, len(content), 257):
        yield content[start : start + 257]


class _PreviewProbe:
    def assess(self, *, local_owner_id: str, package):
        assert local_owner_id == OWNER_ID
        return WorldPackagePreviewAssessment(
            trust_state=WorldPackageTrustState.CHECKSUM_VERIFIED_UNSIGNED,
            collision_plan=plan_world_package_collisions(
                world_name=package.world.name,
                character_hints=tuple(
                    (item.ref, item.display_name, item.handle_hint)
                    for item in package.characters.characters
                ),
                content_digest=package.manifest.content_digest,
                existing_world_slugs=frozenset({"fixture-world"}),
                existing_character_handles=frozenset({"mango"}),
                duplicate_state=WorldPackageDuplicateState.NEW_PACKAGE,
            ),
            warnings=("author_signature_not_available",),
        )


def _stage(
    tmp_path: Path,
    content: bytes,
    *,
    now: list[datetime] | None = None,
):
    current = now or [datetime(2026, 8, 26, 0, 0, tzinfo=UTC)]
    runtime = tmp_path / "runtime"
    store = FilesystemWorldPackageStaging(
        runtime,
        clock=lambda: current[0],
    )
    use_case = StageWorldPackage(
        staging=store,
        validator=ZipWorldPackageImportValidator(store),
        preview_probe=_PreviewProbe(),
        clock=lambda: current[0],
    )
    prepared = asyncio.run(
        use_case.stage(
            operation_id=OPERATION_ID,
            local_owner_id=OWNER_ID,
            chunks=_chunks(content),
        )
    )
    return store, use_case, prepared


def _validated_package(tmp_path: Path):
    store = FilesystemWorldPackageStaging(tmp_path / "runtime")
    asyncio.run(
        store.receive(
            operation_id=OPERATION_ID,
            owner_id=OWNER_ID,
            chunks=_chunks(_archive()),
        )
    )
    return ZipWorldPackageImportValidator(store).validate(
        operation_id=OPERATION_ID
    )


def test_valid_package_reaches_preview_ready_without_canonical_writes(
    tmp_path: Path,
) -> None:
    canonical = tmp_path / "canonical"
    media = tmp_path / "media"
    canonical.mkdir()
    media.mkdir()
    (canonical / "sentinel").write_text("unchanged", encoding="utf-8")
    (media / "sentinel").write_text("unchanged", encoding="utf-8")

    store, use_case, prepared = _stage(tmp_path, _archive())

    assert prepared.preview.state is WorldPackageImportState.PREVIEW_READY
    assert prepared.preview.trust_state is WorldPackageTrustState.CHECKSUM_VERIFIED_UNSIGNED
    assert prepared.preview.character_names == ("망고",)
    assert prepared.preview.collision_plan.planned_world_slug
    assert prepared.preview.excluded_runtime_records == 0
    assert (canonical / "sentinel").read_text(encoding="utf-8") == "unchanged"
    assert (media / "sentinel").read_text(encoding="utf-8") == "unchanged"
    assert [path.name for path in canonical.iterdir()] == ["sentinel"]
    assert [path.name for path in media.iterdir()] == ["sentinel"]

    preview = use_case.read_preview(
        operation_id=OPERATION_ID,
        local_owner_id=OWNER_ID,
        preview_token=prepared.preview_token,
    )
    assert preview.content_digest == prepared.preview.content_digest
    use_case.discard(
        operation_id=OPERATION_ID,
        local_owner_id=OWNER_ID,
        preview_token=prepared.preview_token,
    )
    assert not any(store.root.iterdir())


def test_preview_token_is_owner_bound_expires_and_startup_cleans_orphans(
    tmp_path: Path,
) -> None:
    now = [datetime(2026, 8, 26, 0, 0, tzinfo=UTC)]
    store, use_case, prepared = _stage(tmp_path, _archive(), now=now)
    with pytest.raises(WorldPackageContractError) as forbidden:
        use_case.read_preview(
            operation_id=OPERATION_ID,
            local_owner_id="different-owner",
            preview_token=prepared.preview_token,
        )
    assert forbidden.value.reason_code is WorldPackageReasonCode.STAGE_FORBIDDEN

    now[0] += timedelta(minutes=31)
    with pytest.raises(WorldPackageContractError) as expired:
        use_case.read_preview(
            operation_id=OPERATION_ID,
            local_owner_id=OWNER_ID,
            preview_token=prepared.preview_token,
        )
    assert expired.value.reason_code is WorldPackageReasonCode.STAGE_EXPIRED
    assert not any(store.root.iterdir())

    orphan = store.root / "019ff9d5-559d-7452-b0f5-68f4964a2d48"
    orphan.mkdir()
    (orphan / "untrusted").write_bytes(b"secret package bytes")
    restarted = FilesystemWorldPackageStaging(tmp_path / "runtime")
    assert not any(restarted.root.iterdir())


@pytest.mark.parametrize(
    ("mutator", "expected"),
    [
        (
            lambda values: _zip({**values, "../escape": b"x"}),
            WorldPackageReasonCode.PATH_UNSAFE,
        ),
        (
            lambda values: _zip(
                {**values, "CONTENT/world.json": values["content/world.json"]}
            ),
            WorldPackageReasonCode.PATH_UNSAFE,
        ),
        (
            lambda values: _zip(values, symlink="content/world.json"),
            WorldPackageReasonCode.ARCHIVE_INVALID,
        ),
        (
            lambda values: _zip(
                {**values, "LICENSE.txt": b"0" * (250 * 1024)},
                compression={"LICENSE.txt": ZIP_DEFLATED},
            ),
            WorldPackageReasonCode.ARCHIVE_LIMIT_EXCEEDED,
        ),
        (
            lambda values: _zip(values) + b"polyglot-tail",
            WorldPackageReasonCode.ARCHIVE_INVALID,
        ),
        (
            lambda values: _zip(
                {
                    key: value
                    for key, value in values.items()
                    if key != "content/world.json"
                }
            ),
            WorldPackageReasonCode.ARCHIVE_INVALID,
        ),
        (
            lambda values: _zip({**values, "assets/extra.txt": b"extra"}),
            WorldPackageReasonCode.ARCHIVE_INVALID,
        ),
        (
            lambda values: _zip(
                {**values, "content/world.json": b'{"tampered":true}'}
            ),
            WorldPackageReasonCode.INTEGRITY_MISMATCH,
        ),
    ],
)
def test_malicious_archives_fail_closed_without_raw_payload_leakage(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    mutator,
    expected: WorldPackageReasonCode,
) -> None:
    marker = "secret package bytes must never enter logs"
    payloads = _payloads(_archive())
    manifest = json.loads(payloads["manifest.json"])
    manifest["license"]["attribution"] = marker
    payloads["manifest.json"] = canonical_json_bytes(manifest)
    malicious = mutator(payloads)
    store = FilesystemWorldPackageStaging(tmp_path / "runtime")
    asyncio.run(
        store.receive(
            operation_id=OPERATION_ID,
            owner_id=OWNER_ID,
            chunks=_chunks(malicious),
        )
    )
    store.transition(
        operation_id=OPERATION_ID,
        owner_id=OWNER_ID,
        state=WorldPackageImportState.VALIDATING,
    )
    with pytest.raises(WorldPackageContractError) as rejected:
        ZipWorldPackageImportValidator(store).validate(operation_id=OPERATION_ID)
    assert rejected.value.reason_code is expected
    assert str(rejected.value) == expected.value
    assert marker not in caplog.text


@pytest.mark.parametrize(
    ("field", "value", "expected"),
    [
        (
            "license",
            {
                "expression": "MIT",
                "attribution": "",
                "source_url": None,
                "license_text_path": None,
            },
            WorldPackageReasonCode.LICENSE_MISSING,
        ),
        (
            "contract",
            "future-world-contract-v99",
            WorldPackageReasonCode.CONTRACT_UNSUPPORTED,
        ),
        (
            "reader",
            "99.0.0-1",
            WorldPackageReasonCode.APP_VERSION_UNSUPPORTED,
        ),
    ],
)
def test_unknown_license_contract_and_reader_version_fail_closed(
    tmp_path: Path,
    field: str,
    value,
    expected: WorldPackageReasonCode,
) -> None:
    payloads = _payloads(_archive())
    manifest = json.loads(payloads["manifest.json"])
    if field == "license":
        manifest["license"] = value
    elif field == "contract":
        manifest["compatibility"]["world_contract_version"] = value
    else:
        manifest["compatibility"]["min_reader_version"] = value
    payloads["manifest.json"] = canonical_json_bytes(manifest)
    content = _zip(payloads)
    store = FilesystemWorldPackageStaging(tmp_path / "runtime")
    asyncio.run(
        store.receive(
            operation_id=OPERATION_ID,
            owner_id=OWNER_ID,
            chunks=_chunks(content),
        )
    )
    with pytest.raises(WorldPackageContractError) as rejected:
        ZipWorldPackageImportValidator(store).validate(operation_id=OPERATION_ID)
    assert rejected.value.reason_code is expected


@pytest.mark.parametrize("mutation", ["missing_role", "duplicate_role"])
def test_semantically_invalid_world_references_fail_after_integrity_passes(
    tmp_path: Path,
    mutation: str,
) -> None:
    payloads = _payloads(_archive())
    world = json.loads(payloads["content/world.json"])
    if mutation == "missing_role":
        world["places"][0]["access_role_refs"] = ["roles/missing"]
    else:
        world["roles"].append(dict(world["roles"][0]))
    content = _replace_indexed_payload(
        payloads,
        path="content/world.json",
        content=canonical_json_bytes(world),
    )
    store = FilesystemWorldPackageStaging(tmp_path / "runtime")
    asyncio.run(
        store.receive(
            operation_id=OPERATION_ID,
            owner_id=OWNER_ID,
            chunks=_chunks(content),
        )
    )
    with pytest.raises(WorldPackageContractError) as rejected:
        ZipWorldPackageImportValidator(store).validate(operation_id=OPERATION_ID)
    assert (
        rejected.value.reason_code
        is WorldPackageReasonCode.REFERENCE_INVALID
    )


def test_reserved_no_role_payload_is_accepted_only_with_canonical_content(
    tmp_path: Path,
) -> None:
    payloads = _payloads(_archive())
    world = json.loads(payloads["content/world.json"])
    world["roles"].append(
        {
            "allowed_activity_scope": [],
            "autonomous_allowed": True,
            "description": "별도의 World 역할을 지정하지 않은 캐릭터",
            "name": "역할 없음",
            "ref": "roles/no-specific-role",
            "responsibilities": [],
        }
    )
    world_characters = json.loads(payloads["content/world-characters.json"])
    world_characters["characters"][0]["role_ref"] = "roles/no-specific-role"
    _replace_indexed_payload(
        payloads,
        path="content/world.json",
        content=canonical_json_bytes(world),
    )
    valid_content = _replace_indexed_payload(
        payloads,
        path="content/world-characters.json",
        content=canonical_json_bytes(world_characters),
    )

    _store, _use_case, prepared = _stage(tmp_path / "valid", valid_content)
    assert prepared.preview.state is WorldPackageImportState.PREVIEW_READY

    tampered_payloads = _payloads(valid_content)
    tampered_world = json.loads(tampered_payloads["content/world.json"])
    reserved = next(
        role
        for role in tampered_world["roles"]
        if role["ref"] == "roles/no-specific-role"
    )
    reserved["name"] = "위조된 역할"
    tampered_content = _replace_indexed_payload(
        tampered_payloads,
        path="content/world.json",
        content=canonical_json_bytes(tampered_world),
    )

    with pytest.raises(WorldPackageContractError) as rejected:
        _stage(tmp_path / "tampered", tampered_content)
    assert rejected.value.reason_code is WorldPackageReasonCode.REFERENCE_INVALID


def test_webp_preview_is_decoded_bounded_and_metadata_stripped(
    tmp_path: Path,
) -> None:
    store, _use_case, prepared = _stage(
        tmp_path,
        _archive(with_metadata_image=True),
    )
    normalized = prepared.preview.normalized_assets
    assert len(normalized) == 1
    assert normalized[0].width == 12
    assert normalized[0].height == 8
    normalized_path = (
        store.root
        / OPERATION_ID
        / "extracted"
        / "normalized"
        / Path(normalized[0].normalized_ref).name
    )
    with Image.open(normalized_path) as image:
        assert "exif" not in image.info
        assert "xmp" not in image.info
        assert "icc_profile" not in image.info


def test_sql_preview_probe_labels_trust_and_blocks_duplicate_or_tampered_version(
    tmp_path: Path,
) -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    package = _validated_package(tmp_path)
    package_id = str(package.manifest.package_id)
    fallback_world_slug = f"world-{package.manifest.content_digest[:12]}"
    source_world = models.World(
        id="source-world",
        slug=fallback_world_slug,
        owner_user_id=OWNER_ID,
        name="Source World",
        contract_version="world-contract-v1",
        contract_hash="1" * 64,
        create_idempotency_key="source-world-create",
    )
    imported_world = models.World(
        id="imported-world",
        slug="already-imported-world",
        owner_user_id=OWNER_ID,
        name="Imported World",
        contract_version="world-contract-v1",
        contract_hash="2" * 64,
        create_idempotency_key="imported-world-create",
    )
    owner = models.User(
        id=OWNER_ID,
        display_name="Preview Owner",
        display_name_normalized="preview owner",
    )
    character = models.Character(
        id="existing-character",
        owner_id=OWNER_ID,
        name="Existing Mango",
        handle="mango",
        persona_summary="Existing local character",
    )
    imported = WorldPackageImport(
        import_id="existing-import",
        local_owner_id=OWNER_ID,
        package_id=package_id,
        package_version=package.manifest.package_version,
        content_digest=package.manifest.content_digest,
        imported_world_id=imported_world.id,
        import_mode="new_world",
        trust_state="checksum_verified_unsigned",
        license_expression="CC-BY-4.0",
        idempotency_key="existing-import-request",
    )
    with factory() as db:
        db.add_all(
            [
                owner,
                source_world,
                imported_world,
                character,
                WorldPackageSource(
                    package_id=package_id,
                    source_world_id=source_world.id,
                    next_version=2,
                ),
                imported,
            ]
        )
        db.flush()
        db.add(
            WorldPackageExport(
                export_id="existing-export",
                package_id=package_id,
                package_version=package.manifest.package_version,
                source_world_id=source_world.id,
                seed_digest="3" * 64,
                manifest_digest=package.manifest_digest,
                license_expression="CC-BY-4.0",
                delivery_mode="browser_download",
                delivered_at=datetime(2026, 8, 26, tzinfo=UTC),
            )
        )
        db.commit()

        assessment = SqlAlchemyWorldPackagePreviewProbe(db).assess(
            local_owner_id=OWNER_ID,
            package=package,
        )
        assert assessment.trust_state is WorldPackageTrustState.LOCALLY_EXPORTED
        assert (
            assessment.collision_plan.duplicate_state
            is WorldPackageDuplicateState.ALREADY_IMPORTED
        )
        assert assessment.collision_plan.commit_allowed_by_default is False
        assert (
            assessment.collision_plan.planned_world_slug
            == f"{fallback_world_slug}-2"
        )
        assert assessment.collision_plan.characters[0].planned_handle == "mango_2"

        imported.content_digest = "0" * 64
        db.commit()
        with pytest.raises(WorldPackageContractError) as tampered:
            SqlAlchemyWorldPackagePreviewProbe(db).assess(
                local_owner_id=OWNER_ID,
                package=package,
            )
        assert (
            tampered.value.reason_code
            is WorldPackageReasonCode.TAMPERED_VERSION
        )
    engine.dispose()


def test_stage_api_is_owner_only_and_changes_no_world_or_import_rows(
    tmp_path: Path,
) -> None:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    owner = models.User(
        id=OWNER_ID,
        display_name="Preview Owner",
        display_name_normalized="preview owner",
    )
    with factory() as db:
        db.add(owner)
        db.commit()

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
    content = _archive()
    response = client.post(
        "/api/v1/world-package-imports/stage",
        headers=FRONTEND_HEADERS,
        files={
            "package": (
                "private-original-filename.angmoo-world",
                content,
                "application/vnd.angmoo.world+zip",
            )
        },
    )
    assert response.status_code == 201, response.text
    prepared = response.json()
    preview = prepared["preview"]
    assert preview["state"] == "PREVIEW_READY"
    assert preview["world_name"]
    assert "private-original-filename" not in json.dumps(prepared)

    with factory() as db:
        assert int(db.scalar(select(func.count()).select_from(models.World)) or 0) == 0
        assert int(db.scalar(select(func.count()).select_from(models.Character)) or 0) == 0
        assert int(db.scalar(select(func.count()).select_from(WorldPackageImport)) or 0) == 0
    assert not any(media_root.iterdir())

    operation_id = preview["operation_id"]
    token = prepared["preview_token"]
    read = client.get(
        f"/api/v1/world-package-imports/{operation_id}/preview",
        headers={**FRONTEND_HEADERS, "X-World-Package-Preview-Token": token},
    )
    assert read.status_code == 200
    forbidden = client.get(
        f"/api/v1/world-package-imports/{operation_id}/preview",
        headers={**FRONTEND_HEADERS, "X-World-Package-Preview-Token": "x" * 43},
    )
    assert forbidden.status_code == 403
    discarded = client.delete(
        f"/api/v1/world-package-imports/{operation_id}",
        headers={**FRONTEND_HEADERS, "X-World-Package-Preview-Token": token},
    )
    assert discarded.status_code == 204
    expired = client.get(
        f"/api/v1/world-package-imports/{operation_id}/preview",
        headers={**FRONTEND_HEADERS, "X-World-Package-Preview-Token": token},
    )
    assert expired.status_code == 410
    engine.dispose()
