"""Retirement removes native gates, never shared provenance or update checks."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from copy import deepcopy
import json
import pytest

from scripts.release import assets
from scripts.release.platforms import native_windows
from scripts.release.prepare import validate_p5
from scripts.release.postgresql_acceptance import validate
from launcher.termux.payload import digest_file
from test_postgresql_release_acceptance import acceptance


def update():
    value = acceptance()
    value["source_version"] = "0.1.4"
    del value["platforms"]["windows-x64"]
    for row in value["platforms"].values():
        row["update"] = row.pop("migration")
    return value


def test_versioned_acceptance_preserves_legacy_and_requires_supported_updates():
    assert native_windows("0.1.4") and not native_windows("0.1.5")
    validate(acceptance(), "a" * 40)
    validate(update(), "a" * 40, version="0.1.5")
    with pytest.raises(ValueError):
        validate(acceptance(), "a" * 40, version="0.1.5")
    for platform in update()["platforms"]:
        value = update()
        value["platforms"][platform]["update"] = False
        with pytest.raises(ValueError):
            validate(value, "a" * 40, version="0.1.5")


def test_current_p5_still_binds_shared_checks_images_and_update_evidence():
    manifest = {"source_sha": "a" * 40, "version": "0.1.5", "images": [
        {"service": s, "platform": p, "manifest_digest": "sha256:" + "b" * 64}
        for s in ("backend", "frontend", "postgres") for p in ("linux/amd64", "linux/arm64")]}
    report = {"schema": "angmoo-p5.v1", "source_sha": manifest["source_sha"],
        "images": {r["service"] + "/" + r["platform"]: r["manifest_digest"] for r in manifest["images"]},
        "checks": [{"workflow": w, "run_id": "1", "attempt": "1"} for w in ("ci.yml", "security.yml", "local-smoke.yml")],
        "android_support": "experimental-not-certified", "postgresql_update": update()}
    class GitHub:
        def run(self, *args, **kwargs):
            assert kwargs["source"] == "a" * 40
    validate_p5(GitHub(), report, manifest, None)
    for field in ("images", "checks", "postgresql_update"):
        broken = deepcopy(report)
        broken.pop(field)
        with pytest.raises(ValueError):
            validate_p5(GitHub(), broken, manifest, None)
    report["windows_user_check"] = {"result": "PASS"}
    with pytest.raises(ValueError, match="retired_windows"):
        validate_p5(GitHub(), report, manifest, None)


def test_common_assets_reject_wrong_source_changed_bytes_and_unexpected_executable(tmp_path):
    for name in assets.FILES:
        (tmp_path / name).write_text("synthetic source")
    receipt = {"schema": "angmoo-release-assets.v1", "source_sha": "a" * 40, "version": "0.1.5",
               "files": {name: digest_file(tmp_path / name) for name in assets.FILES}}
    (tmp_path / "release-assets.json").write_text(json.dumps(receipt))
    assets.validate(tmp_path, "a" * 40, "0.1.5")
    with pytest.raises(ValueError, match="identity"):
        assets.validate(tmp_path, "b" * 40, "0.1.5")
    (tmp_path / "LICENSE").write_text("changed")
    with pytest.raises(ValueError, match="hash"):
        assets.validate(tmp_path, "a" * 40, "0.1.5")
    (tmp_path / "unexpected.exe").write_text("unreviewed")
    with pytest.raises(ValueError, match="file_set"):
        assets.validate(tmp_path, "a" * 40, "0.1.5")
