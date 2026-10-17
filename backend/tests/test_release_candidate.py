"""Release identity attacks and publish resumption, using no remote writes."""

import copy
import hashlib
import io
import json
from pathlib import Path
import sys
import tarfile

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from launcher.termux.payload import digest_file, inspect_oci, proot_archive, validate_manifest, verify_archive
from scripts.release.github import GitHub
from scripts.release.publish import synchronize
from scripts.release.workflow_policy import validate as validate_workflow
from scripts.release.windows_receipt import aggregate
from scripts.ci.windows_installer_upgrade_coverage import readable_predecessors, partition_versions, SCHEMA

SOURCE = "a" * 40


def test_termux_release_asset_is_identical_after_checkout_timestamp_changes(tmp_path):
    import os
    import zipfile
    from scripts.release.prepare import package_termux_tools
    root = tmp_path / "source"
    tools = root / "launcher/termux"
    tools.mkdir(parents=True)
    names = ("angmoo.py", "payload.py", "processes.py", "requirements.txt", "setup.sh")
    for name in names:
        (tools / name).write_bytes(("synthetic " + name).encode())
    (root / "LICENSE").write_text("synthetic license")
    first, second = tmp_path / "first.zip", tmp_path / "second.zip"
    package_termux_tools(first, root)
    for path in root.rglob("*"):
        if path.is_file():
            os.utime(path, (1_600_000_000, 1_600_000_000))
    package_termux_tools(second, root)
    assert first.read_bytes() == second.read_bytes()
    with zipfile.ZipFile(first) as archive:
        assert set(archive.namelist()) == {*names, "LICENSE"}
        assert archive.read("setup.sh") == b"synthetic setup.sh"


def oci(tmp_path, *, service="backend", architecture="arm64", attestation_target=None, nested=False):
    blobs = {}
    def blob(value):
        raw = value if isinstance(value, bytes) else json.dumps(value, separators=(",", ":")).encode()
        sha = hashlib.sha256(raw).hexdigest()
        blobs["blobs/sha256/" + sha] = raw
        return {"digest": "sha256:" + sha, "size": len(raw)}
    layer = blob(b"synthetic-layer")
    config = blob({"os": "linux", "architecture": architecture, "rootfs": {"diff_ids": ["sha256:" + "b" * 64]}, "config": {"User": "angmoo" if service == "backend" else "node", "WorkingDir": "/app", "Cmd": ["contributor-api"] if service == "backend" else ["node", "app/server.js"], "Entrypoint": ["/usr/local/bin/angmoo-backend-entrypoint"] if service == "backend" else [], "Labels": {"org.opencontainers.image.revision": SOURCE, "org.opencontainers.image.version": "0.1.0", "org.opencontainers.image.source": "https://github.com/angmoo-tree/angmoo"}}})
    image = blob({"config": config, "layers": [layer]})
    image["platform"] = {"os": "linux", "architecture": architecture}
    target = attestation_target or image["digest"]
    attestation = blob({"config": blob({}), "layers": [blob({"predicateType": kind, "subject": [{"digest": {"sha256": target[7:]}}]}) for kind in ("https://spdx.dev/Document", "https://slsa.dev/provenance/v1")]})
    attestation["annotations"] = {"vnd.docker.reference.type": "attestation-manifest", "vnd.docker.reference.digest": target}
    index = {"schemaVersion": 2, "manifests": [image, attestation]}
    blobs["index.json"] = json.dumps({"schemaVersion": 2, "manifests": [blob(index)]} if nested else index).encode()
    blobs["oci-layout"] = b'{"imageLayoutVersion":"1.0.0"}'
    path = tmp_path / f"{service}-{architecture}.oci.tar"
    with tarfile.open(path, "w") as archive:
        for name, raw in blobs.items():
            info = tarfile.TarInfo(name)
            info.size = len(raw)
            archive.addfile(info, io.BytesIO(raw))
    return path


def test_oci_binds_actual_bytes_source_architecture_and_attestations(tmp_path):
    path = oci(tmp_path)
    item = inspect_oci(path, service="backend", platform="linux/arm64", source=SOURCE, version="0.1.0")
    assert verify_archive(path, item)["diff_ids"] == item["diff_ids"]
    for field, wrong in (("platform", "linux/amd64"), ("source_sha", "b" * 40), ("config_digest", "sha256:" + "c" * 64)):
        replaced = {**item, field: wrong}
        with pytest.raises(ValueError):
            verify_archive(path, replaced)
    with path.open("ab") as stream:
        stream.write(b"corrupt")
    with pytest.raises(ValueError, match="archive_hash_mismatch"):
        verify_archive(path, item)


def test_proot_transport_preserves_nested_execution_and_attestation_blobs(tmp_path):
    path = oci(tmp_path, nested=True)
    item = inspect_oci(path, service="backend", platform="linux/arm64", source=SOURCE, version="0.1.0")
    before = path.read_bytes()
    target = tmp_path / "transport.oci.tar"
    proot_archive(path, target, item)
    with tarfile.open(path) as original, tarfile.open(target) as flattened:
        index = json.load(flattened.extractfile("index.json"))
        assert index["manifests"][0]["digest"] == item["manifest_digest"]
        for member in original:
            if member.name.startswith("blobs/"):
                assert original.extractfile(member).read() == flattened.extractfile(member.name).read()
    assert path.read_bytes() == before
    with pytest.raises(ValueError, match="archive_source_overwrite"):
        proot_archive(path, path, item)
    path.write_bytes(before + b"corrupt")
    with pytest.raises(ValueError, match="archive_hash_mismatch"):
        proot_archive(path, tmp_path / "must-not-exist.oci.tar", item)
    assert not (tmp_path / "must-not-exist.oci.tar").exists()


def test_candidate_requires_all_four_platforms_without_duplicate_or_swapped_sources(tmp_path):
    images = [inspect_oci(oci(tmp_path, service=s, architecture=a), service=s, platform="linux/" + a, source=SOURCE, version="0.1.0") for s in ("backend", "frontend") for a in ("amd64", "arm64")]
    manifest = {"schema": "angmoo-release-candidate.v1", "repository": "angmoo-tree/angmoo", "source_sha": SOURCE, "source_tree": "c" * 40, "clean": True, "version": "0.1.0", "tag": "release-v0.1.0", "images": images}
    validate_manifest(manifest)
    for changed in (images[:3], images + [images[0]], [{**i, "source_sha": "d" * 40} if n == 0 else i for n, i in enumerate(images)]):
        with pytest.raises(ValueError):
            validate_manifest({**manifest, "images": changed})


def test_oci_rejects_traversal_before_any_extraction(tmp_path):
    path = oci(tmp_path)
    with tarfile.open(path, "a") as archive:
        info = tarfile.TarInfo("../escape")
        info.size = 1
        archive.addfile(info, io.BytesIO(b"x"))
    with pytest.raises(ValueError, match="oci_path_invalid"):
        inspect_oci(path, service="backend", platform="linux/arm64", source=SOURCE, version="0.1.0")
    assert not (tmp_path.parent / "escape").exists()


def test_oci_rejects_valid_attestation_for_another_execution_image(tmp_path):
    path = oci(tmp_path, attestation_target="sha256:" + "f" * 64)
    with pytest.raises(ValueError, match="oci_attestation_target_mismatch"):
        inspect_oci(path, service="backend", platform="linux/arm64", source=SOURCE, version="0.1.0")


def test_p5_requires_exact_images_windows_and_concrete_user_check():
    from scripts.release.prepare import validate_p5
    manifest = {"source_sha": SOURCE, "images": [{"service": s, "platform": p, "manifest_digest": "sha256:" + str(i) * 64} for i, (s, p) in enumerate(( (s, p) for s in ("backend", "frontend") for p in ("linux/amd64", "linux/arm64")))]}
    windows = {"exe": {"sha256": "sha256:" + "a" * 64}, "run_id": "1", "attempt": "2"}
    report = {"schema": "angmoo-p5.v1", "source_sha": SOURCE, "windows": {"sha256": windows["exe"]["sha256"], "run_id": "1", "attempt": "2"}, "images": {i["service"] + "/" + i["platform"]: i["manifest_digest"] for i in manifest["images"]}, "checks": [{"workflow": f, "run_id": str(n), "attempt": "1"} for n, f in enumerate(("ci.yml", "local-smoke.yml", "security.yml"))], "windows_user_check": {"result": "PASS", "reviewer": "jingujeon", "exe_sha256": windows["exe"]["sha256"], "evidence": "Verified exact synthetic EXE in an isolated test", "checked_at": "2026-10-18T12:00:00Z"}, "android_support": "experimental-not-certified"}
    calls = []
    client = GitHub()
    client.run = lambda *args, **kwargs: calls.append((args, kwargs))
    validate_p5(client, report, manifest, windows)
    assert len(calls) == 3 and all(c[1]["source"] == SOURCE for c in calls)
    for key, value in (("images", {}), ("windows", {}), ("source_sha", "b" * 40), ("checks", []), ("windows_user_check", {"result": "PASS"}), ("android_support", "certified")):
        with pytest.raises(ValueError):
            validate_p5(client, {**report, key: value}, manifest, windows)


class Release:
    def __init__(self):
        self.value = None
        self.data = {}
        self.calls = []
        self.interrupt_after_upload = False

    def find(self, tag):
        self.calls.append("read")
        return copy.deepcopy(self.value)

    def create(self, expected):
        self.calls.append("create")
        self.value = {"id": 1, "tag_name": expected["tag"], "name": expected["name"], "body": expected["notes"], "draft": True, "prerelease": False, "assets": [], "html_url": "https://github.com/angmoo-tree/angmoo/releases/tag/release-v0.1.0"}
        return copy.deepcopy(self.value)

    def upload(self, tag, path):
        self.calls.append("upload")
        self.data[path.name] = path.read_bytes()
        self.value["assets"].append({"id": len(self.data), "name": path.name, "size": len(self.data[path.name])})
        if self.interrupt_after_upload:
            self.interrupt_after_upload = False
            raise OSError("connection lost after accepted upload")

    def asset_digest(self, asset):
        return "sha256:" + hashlib.sha256(self.data[asset["name"]]).hexdigest()

    def publish(self, release):
        self.calls.append("publish")
        self.value["draft"] = False


def staged(tmp_path):
    (tmp_path / "Angmoo_0.1.0_x64-setup.exe").write_bytes(b"synthetic-exe")
    (tmp_path / "release-manifest.json").write_text("{}")
    return {"source_sha": SOURCE, "tag": "release-v0.1.0", "name": "Angmoo 0.1.0", "notes": "English / 한국어", "publication_ready": True, "assets": [{"name": p.name, "size": p.stat().st_size, "sha256": digest_file(p)} for p in tmp_path.iterdir()]}


def test_verify_has_no_remote_write_or_publish_requirement(tmp_path):
    expected, api = staged(tmp_path), Release()
    expected["publication_ready"] = False
    assert synchronize(expected, tmp_path, "verify", api, lambda: pytest.fail("verify must not authorize writes"))["remote_writes"] == 0
    assert api.calls == []
    with pytest.raises(ValueError, match="release_publication_not_ready"):
        synchronize(expected, tmp_path, "draft", api, lambda: None)
    assert api.calls == []


def test_publish_resumes_partial_upload_without_clobber_and_checks_final_bytes(tmp_path):
    expected, api = staged(tmp_path), Release()
    api.interrupt_after_upload = True
    with pytest.raises(OSError):
        synchronize(expected, tmp_path, "publish", api, lambda: None)
    assert api.value["draft"]
    assert synchronize(expected, tmp_path, "publish", api, lambda: None)["state"] == "PUBLISHED"
    assert api.calls.count("create") == 1 and api.calls.count("upload") == 2 and api.calls.count("publish") == 1
    synchronize(expected, tmp_path, "publish", api, lambda: None)
    assert api.calls.count("upload") == 2 and api.calls.count("publish") == 1
    api.data[next(iter(api.data))] = b"changed"
    with pytest.raises(ValueError, match="release_existing_asset_conflict"):
        synchronize(expected, tmp_path, "publish", api, lambda: None)


def test_source_change_and_staging_extra_file_prevent_all_writes(tmp_path):
    expected, api = staged(tmp_path), Release()
    def changed():
        raise ValueError("tag_changed")
    with pytest.raises(ValueError, match="tag_changed"):
        synchronize(expected, tmp_path, "publish", api, changed)
    assert api.calls == []
    (tmp_path / "private.sqlite").write_text("private")
    with pytest.raises(ValueError, match="release_staging_extra_files"):
        synchronize(expected, tmp_path, "publish", api, lambda: None)


def test_full_windows_receipt_rejects_mixed_attempt_or_installer_bytes():
    versions = readable_predecessors()
    reports = [{"schema": SCHEMA, "status": "completed", "source_sha": SOURCE, "run_id": "10", "run_attempt": "2", "partition": part, "versions": list(partition_versions(versions, part)), "idempotent": True} for part in ("first", "second")]
    receipts = [{"schema": "angmoo-installer-test.v1", "source_sha": SOURCE, "run_id": "10", "attempt": "2", "kind": k, "status": "PASS", "artifact_id": "20", "exe": {"sha256": "sha256:" + "a" * 64}} for k in ("clean-install", "failure-recovery", "upgrade-first", "upgrade-second")]
    assert aggregate(receipts, reports, source=SOURCE, run="10", attempt="2")["coverage"]["covered"] == len(versions)
    for key, value in (("attempt", "1"), ("exe", {"sha256": "sha256:" + "b" * 64}), ("artifact_id", "21")):
        changed = copy.deepcopy(receipts)
        changed[0][key] = value
        with pytest.raises(ValueError):
            aggregate(changed, reports, source=SOURCE, run="10", attempt="2")
    with pytest.raises(ValueError):
        aggregate(receipts[:3], reports, source=SOURCE, run="10", attempt="2")


def test_artifact_expiry_wrong_source_and_attempt_are_rejected():
    run = {"id": 10, "head_sha": SOURCE, "run_started_at": "2026-10-18T10:00:00Z", "updated_at": "2026-10-18T11:00:00Z"}
    value = {"id": 20, "name": "candidate-2", "expired": False, "workflow_run": {"id": 10, "head_sha": SOURCE}, "created_at": "2026-10-18T10:30:00Z", "digest": "sha256:" + "b" * 64}
    client = GitHub()
    client.read = lambda _: value
    assert client.artifact("20", run, name="candidate-2")["id"] == 20
    for key, changed in (("expired", True), ("name", "candidate-1"), ("created_at", "2026-10-18T09:00:00Z"), ("workflow_run", {"id": 99, "head_sha": SOURCE})):
        original = value[key]
        value[key] = changed
        with pytest.raises(ValueError):
            client.artifact("20", run, name="candidate-2")
        value[key] = original


def test_candidate_workflow_cannot_gain_write_permissions_or_drop_arm64():
    import yaml
    document = yaml.safe_load((ROOT / ".github/workflows/container-candidate.yml").read_text())
    assert validate_workflow(document, "container-candidate.yml") == []
    document["jobs"]["build-validate"]["permissions"] = {"packages": "write"}
    assert validate_workflow(document, "container-candidate.yml")


def test_release_preparation_binds_windows_bytes_and_excludes_artifact_extras(tmp_path, monkeypatch):
    import shutil
    import subprocess
    import scripts.release.prepare as preparation
    from scripts.release.windows_receipt import tested_installer

    directories = {kind: tmp_path / kind for kind in ("candidate", "windows", "validation", "signed")}
    for directory in directories.values():
        directory.mkdir()
    candidate = directories["candidate"]
    images = []
    for service in ("backend", "frontend"):
        for architecture in ("amd64", "arm64"):
            item = inspect_oci(oci(candidate, service=service, architecture=architecture),
                service=service, platform="linux/" + architecture, source=SOURCE, version="0.1.0")
            item["validation"] = dict(runtime="PASS", native="PASS", security="PASS")
            for field in ("sbom", "security_report"):
                report = candidate / f"{service}-{architecture}-{field}.json"
                report.write_text('{"status":"PASS"}')
                item[field] = {"name": report.name, "sha256": digest_file(report)}
            images.append(item)
    (candidate / "candidate.json").write_text(json.dumps({"schema": "angmoo-release-candidate.v1",
        "repository": "angmoo-tree/angmoo", "source_sha": SOURCE, "source_tree": "b" * 40,
        "clean": True, "version": "0.1.0", "tag": "release-v0.1.0", "images": images}))
    windows = directories["windows"]
    installer = windows / "Angmoo_0.1.0_x64-setup.exe"
    installer.write_bytes(b"synthetic installer, never executable")
    (windows / "SHA256SUMS").write_text(f"{digest_file(installer)[7:]}  {installer.name}\n")
    exe = tested_installer(windows)
    for name in ("LICENSE", "THIRD_PARTY_NOTICES.md", "private.sqlite"):
        (windows / name).write_text("synthetic artifact extra")
    provenance = {"predicate": {"buildDefinition": {"externalParameters": {"version": "0.1.0", "commit": SOURCE},
        "internalParameters": {"sourceWorktreeDirty": False}}},
        "subject": [{"name": exe["name"], "digest": {"sha256": exe["sha256"][7:]}}]}
    (windows / "angmoo-installer.provenance.json").write_text(json.dumps(provenance))
    (windows / "angmoo-installer.spdx.json").write_text(json.dumps({"files": [
        {"fileName": exe["name"], "checksums": [{"algorithm": "SHA256", "checksumValue": exe["sha256"][7:]}]}]}))
    (directories["validation"] / "windows-release-validation.json").write_text(json.dumps({
        "schema": "angmoo-windows-release-validation.v1", "status": "PASS", "profile": "full",
        "exe": exe, "source_sha": SOURCE, "run_id": "10", "attempt": "2", "artifact_id": "20"}))
    (directories["signed"] / "bundle.jsonl").write_text("synthetic signed bundle fixture")

    class Evidence:
        def main_source(self, source):
            assert source == SOURCE
        def run(self, run_id, attempt, **kwargs):
            assert kwargs["source"] == SOURCE
            return {"id": run_id}
        def artifact(self, artifact_id, run, **kwargs):
            return {"kind": "windows" if artifact_id == "20" else "candidate"}
        def named_artifact(self, run, name):
            return {"kind": "validation" if name.startswith("windows-release-validation-") else "signed"}
        def download(self, artifact, destination):
            shutil.copytree(directories[artifact["kind"]], destination)
            return destination
        def read(self, path):
            assert path == "commits/release-v0.1.0"
            return {"sha": SOURCE}

    attestation_calls = []
    def attest(command, **kwargs):
        assert command[:3] == ["gh", "attestation", "verify"] and kwargs == {"check": True}
        attestation_calls.append(command)
        return subprocess.CompletedProcess(command, 0)
    monkeypatch.setattr(preparation.subprocess, "run", attest)
    monkeypatch.setattr(preparation, "registry_document", lambda _: None)
    arguments = dict(source=SOURCE, tag="release-v0.1.0", windows_run="10", windows_attempt="2",
        windows_artifact="20", candidate_run="11", candidate_attempt="1", candidate_artifact="21",
        review_ref=None, github=Evidence())
    output = tmp_path / "prepared"
    expected = preparation.prepare(**arguments, output=output)
    assert len(attestation_calls) == 1 and "--source-digest" in attestation_calls[0]
    assert expected["publication_ready"] is False  # P5 and published images are absent.
    assert "private.sqlite" not in {item["name"] for item in expected["assets"]}
    api = Release()
    assert synchronize(expected, output / "assets", "verify", api, lambda: pytest.fail("no write"))["remote_writes"] == 0
    assert api.calls == []
    provenance["predicate"]["buildDefinition"]["externalParameters"]["commit"] = "c" * 40
    (windows / "angmoo-installer.provenance.json").write_text(json.dumps(provenance))
    with pytest.raises(ValueError, match="windows_provenance_mismatch"):
        preparation.prepare(**arguments, output=tmp_path / "rejected")
