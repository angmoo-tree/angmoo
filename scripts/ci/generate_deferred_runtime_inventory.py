"""Inventory runtime strings deferred from T2 to their Local conversion owners."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT = ROOT / "security/t2_deferred_runtime_inventory.json"
EXCLUDED = {
    "scripts/ci/generate_deferred_runtime_inventory.py",
    "security/t2_deferred_runtime_inventory.json",
}
MARKERS = {
    "product-host": ("angmoo.com", "L0-L4 product URL, privacy UX, provider referer"),
    "auth-host": ("auth.angmoo.com", "L0-L4 authentication origin"),
    "privacy-contact": ("privacy" + "@" + "angmoo.com", "L0-L4 local privacy contact UX"),
    "private-admin-flag": ("NEXT_PUBLIC_PRIVATE_ADMIN_ENABLED", "L0-L2 runtime feature-flag reference audit"),
    "hosted-extension-type": ("HostedBackendExtension", "L0-L4 hosted extension compatibility audit"),
}


def _tracked_files() -> list[str]:
    result = subprocess.run(
        ["git", "-C", str(ROOT), "ls-files", "-z"],
        capture_output=True,
        check=True,
    )
    return sorted(
        item.decode("utf-8", errors="surrogateescape")
        for item in result.stdout.split(b"\0")
        if item
    )


def render() -> str:
    entries: list[dict[str, object]] = []
    for relative in _tracked_files():
        if relative in EXCLUDED:
            continue
        path = ROOT / relative
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        found = sorted(
            marker_id
            for marker_id, (value, _) in MARKERS.items()
            if value in text
        )
        if found:
            entries.append(
                {
                    "path": relative,
                    "markers": found,
                    "owner_phases": sorted({MARKERS[marker][1] for marker in found}),
                }
            )
    payload = {
        "schema_version": 1,
        "purpose": "Strings intentionally deferred from T2 without bulk replacement",
        "entries": entries,
    }
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    if not args.write and not args.check:
        parser.error("use --write or --check")
    try:
        rendered = render()
        if args.write:
            args.output.write_text(rendered, encoding="utf-8", newline="\n")
        if args.check and args.output.read_text(encoding="utf-8") != rendered:
            raise RuntimeError("deferred runtime inventory is stale")
    except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
        print(f"Deferred runtime inventory failed: {exc}", file=sys.stderr)
        return 1
    print(f"Deferred runtime inventory passed: files={len(json.loads(rendered)['entries'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
