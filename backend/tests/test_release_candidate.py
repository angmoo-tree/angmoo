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
