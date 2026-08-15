"""Validate locally built Angmoo runtime images without exposing secrets."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
from typing import Any


EXPECTED_SOURCE = "https://github.com/angmoo-tree/angmoo"
FORBIDDEN_ENVIRONMENT = {
    "APP_SECRET",
    "DATABASE_URL",
    "GEMINI_API_KEY",
    "GOOGLE_API_KEY",
    "NEO4J_AUTH",
    "NEO4J_PASSWORD",
    "POLLINATIONS_API_KEY",
    "POSTGRES_PASSWORD",
    "REPLICATE_API_TOKEN",
}
FORBIDDEN_HISTORY_MARKERS = tuple(
    marker.lower()
    for marker in (
        "APP_SECRET",
        "GEMINI_API_KEY",
        "GOOGLE_API_KEY",
        "NEO4J_AUTH",
        "NEO4J_PASSWORD",
        "POLLINATIONS_API_KEY",
        "POSTGRES_PASSWORD",
        "REPLICATE_API_TOKEN",
    )
)


def validate_image_document(
    document: Any,
    *,
    image: str,
    expected_revision: str,
    expected_version: str,
) -> list[str]:
    errors: list[str] = []
    if not isinstance(document, dict):
        return [f"image inspect is not an object: {image}"]
    config = document.get("Config")
    if not isinstance(config, dict):
        return [f"image Config is missing: {image}"]

    user = str(config.get("User") or "").strip().lower()
    if user in {"", "0", "root", "0:0", "root:root"}:
        errors.append(f"runtime image must use a non-root user: {image}")

    labels = config.get("Labels") or {}
    if not isinstance(labels, dict):
        labels = {}
    expected_labels = {
        "org.opencontainers.image.source": EXPECTED_SOURCE,
        "org.opencontainers.image.revision": expected_revision,
        "org.opencontainers.image.version": expected_version,
        "org.opencontainers.image.licenses": "GPL-3.0-only",
    }
    for key, expected in expected_labels.items():
        if labels.get(key) != expected:
            errors.append(
                f"OCI label mismatch: {image} {key}={labels.get(key)!r} expected={expected!r}"
            )

    environment = config.get("Env") or []
    environment_keys = {
        str(value).split("=", 1)[0]
        for value in environment
        if isinstance(value, str) and "=" in value
    }
    leaked_keys = sorted(FORBIDDEN_ENVIRONMENT & environment_keys)
    if leaked_keys:
        errors.append(
            f"runtime secret environment is baked into image: {image} keys={leaked_keys}"
        )

    if not config.get("Healthcheck"):
        errors.append(f"runtime image healthcheck is missing: {image}")
    if document.get("Os") != "linux":
        errors.append(f"runtime image OS must be linux: {image}")
    if document.get("Architecture") != "amd64":
        errors.append(f"unverified runtime architecture: {image}")
    return errors


def validate_history(image: str, lines: list[str]) -> list[str]:
    errors: list[str] = []
    lowered = "\n".join(lines).lower()
    exposed = sorted(
        marker for marker in FORBIDDEN_HISTORY_MARKERS if marker in lowered
    )
    if exposed:
        errors.append(f"secret marker found in image history: {image} markers={exposed}")
    return errors


def _inspect(image: str) -> dict[str, Any]:
    completed = subprocess.run(
        ["docker", "image", "inspect", image],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if completed.returncode:
        raise RuntimeError(completed.stderr.strip() or f"cannot inspect {image}")
    payload = json.loads(completed.stdout)
    if not isinstance(payload, list) or len(payload) != 1:
        raise RuntimeError(f"unexpected image inspect result: {image}")
    return payload[0]


def _history(image: str) -> list[str]:
    completed = subprocess.run(
        ["docker", "history", "--no-trunc", "--format", "{{json .CreatedBy}}", image],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if completed.returncode:
        raise RuntimeError(completed.stderr.strip() or f"cannot read history for {image}")
    return completed.stdout.splitlines()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", action="append", required=True)
    parser.add_argument("--revision", required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()

    errors: list[str] = []
    report: list[dict[str, str]] = []
    try:
        for image in args.image:
            document = _inspect(image)
            errors.extend(
                validate_image_document(
                    document,
                    image=image,
                    expected_revision=args.revision,
                    expected_version=args.version,
                )
            )
            errors.extend(validate_history(image, _history(image)))
            report.append({"image": image, "image_id": str(document.get("Id", ""))})
    except (OSError, RuntimeError, json.JSONDecodeError) as exc:
        errors.append(f"container image validation failed: {exc}")

    for error in errors:
        print(error, file=sys.stderr)
    if errors:
        return 1
    if args.report:
        args.report.write_text(
            json.dumps({"images": report}, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    print(f"Container image metadata passed: images={len(args.image)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
