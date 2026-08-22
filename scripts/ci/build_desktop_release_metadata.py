#!/usr/bin/env python3
"""Build deterministic ER6 installer checksums, SPDX SBOM, and provenance."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import tomllib
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
FORBIDDEN_ARTIFACT_NAMES = {
    "release-candidate-backup.json",
    "synthetic-fixture.json",
    "app-secret",
}


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bundle-root", required=True, type=Path)
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument("--version", required=True)
    parser.add_argument("--commit", required=True)
    return parser


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _artifact_files(root: Path, *, version: str) -> list[Path]:
    candidates = sorted(
        candidate
        for candidate in root.rglob("*")
        if candidate.is_file() and candidate.suffix.lower() in {".exe", ".msi"}
    )
    versioned = [candidate for candidate in candidates if version in candidate.name]
    files = versioned or candidates
    if not files:
        raise SystemExit("No Windows installer artifacts were found")
    extensions = {candidate.suffix.lower() for candidate in files}
    if extensions != {".exe", ".msi"}:
        raise SystemExit("Both NSIS and MSI installer artifacts are required")
    for candidate in root.rglob("*"):
        if candidate.is_file() and candidate.name in FORBIDDEN_ARTIFACT_NAMES:
            raise SystemExit(f"Private migration artifact refused: {candidate.name}")
    return files


def _component_id(kind: str, name: str, version: str) -> str:
    value = re.sub(r"[^A-Za-z0-9.-]+", "-", f"{kind}-{name}-{version}")
    suffix = hashlib.sha256(f"{kind}:{name}:{version}".encode()).hexdigest()[:12]
    return f"SPDXRef-Package-{value[:80]}-{suffix}"


def _component(kind: str, name: str, version: str) -> dict[str, Any]:
    purl_type = {"python": "pypi", "node": "npm", "rust": "cargo"}[kind]
    return {
        "SPDXID": _component_id(kind, name, version),
        "name": name,
        "versionInfo": version,
        "downloadLocation": "NOASSERTION",
        "filesAnalyzed": False,
        "licenseConcluded": "NOASSERTION",
        "licenseDeclared": "NOASSERTION",
        "copyrightText": "NOASSERTION",
        "externalRefs": [
            {
                "referenceCategory": "PACKAGE-MANAGER",
                "referenceType": "purl",
                "referenceLocator": f"pkg:{purl_type}/{name}@{version}",
            }
        ],
    }


def _locked_components() -> list[dict[str, Any]]:
    coordinates: set[tuple[str, str, str]] = set()
    uv_payload = tomllib.loads(
        (REPOSITORY_ROOT / "backend" / "uv.lock").read_text(encoding="utf-8")
    )
    for package in uv_payload.get("package", []):
        name = package.get("name")
        version = package.get("version")
        if isinstance(name, str) and isinstance(version, str):
            coordinates.add(("python", name, version))

    cargo_payload = tomllib.loads(
        (REPOSITORY_ROOT / "desktop" / "src-tauri" / "Cargo.lock").read_text(
            encoding="utf-8"
        )
    )
    for package in cargo_payload.get("package", []):
        name = package.get("name")
        version = package.get("version")
        if isinstance(name, str) and isinstance(version, str):
            coordinates.add(("rust", name, version))

    desktop_lock = json.loads(
        (REPOSITORY_ROOT / "desktop" / "package-lock.json").read_text(
            encoding="utf-8"
        )
    )
    for package_path, package in desktop_lock.get("packages", {}).items():
        if not package_path.startswith("node_modules/"):
            continue
        name = package_path.removeprefix("node_modules/")
        version = package.get("version")
        if isinstance(version, str):
            coordinates.add(("node", name, version))

    pnpm_lock = (
        REPOSITORY_ROOT / "frontend" / "pnpm-lock.yaml"
    ).read_text(encoding="utf-8")
    in_packages = False
    for line in pnpm_lock.splitlines():
        if line == "packages:":
            in_packages = True
            continue
        if in_packages and line and not line.startswith(" "):
            break
        if not in_packages:
            continue
        if not line.startswith("  ") or line.startswith("    "):
            continue
        key = line.strip().removesuffix(":").strip("'")
        coordinate = key.split("(", 1)[0]
        if "@" not in coordinate:
            continue
        name, version = coordinate.rsplit("@", 1)
        if name and version:
            coordinates.add(("node", name, version))

    return [
        _component(kind, name, version)
        for kind, name, version in sorted(coordinates)
    ]


def _spdx(
    *,
    artifacts: list[Path],
    version: str,
    commit: str,
    created_at: str,
) -> dict[str, Any]:
    app_id = "SPDXRef-Package-Angmoo"
    artifact_entries = []
    relationships = []
    for index, artifact in enumerate(artifacts, start=1):
        artifact_id = f"SPDXRef-File-Installer-{index}"
        artifact_entries.append(
            {
                "SPDXID": artifact_id,
                "fileName": artifact.name,
                "checksums": [
                    {"algorithm": "SHA256", "checksumValue": _sha256(artifact)}
                ],
                "licenseConcluded": "NOASSERTION",
                "copyrightText": "NOASSERTION",
            }
        )
        relationships.append(
            {
                "spdxElementId": app_id,
                "relationshipType": "CONTAINS",
                "relatedSpdxElement": artifact_id,
            }
        )
    components = _locked_components()
    relationships.extend(
        {
            "spdxElementId": app_id,
            "relationshipType": "DEPENDS_ON",
            "relatedSpdxElement": component["SPDXID"],
        }
        for component in components
    )
    return {
        "spdxVersion": "SPDX-2.3",
        "dataLicense": "CC0-1.0",
        "SPDXID": "SPDXRef-DOCUMENT",
        "name": f"angmoo-windows-installer-{version}",
        "documentNamespace": (
            "https://github.com/angmoo-tree/angmoo/sbom/"
            f"{commit}/windows-installer"
        ),
        "creationInfo": {
            "created": created_at,
            "creators": ["Tool: Angmoo ER6 deterministic SBOM generator"],
        },
        "documentDescribes": [app_id],
        "packages": [
            {
                "SPDXID": app_id,
                "name": "angmoo",
                "versionInfo": version,
                "downloadLocation": "NOASSERTION",
                "filesAnalyzed": True,
                "licenseConcluded": "GPL-3.0-only",
                "licenseDeclared": "GPL-3.0-only",
                "copyrightText": "NOASSERTION",
            },
            *components,
        ],
        "files": artifact_entries,
        "relationships": relationships,
    }


def _provenance(
    *,
    artifacts: list[Path],
    version: str,
    commit: str,
    created_at: str,
) -> dict[str, Any]:
    locks = [
        REPOSITORY_ROOT / "backend" / "uv.lock",
        REPOSITORY_ROOT / "frontend" / "pnpm-lock.yaml",
        REPOSITORY_ROOT / "desktop" / "package-lock.json",
        REPOSITORY_ROOT / "desktop" / "src-tauri" / "Cargo.lock",
    ]
    return {
        "_type": "https://in-toto.io/Statement/v1",
        "subject": [
            {"name": artifact.name, "digest": {"sha256": _sha256(artifact)}}
            for artifact in artifacts
        ],
        "predicateType": "https://slsa.dev/provenance/v1",
        "predicate": {
            "buildDefinition": {
                "buildType": "https://github.com/angmoo-tree/angmoo/er6-windows-installer/v1",
                "externalParameters": {"version": version, "commit": commit},
                "internalParameters": {"runnerOs": os.environ.get("RUNNER_OS", "local")},
                "resolvedDependencies": [
                    {
                        "uri": path.relative_to(REPOSITORY_ROOT).as_posix(),
                        "digest": {"sha256": _sha256(path)},
                    }
                    for path in locks
                ],
            },
            "runDetails": {
                "builder": {
                    "id": "https://github.com/angmoo-tree/angmoo/actions/workflows/windows-installer.yml"
                },
                "metadata": {
                    "invocationId": os.environ.get("GITHUB_RUN_ID", "local"),
                    "startedOn": created_at,
                    "finishedOn": created_at,
                },
            },
        },
    }


def main() -> int:
    args = _parser().parse_args()
    bundle_root = args.bundle_root.resolve()
    output_root = args.output_root.resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    artifacts = _artifact_files(bundle_root, version=args.version)
    created_at = datetime.now(UTC).replace(microsecond=0).isoformat()

    checksums = "".join(
        f"{_sha256(artifact)}  {artifact.name}\n" for artifact in artifacts
    )
    (output_root / "SHA256SUMS").write_text(checksums, encoding="ascii")
    (output_root / "angmoo-installer.spdx.json").write_text(
        json.dumps(
            _spdx(
                artifacts=artifacts,
                version=args.version,
                commit=args.commit,
                created_at=created_at,
            ),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    (output_root / "angmoo-installer.provenance.json").write_text(
        json.dumps(
            _provenance(
                artifacts=artifacts,
                version=args.version,
                commit=args.commit,
                created_at=created_at,
            ),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    shutil.copy2(
        REPOSITORY_ROOT / "THIRD_PARTY_NOTICES.md",
        output_root / "THIRD_PARTY_NOTICES.md",
    )
    shutil.copy2(REPOSITORY_ROOT / "LICENSE", output_root / "LICENSE")
    print(
        json.dumps(
            {
                "artifacts": [artifact.name for artifact in artifacts],
                "metadata_root": str(output_root),
                "status": "PASS",
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
