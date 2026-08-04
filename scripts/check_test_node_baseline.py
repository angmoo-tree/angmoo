"""Verify that M4 preserves every approved M3 public test node."""

from __future__ import annotations

import argparse
from pathlib import Path
import subprocess
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = REPO_ROOT / "backend"
BASELINES = {
    "public": (BACKEND_ROOT / "security" / "m3_public_test_nodes.txt", 604),
    "private": (BACKEND_ROOT / "security" / "m3_private_test_nodes.txt", 641),
}
IGNORED_TESTS = (
    "tests/test_admin_operations.py",
    "tests/test_openclaw_gateway.py",
    "tests/test_inject_replicate_token_for_catgirl.py",
)


def collect_nodes(profile: str) -> list[str]:
    command = [
        sys.executable,
        "-m",
        "pytest",
        "--collect-only",
        "-q",
        "tests",
        *(
            (f"--ignore={path}" for path in IGNORED_TESTS)
            if profile == "public"
            else ()
        ),
    ]
    result = subprocess.run(
        command,
        cwd=BACKEND_ROOT,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "pytest collection failed")
    return sorted(
        line.strip()
        for line in result.stdout.splitlines()
        if line.startswith("tests/") and "::" in line
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--profile", choices=("public", "private", "both"))
    args = parser.parse_args()
    try:
        selected_profile = args.profile
        if selected_profile is None:
            selected_profile = (
                "both" if BASELINES["private"][0].exists() else "public"
            )
        profiles = (
            ("public", "private")
            if selected_profile == "both"
            else (selected_profile,)
        )
        summaries: list[str] = []
        for profile in profiles:
            baseline, expected_count = BASELINES[profile]
            current = collect_nodes(profile)
            m3_nodes = [node for node in current if "/test_m4_" not in node]
            if args.write:
                baseline.write_text(
                    "\n".join(m3_nodes) + "\n", encoding="utf-8", newline="\n"
                )
            approved = [
                line.strip()
                for line in baseline.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            missing = sorted(set(approved) - set(current))
            if len(approved) != expected_count or missing:
                raise RuntimeError(
                    f"profile={profile} approved={len(approved)} "
                    f"current={len(current)} missing={len(missing)}"
                )
            summaries.append(
                f"{profile}:approved={len(approved)} "
                f"current={len(current)} new={len(set(current) - set(approved))}"
            )
    except (OSError, RuntimeError) as exc:
        print(f"Test node baseline failed: {exc}", file=sys.stderr)
        return 1
    print("Test node baseline passed: " + " ".join(summaries))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
