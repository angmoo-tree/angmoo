"""Verify same-run fixture and shared payload before isolated installer use."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import zipfile

FIELDS = {"angmoo-desktop.exe": "app_host_sha256", "angmoo-sidecar.exe": "app_sidecar_sha256", "uninstall.exe": "app_uninstaller_sha256"}


def verified_payload(archive: Path, payload: Path) -> dict[str, bytes]:
    bundle = json.loads((archive.parent / "bundle.json").read_text(encoding="utf-8"))
    if bundle.get("schema") != "installer-fixture-bundle.v1" or any(bundle.get(key) != os.environ[env] for key, env in (("source_sha", "SOURCE_SHA"), ("run_id", "GITHUB_RUN_ID"), ("run_attempt", "GITHUB_RUN_ATTEMPT"))):
        raise ValueError("fixture_bundle_identity_mismatch")
    expected = bundle["archives"].get(archive.parent.name + "/" + archive.name)
    if hashlib.sha256(archive.read_bytes()).hexdigest() != expected or hashlib.sha256(payload.read_bytes()).hexdigest() != bundle["payload_sha256"]:
        raise ValueError("fixture_bundle_hash_mismatch")
    with zipfile.ZipFile(archive) as fixture:
        for info in fixture.infolist():
            path = Path(info.filename)
            if path.is_absolute() or ".." in path.parts or "\\" in info.filename or ":" in info.filename or info.filename.startswith("/") or (info.external_attr >> 16) & 0o170000 == 0o120000:
                raise ValueError("fixture_archive_path_invalid")
        contract = json.loads(fixture.read("fixture-manifest.json"))
    if contract.get("synthetic_fixture") is not True or contract.get("contains_real_credentials") is not False:
        raise ValueError("fixture_not_synthetic")
    with zipfile.ZipFile(payload) as packed:
        if set(packed.namelist()) != set(FIELDS) or len(packed.namelist()) != len(FIELDS):
            raise ValueError("fixture_payload_members_invalid")
        result = {name: packed.read(name) for name in FIELDS}
    if any(hashlib.sha256(data).hexdigest() != contract[FIELDS[name]] for name, data in result.items()):
        raise ValueError("fixture_payload_identity_mismatch")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--payload", type=Path, required=True)
    parser.add_argument("--fixture-root", type=Path)
    args = parser.parse_args()
    payload = verified_payload(args.archive, args.payload)
    if args.fixture_root:
        # Called only after the existing hosted-runner/sentinel/exact-root
        # guards, and after validation of the archive before any removal.
        app = args.fixture_root / "app"
        if app.is_symlink() or (hasattr(app, "is_junction") and app.is_junction()):
            raise ValueError("fixture_payload_destination_redirected")
        app.mkdir(parents=True, exist_ok=True)
        for name, data in payload.items():
            path = app / name
            if path.exists() or path.is_symlink():
                raise ValueError("fixture_payload_destination_exists")
            path.write_bytes(data)
    print("installer_fixture_payload_verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
