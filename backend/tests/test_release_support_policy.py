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


def test_modern_preparation_consumes_independent_assets_without_native_metadata(tmp_path, monkeypatch):
    import shutil
    import scripts.release.prepare as preparation
    source, version = "a" * 40, "0.1.5"
    product = tmp_path / "product"
    metadata = {
        "backend/pyproject.toml": '[project]\nversion="0.1.5"\n',
        "backend/uv.lock": '[[package]]\nname="backend"\nversion="0.1.5"\n',
        "backend/app/runtime/product_identity.py": 'PRODUCT_VERSION="0.1.5"\n',
        "frontend/package.json": '{"version":"0.1.5"}',
        "LICENSE": "synthetic license",
    }
    for path, body in metadata.items():
        target = product / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body, encoding="utf-8")
    shutil.copytree(Path(__file__).resolve().parents[2] / "launcher/termux", product / "launcher/termux",
                    ignore=shutil.ignore_patterns("__pycache__"))
    (product / "docs/public").mkdir(parents=True)
    for stem in ("termux", "postgresql-runtime", "postgresql-backup"):
        for suffix in ("", ".ko"):
            (product / "docs/public" / (stem + suffix + ".md")).write_text("Synthetic guide")
    candidate, common = tmp_path / "candidate", tmp_path / "common"
    candidate.mkdir(); common.mkdir()
    for name in assets.FILES:
        (common / name).write_text("synthetic source asset")
    receipt = {"schema": "angmoo-release-assets.v1", "source_sha": source, "version": version,
               "files": {name: digest_file(common / name) for name in assets.FILES}}
    (common / "release-assets.json").write_text(json.dumps(receipt))
    digest = "sha256:" + "b" * 64
    report = candidate / "report.json"
    report.write_text('{"status":"PASS"}')
    images = [{"service": s, "platform": "linux/" + p, "source_sha": source, "version": version,
               "repository": "ghcr.io/angmoo-tree/angmoo-" + s,
               "manifest_digest": digest, "config_digest": digest, "archive_digest": digest,
               "layers": [digest], "diff_ids": [digest], "attestation_manifests": [digest],
               "archive": f"{s}-{p}.oci.tar", "archive_size": 100,
               "validation": {"runtime": "PASS", "native": "PASS", "security": "PASS"},
               **{k: {"name": report.name, "sha256": digest_file(report)} for k in ("sbom", "security_report")}}
              for s in ("backend", "frontend", "postgres") for p in ("amd64", "arm64")]
    (candidate / "candidate.json").write_text(json.dumps({"schema": "angmoo-release-candidate.v1",
        "repository": "angmoo-tree/angmoo", "source_sha": source, "source_tree": "c" * 40,
        "clean": True, "version": version, "tag": "release-v0.1.5", "images": images}))
    calls = []
    class Evidence:
        def main_source(self, value): assert value == source
        def run(self, run, attempt, **kw):
            calls.append(kw["workflow"])
            assert kw["source"] == source and kw["workflow"] in {"container-candidate.yml", "release-assets.yml"}
            return {"id": run}
        def artifact(self, artifact, run, **kw):
            assert kw["name"] == ("release-candidate-" if artifact == "1" else "release-assets-") + source + "-1"
            return artifact
        def download(self, artifact, destination):
            shutil.copytree(candidate if artifact == "1" else common, destination)
            return destination
        def read(self, path): return {"sha": source}
    monkeypatch.setattr(preparation, "registry_document", lambda _: None)
    args = dict(source=source, tag="release-v0.1.5", windows_run="", windows_attempt="", windows_artifact="",
                candidate_run="1", candidate_attempt="1", candidate_artifact="1", assets_run="2",
                assets_attempt="1", assets_artifact="2", review_ref=None, product_root=product, github=Evidence())
    result = preparation.prepare(**args, output=tmp_path / "output")
    assert calls == ["container-candidate.yml", "release-assets.yml"]
    assert not result["publication_ready"]  # No P5 or published image evidence supplied.
    names = {row["name"] for row in result["assets"]}
    assert "angmoo-postgresql-sources.zip" in names and "install-termux.py" in names
    assert not any(name.endswith(".exe") or name.startswith("windows") for name in names)
    receipt["source_sha"] = "d" * 40
    (common / "release-assets.json").write_text(json.dumps(receipt))
    with pytest.raises(ValueError, match="common_assets_identity_mismatch"):
        preparation.prepare(**args, output=tmp_path / "rejected")


def test_docker_host_tools_bind_historical_product_and_separate_producer(tmp_path):
    from scripts.release.docker_tools import download
    source, tooling = "a" * 40, "b" * 40
    for name in ("angmoo-migrate.exe", "angmoo-migrate.py"):
        (tmp_path / name).write_bytes(b"synthetic tool; never executed")
    receipt = {"schema": "angmoo-migration-tools.v1", "source_sha": source,
               "source_version": "0.1.3", "target_version": "0.1.4",
               "files": {n: digest_file(tmp_path / n)[7:] for n in ("angmoo-migrate.exe", "angmoo-migrate.py")}}
    path = tmp_path / "angmoo-migration-tools.json"
    path.write_text(json.dumps(receipt))
    ancestors = []
    class Evidence:
        def read(self, path): return {"head_sha": tooling}
        def main_source(self, value): ancestors.append(value)
        def run(self, run, attempt, **kw):
            assert kw == {"workflow": "docker-migration-tools.yml", "source": tooling}
            return {"id": run}
        def artifact(self, artifact, run, **kw):
            assert kw["name"] == f"docker-migration-tools-{source}-2"
            return artifact
        def download(self, artifact, directory): return tmp_path
    args = dict(source=source, run="1", attempt="2", artifact="3", directory=tmp_path)
    assert set(download(Evidence(), **args)) == {"angmoo-migrate.exe", "angmoo-migrate.py"}
    assert ancestors == [tooling, source]
    receipt["source_sha"] = tooling
    path.write_text(json.dumps(receipt))
    with pytest.raises(ValueError, match="identity"):
        download(Evidence(), **args)
    receipt["source_sha"] = source
    path.write_text(json.dumps(receipt))
    (tmp_path / "angmoo-migrate.py").write_bytes(b"altered")
    with pytest.raises(ValueError, match="hash"):
        download(Evidence(), **args)
