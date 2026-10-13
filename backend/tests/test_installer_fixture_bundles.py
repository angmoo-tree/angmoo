"""Shared predecessor payloads preserve independent fixtures and fail closed."""
import hashlib
import json
from pathlib import Path
import sys
import zipfile

import pytest

sys.path.insert(0, str(Path(__file__).parents[2] / "scripts/ci"))
from build_installer_fixtures import pack_fixture, PAYLOAD_FILES
from hydrate_installer_fixture import verified_payload, FIELDS


@pytest.fixture
def bundle(tmp_path, monkeypatch):
    payload = {name: (name + " synthetic predecessor").encode() for name in PAYLOAD_FILES}
    fixture = tmp_path / "working"
    (fixture / "app").mkdir(parents=True)
    contract = {"synthetic_fixture": True, "contains_real_credentials": False}
    for name, data in payload.items():
        (fixture / "app" / name).write_bytes(data)
        contract[FIELDS[name]] = hashlib.sha256(data).hexdigest()
    (fixture / "fixture-manifest.json").write_text(json.dumps(contract))
    (fixture / "database.sqlite").write_bytes(b"synthetic, not a real database")
    archive = tmp_path / "first/supported-v1.zip"
    pack_fixture(fixture, archive, payload)
    shared = tmp_path / "predecessor-payload.zip"
    with zipfile.ZipFile(shared, "w") as packed:
        for name, data in payload.items(): packed.writestr(name, data)
    identity = {"schema": "installer-fixture-bundle.v1", "source_sha": "a" * 40, "run_id": "123", "run_attempt": "1",
                "archives": {"first/supported-v1.zip": hashlib.sha256(archive.read_bytes()).hexdigest()},
                "payload_sha256": hashlib.sha256(shared.read_bytes()).hexdigest()}
    (archive.parent / "bundle.json").write_text(json.dumps(identity))
    for key, value in (("SOURCE_SHA", "a" * 40), ("GITHUB_RUN_ID", "123"), ("GITHUB_RUN_ATTEMPT", "1")):
        monkeypatch.setenv(key, value)
    return archive, shared, payload


def test_archive_omits_only_duplicate_pe_bytes_and_hydrates_exact_identity(bundle):
    archive, shared, payload = bundle
    with zipfile.ZipFile(archive) as packed:
        assert set(packed.namelist()) == {"database.sqlite", "fixture-manifest.json"}
    assert verified_payload(archive, shared) == payload


@pytest.mark.parametrize("fault", ["payload", "fixture", "attempt", "source", "payload_contract"])
def test_mixed_or_modified_artifact_cannot_restore_a_fixture(bundle, monkeypatch, fault):
    archive, shared, _ = bundle
    if fault == "payload": shared.write_bytes(b"modified")
    elif fault == "fixture": archive.write_bytes(b"modified")
    elif fault == "attempt": monkeypatch.setenv("GITHUB_RUN_ATTEMPT", "2")
    elif fault == "source": monkeypatch.setenv("SOURCE_SHA", "b" * 40)
    else:
        with zipfile.ZipFile(shared, "w") as packed:
            for name in PAYLOAD_FILES: packed.writestr(name, b"wrong predecessor")
        path = archive.parent / "bundle.json"
        identity = json.loads(path.read_text())
        identity["payload_sha256"] = hashlib.sha256(shared.read_bytes()).hexdigest()
        path.write_text(json.dumps(identity))
    with pytest.raises(ValueError, match="mismatch"):
        verified_payload(archive, shared)


def test_payload_reuse_rejects_a_different_version_binary(tmp_path):
    (tmp_path / "app").mkdir()
    for name in PAYLOAD_FILES: (tmp_path / "app" / name).write_bytes(b"changed")
    with pytest.raises(ValueError, match="payload_differs"):
        pack_fixture(tmp_path, tmp_path / "unused.zip", {name: b"original" for name in PAYLOAD_FILES})
