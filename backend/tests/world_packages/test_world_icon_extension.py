from io import BytesIO
import json
from types import SimpleNamespace
from zipfile import ZipFile

from PIL import Image

from world_packages.test_export import _database_fixture, _FakeRegistry
from app.domains.worlds.models import World
from app.runtime.world_packages.export_source import SqlAlchemyWorldPackageSourceSnapshot
from app.domains.world_packages.storage.export_assets import ManagedMediaPackageAssets
from app.domains.world_packages.service.export import ExportWorldPackage
from app.domains.world_packages.archive.export import DeterministicWorldPackageZipArchive
from app.domains.world_packages.archive.validation import ZipWorldPackageImportValidator
from app.domains.world_packages.archive.exclusions import scan_world_package_bytes
from app.domains.world_packages.schemas.manifest import WorldPackageLicense
from app.domains.world_packages.contracts.world_icon import WORLD_ICON_EXTENSION, world_icon_reference


def test_world_icon_is_required_portable_asset_and_roundtrips_validation(tmp_path):
    engine, factory, owner = _database_fixture(tmp_path)
    media = tmp_path / "media"
    icon = media / "worlds" / "private-source-world-id" / "icon.webp"
    icon.parent.mkdir(parents=True)
    Image.new("RGB", (48, 48), "green").save(icon, "WEBP", lossless=True)
    with factory() as db:
        world = db.get(World, "private-source-world-id")
        world.icon_media_id = "/media/worlds/private-source-world-id/icon.webp"
        db.commit()
        exporter = ExportWorldPackage(source=SqlAlchemyWorldPackageSourceSnapshot(db),
            assets=ManagedMediaPackageAssets(media_root=media), registry=_FakeRegistry(),
            archive=DeterministicWorldPackageZipArchive())
        _, result = exporter.build(source_world_id=world.id, local_owner_id=owner.id,
            license=WorldPackageLicense(expression="CC0-1.0", attribution="test", source_url=None), license_text=None)
    with ZipFile(BytesIO(result.content)) as archive:
        manifest = json.loads(archive.read("manifest.json"))
        definition = json.loads(archive.read("content/world.json"))
        assert WORLD_ICON_EXTENSION in manifest["required_extensions"]
        reference = definition["extensions"][WORLD_ICON_EXTENSION]["asset_ref"]
        assert reference in archive.namelist()
        assert not any("card-source" in name for name in archive.namelist())
    assert scan_world_package_bytes(result.content).entry_count > 0
    upload = tmp_path / "icon.angmoo-world"
    upload.write_bytes(result.content)
    extracted = tmp_path / "extracted"
    extracted.mkdir()
    validator = ZipWorldPackageImportValidator(SimpleNamespace(upload_path=lambda _: upload, extracted_path=lambda _: extracted))
    imported = validator.validate(operation_id="test-icon")
    assert world_icon_reference(imported.world) == reference
    engine.dispose()
