"""Package independent schema fixtures while transmitting identical PE bytes once."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import zipfile

from windows_installer_upgrade_coverage import readable_predecessors, partition_versions

PAYLOAD_FILES = ("angmoo-desktop.exe", "angmoo-sidecar.exe", "uninstall.exe")


def pack_fixture(root: Path, target: Path, payload: dict[str, bytes]) -> None:
    for name, data in payload.items():
        if (root / "app" / name).read_bytes() != data:
            raise ValueError("fixture_shared_payload_differs")
    target.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for path in sorted(root.rglob("*")):
            if path.is_symlink():
                raise ValueError("fixture_reparse_refused")
            if path.is_file() and path.relative_to(root).as_posix() not in {"app/" + name for name in PAYLOAD_FILES}:
                archive.write(path, path.relative_to(root).as_posix())


def main() -> int:
    from build_windows_installer_supported_upgrade_fixture import build_fixture
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--host", type=Path, required=True)
    parser.add_argument("--sidecar", type=Path, required=True)
    parser.add_argument("--profile", choices=("full", "installer-smoke"), required=True)
    args = parser.parse_args()
    versions = readable_predecessors()
    selected = versions if args.profile == "full" else (versions[0], versions[-1])
    root = args.output_root.resolve()
    payload = None
    archives = {}
    for version in selected:
        fixture = root / "working" / f"supported-v{version}"
        build_fixture(fixture, host=args.host.resolve(), sidecar=args.sidecar.resolve(), source_version=version, conflict=False)
        if payload is None:
            payload = {name: (fixture / "app" / name).read_bytes() for name in PAYLOAD_FILES}
            (root / "payload").mkdir(parents=True)
            with zipfile.ZipFile(root / "payload/predecessor-payload.zip", "w", compression=zipfile.ZIP_DEFLATED) as packed:
                for name, data in payload.items():
                    packed.writestr(name, data)
        partition = ("first" if version in partition_versions(versions, "first") else "second") if args.profile == "full" else "representative"
        archive = root / partition / f"supported-v{version}.zip"
        pack_fixture(fixture, archive, payload)
        archives[archive.relative_to(root).as_posix()] = hashlib.sha256(archive.read_bytes()).hexdigest()
    if args.profile == "full":
        fixture = root / "working/conflicting-v2"
        build_fixture(fixture, host=args.host.resolve(), sidecar=args.sidecar.resolve(), source_version=2, conflict=True)
        archive = root / "recovery/conflicting-v2.zip"
        pack_fixture(fixture, archive, payload)
        archives[archive.relative_to(root).as_posix()] = hashlib.sha256(archive.read_bytes()).hexdigest()
    identity = {"schema": "installer-fixture-bundle.v1", "source_sha": os.environ["SOURCE_SHA"],
                "run_id": os.environ["GITHUB_RUN_ID"], "run_attempt": os.environ["GITHUB_RUN_ATTEMPT"],
                "profile": args.profile, "versions": list(selected), "archives": archives,
                "payload_sha256": hashlib.sha256((root / "payload/predecessor-payload.zip").read_bytes()).hexdigest()}
    for folder in {Path(name).parent for name in archives} | {Path("payload")}:
        (root / folder / "bundle.json").write_text(json.dumps(identity, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"versions": list(selected), "fixture_bytes": sum((root / p).stat().st_size for p in archives),
                      "shared_payload_bytes": (root / "payload/predecessor-payload.zip").stat().st_size}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
