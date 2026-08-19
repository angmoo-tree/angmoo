from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
from pathlib import Path
import re
from typing import Any


def _spdx_id(ecosystem: str, name: str, version: str) -> str:
    value = re.sub(r"[^A-Za-z0-9.-]", "-", f"{ecosystem}-{name}-{version}")
    digest = hashlib.sha256(f"{ecosystem}:{name}:{version}".encode()).hexdigest()[:12]
    return f"SPDXRef-{value}-{digest}"


def _package(ecosystem: str, name: str, version: str, license_name: str | None) -> dict[str, Any]:
    declared = license_name or "NOASSERTION"
    if ecosystem == "python" and name.lower() == "pyinstaller":
        declared = "GPL-2.0-or-later WITH Bootloader-exception"
    return {
        "SPDXID": _spdx_id(ecosystem, name, version),
        "name": name,
        "versionInfo": version,
        "downloadLocation": "NOASSERTION",
        "filesAnalyzed": False,
        "licenseConcluded": "NOASSERTION",
        "licenseDeclared": declared,
        "supplier": "NOASSERTION",
        "comment": f"ecosystem={ecosystem}",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cargo-metadata", required=True, type=Path)
    parser.add_argument("--package-lock", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    packages: dict[tuple[str, str, str], dict[str, Any]] = {}
    for distribution in importlib.metadata.distributions():
        name = distribution.metadata.get("Name") or "unknown"
        version = distribution.version
        license_name = distribution.metadata.get("License-Expression") or distribution.metadata.get("License")
        packages[("python", name.lower(), version)] = _package("python", name, version, license_name)

    cargo = json.loads(args.cargo_metadata.read_text(encoding="utf-8-sig"))
    for item in cargo["packages"]:
        packages[("cargo", item["name"], item["version"])] = _package(
            "cargo", item["name"], item["version"], item.get("license")
        )

    package_lock = json.loads(args.package_lock.read_text(encoding="utf-8"))
    for path, item in package_lock.get("packages", {}).items():
        if not path or not item.get("version"):
            continue
        name = path.rsplit("node_modules/", 1)[-1]
        packages[("npm", name, item["version"])] = _package(
            "npm", name, item["version"], item.get("license")
        )

    ordered = [packages[key] for key in sorted(packages)]
    package_digest = hashlib.sha256(
        json.dumps(ordered, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    document = {
        "spdxVersion": "SPDX-2.3",
        "dataLicense": "CC0-1.0",
        "SPDXID": "SPDXRef-DOCUMENT",
        "name": "angmoo-l3-er1-native-runtime-spike",
        "documentNamespace": f"https://angmoo.local/spdx/l3-er1/{package_digest}",
        "creationInfo": {
            "creators": ["Tool: Angmoo ER1 deterministic SBOM generator"],
            "created": "2026-08-19T00:00:00Z",
        },
        "packages": ordered,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": "PASS", "packages": len(ordered), "digest": package_digest}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
