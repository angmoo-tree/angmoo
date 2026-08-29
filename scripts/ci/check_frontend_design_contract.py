"""Check the L4.5 frontend design, provenance, and inventory contract."""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import sys
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_POLICY = ROOT / "security/frontend_design_policy.json"
HEX_SHA = re.compile(r"^[0-9a-f]{40}$")
ABSOLUTE_WINDOWS_DRIVE_PATH = re.compile(r"(?i)(?<![A-Za-z0-9_])[a-z]:[\\/]")
ABSOLUTE_WINDOWS_UNC_PATH = re.compile(r"\\\\[^\\/\s`\"']+[\\/][^\\/\s`\"']+")
ABSOLUTE_UNIX_HOME_PATH = re.compile(
    r"(?:^|[\s`\"'(=])(?:~[/\\]|/(?:home|Users|workspace)/[^/\s`\"']+|/mnt/[A-Za-z]/)"
)
PRIVATE_CHECKOUT_LABEL = "angmoo-private"


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path}: root must be an object")
    return payload


def _sha256_bytes(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _sha256_text(path: Path) -> str:
    """Hash UTF-8 repository text with a checkout-independent LF contract."""

    text = path.read_text(encoding="utf-8")
    canonical = text.replace("\r\n", "\n").replace("\r", "\n")
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _repository_path(value: str, *, label: str) -> Path:
    posix = PurePosixPath(value)
    if posix.is_absolute() or ".." in posix.parts or "\\" in value:
        raise ValueError(f"{label} must be a portable repository-relative POSIX path")
    return ROOT.joinpath(*posix.parts)


def _canonical_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _validate_policy(policy: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if policy.get("schema_version") != 1:
        errors.append("policy.schema_version must be 1")
    if policy.get("policy_id") != "angmoo-l4-5-frontend-design-contract-v1":
        errors.append("policy.policy_id must be angmoo-l4-5-frontend-design-contract-v1")

    for field in (
        "design_contract",
        "documentation",
        "local_base_commit",
    ):
        if not isinstance(policy.get(field), str) or not policy[field]:
            errors.append(f"policy.{field} must be a non-empty string")

    base_commit = policy.get("local_base_commit")
    if isinstance(base_commit, str) and not HEX_SHA.fullmatch(base_commit):
        errors.append("policy.local_base_commit must be a full lowercase Git SHA")

    required_markers = policy.get("required_markers")
    if not isinstance(required_markers, dict):
        errors.append("policy.required_markers must be an object")
    else:
        for relative, markers in required_markers.items():
            if not isinstance(relative, str):
                errors.append("policy.required_markers keys must be strings")
                continue
            try:
                path = _repository_path(relative, label="required marker path")
            except ValueError as exc:
                errors.append(str(exc))
                continue
            if not path.is_file():
                errors.append(f"[missing_contract_file] {relative}")
                continue
            if not isinstance(markers, list) or not all(
                isinstance(marker, str) and marker for marker in markers
            ):
                errors.append(f"policy.required_markers[{relative}] must be a string array")
                continue
            text = path.read_text(encoding="utf-8")
            for marker in markers:
                if marker not in text:
                    errors.append(f"[missing_contract_marker] {relative}: {marker}")

    classifications = {"DIRECT", "ADAPTED", "LOCAL", "REJECTED"}
    adoption = policy.get("adoption_inventory")
    if not isinstance(adoption, list) or not adoption:
        errors.append("policy.adoption_inventory must be a non-empty array")
    else:
        seen: set[tuple[str, str | None, str | None, str]] = set()
        for index, item in enumerate(adoption):
            label = f"policy.adoption_inventory[{index}]"
            if not isinstance(item, dict):
                errors.append(f"{label} must be an object")
                continue
            classification = item.get("classification")
            source = item.get("hosted_source")
            blob = item.get("hosted_blob_oid")
            target = item.get("local_target")
            scope = item.get("scope")
            if classification not in classifications:
                errors.append(f"{label}.classification must be a supported adoption class")
            if not isinstance(scope, str) or not scope:
                errors.append(f"{label}.scope must be a non-empty string")
                continue
            key = (str(classification), source, target, scope)
            if key in seen:
                errors.append(f"{label} duplicates an adoption record")
            seen.add(key)

            if classification in {"DIRECT", "ADAPTED"} or (
                classification == "REJECTED" and (source is not None or blob is not None)
            ):
                if not isinstance(source, str) or not source.startswith("frontend/src/"):
                    errors.append(f"{label}.hosted_source must be a hosted frontend source path")
                if not isinstance(blob, str) or not HEX_SHA.fullmatch(blob):
                    errors.append(f"{label}.hosted_blob_oid must be a full Git blob OID")
            elif classification == "LOCAL" and (blob is not None or source is not None):
                errors.append(f"{label} cannot claim a hosted blob for {classification}")

            if target is not None:
                if not isinstance(target, str):
                    errors.append(f"{label}.local_target must be null or a string")
                else:
                    try:
                        target_path = _repository_path(target, label=f"{label}.local_target")
                    except ValueError as exc:
                        errors.append(str(exc))
                    else:
                        if not target_path.is_file():
                            errors.append(f"[missing_local_target] {target}")
            elif classification != "REJECTED":
                errors.append(f"{label}.local_target is required for {classification}")

    provenance = policy.get("provenance")
    if not isinstance(provenance, dict):
        errors.append("policy.provenance must be an object")
    else:
        for record_name, sha_fields in {
            "hosted_reference": ("commit", "license_blob_oid", "shared_history_commit"),
            "legacy_reference": ("design_revision", "design_blob_oid"),
            "local_repository": ("base_commit", "gpl_transition_commit"),
        }.items():
            record = provenance.get(record_name)
            if not isinstance(record, dict):
                errors.append(f"policy.provenance.{record_name} must be an object")
                continue
            for field in sha_fields:
                value = record.get(field)
                if not isinstance(value, str) or not HEX_SHA.fullmatch(value):
                    errors.append(
                        f"policy.provenance.{record_name}.{field} must be a full Git OID"
                    )

    raw = policy.get("raw_color_scan")
    if not isinstance(raw, dict):
        errors.append("policy.raw_color_scan must be an object")
    else:
        if raw.get("extensions") != [".css", ".ts", ".tsx"]:
            errors.append("policy.raw_color_scan.extensions must remain [.css, .ts, .tsx]")
        for field in ("baseline_occurrences", "baseline_files"):
            if not isinstance(raw.get(field), int) or raw[field] < 0:
                errors.append(f"policy.raw_color_scan.{field} must be a non-negative integer")
        try:
            re.compile(str(raw.get("pattern", "")))
        except re.error as exc:
            errors.append(f"policy.raw_color_scan.pattern is invalid: {exc}")

    portable_paths = policy.get("portable_contract_paths")
    if not isinstance(portable_paths, list) or not portable_paths:
        errors.append("policy.portable_contract_paths must be a non-empty array")
    else:
        seen_portable_paths: set[str] = set()
        for index, relative in enumerate(portable_paths):
            label = f"policy.portable_contract_paths[{index}]"
            if not isinstance(relative, str) or not relative:
                errors.append(f"{label} must be a non-empty string")
                continue
            if relative in seen_portable_paths:
                errors.append(f"{label} duplicates {relative}")
            seen_portable_paths.add(relative)
            try:
                path = _repository_path(relative, label=label)
            except ValueError as exc:
                errors.append(str(exc))
            else:
                if not path.is_file():
                    errors.append(f"[missing_portable_contract_file] {relative}")

    screenshots = policy.get("screenshot_inventory")
    if not isinstance(screenshots, dict):
        errors.append("policy.screenshot_inventory must be an object")
    else:
        for field in ("baseline_call_count", "committed_baseline_count"):
            if not isinstance(screenshots.get(field), int) or screenshots[field] < 0:
                errors.append(
                    f"policy.screenshot_inventory.{field} must be a non-negative integer"
                )

    routes = policy.get("route_surface_inventory")
    if not isinstance(routes, list) or not routes:
        errors.append("policy.route_surface_inventory must be a non-empty array")
    else:
        route_families: set[str] = set()
        for index, item in enumerate(routes):
            label = f"policy.route_surface_inventory[{index}]"
            if not isinstance(item, dict):
                errors.append(f"{label} must be an object")
                continue
            route = item.get("route_family")
            if not isinstance(route, str) or not route.startswith("/"):
                errors.append(f"{label}.route_family must start with /")
            elif route in route_families:
                errors.append(f"{label}.route_family duplicates {route}")
            else:
                route_families.add(route)
            next_file = item.get("next_route_file")
            if not isinstance(next_file, str):
                errors.append(f"{label}.next_route_file must be a string")
            else:
                try:
                    path = _repository_path(next_file, label=f"{label}.next_route_file")
                except ValueError as exc:
                    errors.append(str(exc))
                else:
                    if not path.is_file():
                        errors.append(f"[missing_next_route_file] {next_file}")
    return sorted(set(errors))


def _raw_color_report(policy: dict[str, Any]) -> dict[str, Any]:
    contract = policy["raw_color_scan"]
    source_root = _repository_path(contract["source_root"], label="raw color source root")
    pattern = re.compile(contract["pattern"])
    extensions = set(contract["extensions"])
    per_file: list[dict[str, Any]] = []
    per_extension: dict[str, dict[str, int]] = {
        extension: {"files": 0, "occurrences": 0} for extension in sorted(extensions)
    }
    values: Counter[str] = Counter()

    for path in sorted(
        candidate
        for candidate in source_root.rglob("*")
        if candidate.is_file() and candidate.suffix in extensions
    ):
        matches = [match.group(0).lower() for match in pattern.finditer(path.read_text(encoding="utf-8"))]
        if not matches:
            continue
        relative = path.relative_to(ROOT).as_posix()
        counts = Counter(matches)
        per_file.append(
            {
                "occurrences": len(matches),
                "path": relative,
                "values": dict(sorted(counts.items())),
            }
        )
        per_extension[path.suffix]["files"] += 1
        per_extension[path.suffix]["occurrences"] += len(matches)
        values.update(matches)

    return {
        "files": len(per_file),
        "occurrences": sum(item["occurrences"] for item in per_file),
        "pattern": contract["pattern"],
        "per_extension": per_extension,
        "per_file": per_file,
        "source_root": contract["source_root"],
        "values": dict(sorted(values.items())),
    }


def _static_direct_open_routes(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    match = re.search(r"const\s+ROUTES\s*=\s*\[(.*?)\]\s+as\s+const", text, re.DOTALL)
    if match is None:
        raise ValueError(f"{path}: static ROUTES array not found")
    return re.findall(r'"([^"\r\n]+)"', match.group(1))


def _build_report(policy: dict[str, Any]) -> dict[str, Any]:
    browser = policy["browser_harness"]
    package_path = _repository_path(browser["package"], label="browser package")
    lockfile_path = _repository_path(browser["lockfile"], label="browser lockfile")
    package = _load_json(package_path)
    playwright_version = package.get("devDependencies", {}).get("@playwright/test")
    if playwright_version != browser["playwright_version"]:
        raise ValueError(
            "browser-tests Playwright version drift: "
            f"expected {browser['playwright_version']}, got {playwright_version}"
        )
    lock_text = lockfile_path.read_text(encoding="utf-8")
    if f"@playwright/test@{playwright_version}" not in lock_text:
        raise ValueError("browser-tests lockfile does not contain the pinned Playwright version")

    adoption_targets: dict[str, set[str]] = {}
    for item in policy["adoption_inventory"]:
        target = item["local_target"]
        if target is None:
            continue
        adoption_targets.setdefault(target, set()).add(item["classification"])
    target_report = [
        {
            "classifications": sorted(classifications),
            "path": target,
            "sha256": _sha256_text(_repository_path(target, label="adoption target")),
        }
        for target, classifications in sorted(adoption_targets.items())
    ]

    next_inventory_path = ROOT / "docs/architecture/next-static-compatibility.json"
    next_inventory = _load_json(next_inventory_path)
    static_spec = ROOT / "browser-tests/static-product-shell.spec.ts"
    ignored_browser_parts = {"node_modules", "playwright-report", "test-results"}
    source_files = sorted(
        path
        for path in (ROOT / "browser-tests").rglob("*")
        if path.is_file()
        and path.suffix in {".ts", ".tsx"}
        and not ignored_browser_parts.intersection(path.parts)
    )
    screenshot_calls = 0
    for path in source_files:
        text = path.read_text(encoding="utf-8")
        screenshot_calls += text.count("toHaveScreenshot(") + text.count("page.screenshot(")
    snapshot_images = sorted(
        path.relative_to(ROOT).as_posix()
        for path in (ROOT / "browser-tests").rglob("*")
        if path.is_file()
        and path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}
        and not ignored_browser_parts.intersection(path.parts)
    )

    forbidden_matches: list[dict[str, str]] = []
    for relative in policy["portable_contract_paths"]:
        path = _repository_path(relative, label="portable contract path")
        text = path.read_text(encoding="utf-8")
        if ABSOLUTE_WINDOWS_DRIVE_PATH.search(text):
            forbidden_matches.append({"path": relative, "reason": "absolute_windows_drive_path"})
        if ABSOLUTE_WINDOWS_UNC_PATH.search(text):
            forbidden_matches.append({"path": relative, "reason": "absolute_windows_unc_path"})
        if ABSOLUTE_UNIX_HOME_PATH.search(text):
            forbidden_matches.append({"path": relative, "reason": "absolute_unix_home_path"})
        if PRIVATE_CHECKOUT_LABEL in text.lower():
            forbidden_matches.append({"path": relative, "reason": "private_checkout_label"})

    remote_font_markers: list[dict[str, str]] = []
    frontend_source = ROOT / "frontend/src"
    for path in sorted(
        candidate
        for candidate in frontend_source.rglob("*")
        if candidate.is_file() and candidate.suffix in {".css", ".ts", ".tsx"}
    ):
        text = path.read_text(encoding="utf-8")
        for marker in ("next/font", "@font-face", "fonts.googleapis.com"):
            if marker in text:
                remote_font_markers.append(
                    {"marker": marker, "path": path.relative_to(ROOT).as_posix()}
                )

    bundled_font_files = sorted(
        path.relative_to(ROOT).as_posix()
        for source in (
            ROOT / "frontend/public",
            ROOT / "frontend/src",
            ROOT / "frontend/static-shell",
        )
        for path in source.rglob("*")
        if path.is_file()
        and path.suffix.lower() in {".eot", ".otf", ".ttf", ".woff", ".woff2"}
        and "node_modules" not in path.parts
        and "out" not in path.parts
    )
    license_policy = _load_json(ROOT / "security/license_policy.json")
    frontend_assets: list[dict[str, Any]] = []
    for asset in license_policy.get("assets", []):
        if not isinstance(asset, dict) or not str(asset.get("path", "")).startswith(
            "frontend/"
        ):
            continue
        record = {
            key: asset[key]
            for key in ("license_expression", "name", "notice_marker", "path", "sha256")
            if key in asset
        }
        expected_sha = asset.get("sha256")
        if isinstance(expected_sha, str):
            asset_path = _repository_path(asset["path"], label="licensed frontend asset")
            actual_sha = _sha256_bytes(asset_path)
            if actual_sha != expected_sha:
                raise ValueError(
                    f"frontend asset hash drift: {asset['path']} expected={expected_sha} actual={actual_sha}"
                )
        frontend_assets.append(record)

    return {
        "adoption_targets": target_report,
        "browser_harness": {
            "configs": [
                {
                    "path": path,
                    "sha256": _sha256_text(_repository_path(path, label="browser config")),
                }
                for path in browser["configs"]
            ],
            "lockfile_sha256": _sha256_text(lockfile_path),
            "package": browser["package"],
            "playwright_version": playwright_version,
            "specs": [
                {
                    "path": path,
                    "sha256": _sha256_text(_repository_path(path, label="browser spec")),
                }
                for path in browser["specs"]
            ],
            "static_direct_open_routes": _static_direct_open_routes(static_spec),
        },
        "local_base_commit": policy["local_base_commit"],
        "policy_id": policy["policy_id"],
        "portable_contract": {
            "checked_paths": policy["portable_contract_paths"],
            "forbidden_matches": forbidden_matches,
        },
        "raw_colors": _raw_color_report(policy),
        "route_inventory": {
            "known_gap_count": len(policy["known_route_gaps"]),
            "next_static_inventory": next_inventory_path.relative_to(ROOT).as_posix(),
            "next_static_inventory_route_count": next_inventory.get("route_count"),
            "next_static_inventory_sha256": _sha256_text(next_inventory_path),
            "reviewed_surface_count": len(policy["route_surface_inventory"]),
        },
        "schema_version": 1,
        "source_dependency_audit": {
            "bundled_font_files": bundled_font_files,
            "licensed_frontend_assets": frontend_assets,
            "remote_font_markers": remote_font_markers,
            "sibling_runtime_dependency": False,
            "ui_a_external_asset_or_font_additions": 0,
        },
        "visual_inventory": {
            "committed_snapshot_images": snapshot_images,
            "screenshot_call_count": screenshot_calls,
            "status": policy["screenshot_inventory"]["current_status"],
            "target_viewports": policy["screenshot_inventory"]["target_viewports"],
        },
    }


def check(policy: dict[str, Any], report: dict[str, Any]) -> list[str]:
    errors = _validate_policy(policy)
    if errors:
        return errors
    expected = _build_report(policy)
    if report != expected:
        errors.append(
            "[stale_frontend_design_baseline] run "
            "python scripts/ci/check_frontend_design_contract.py --write"
        )
        return errors

    raw = report["raw_colors"]
    contract = policy["raw_color_scan"]
    if raw["occurrences"] != contract["baseline_occurrences"]:
        errors.append(
            "[raw_color_occurrence_drift] "
            f"expected={contract['baseline_occurrences']} actual={raw['occurrences']}"
        )
    if raw["files"] != contract["baseline_files"]:
        errors.append(
            "[raw_color_file_drift] "
            f"expected={contract['baseline_files']} actual={raw['files']}"
        )
    if report["portable_contract"]["forbidden_matches"]:
        errors.append("[non_portable_frontend_contract] remove private or absolute checkout paths")
    if report["source_dependency_audit"]["remote_font_markers"]:
        errors.append("[remote_font_dependency] Local design contract requires an offline system stack")
    if report["source_dependency_audit"]["bundled_font_files"]:
        errors.append("[unreviewed_bundled_font] record license and offline fallback before adding fonts")
    screenshots = policy["screenshot_inventory"]
    if report["visual_inventory"]["screenshot_call_count"] != screenshots["baseline_call_count"]:
        errors.append(
            "[visual_call_baseline_drift] update the reviewed screenshot inventory intentionally"
        )
    if len(report["visual_inventory"]["committed_snapshot_images"]) != screenshots[
        "committed_baseline_count"
    ]:
        errors.append(
            "[visual_snapshot_baseline_drift] update the reviewed screenshot inventory intentionally"
        )
    return sorted(set(errors))


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--check", action="store_true", help="verify the tracked report")
    action.add_argument("--write", action="store_true", help="write the deterministic report")
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    args = parser.parse_args(list(argv) if argv is not None else None)

    try:
        policy = _load_json(args.policy)
        policy_errors = _validate_policy(policy)
        if policy_errors:
            for error in policy_errors:
                print(error, file=sys.stderr)
            return 1
        report_path = _repository_path(
            policy["raw_color_scan"]["report"], label="raw color report"
        )
        expected = _build_report(policy)
        if args.write:
            report_path.parent.mkdir(parents=True, exist_ok=True)
            report_path.write_text(_canonical_json(expected), encoding="utf-8", newline="\n")
            print(f"Wrote {report_path.relative_to(ROOT).as_posix()}")
            return 0
        if not report_path.is_file():
            print(f"Frontend design baseline missing: {report_path}", file=sys.stderr)
            return 1
        report = _load_json(report_path)
        errors = check(policy, report)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"Frontend design contract check failed: {exc}", file=sys.stderr)
        return 1

    for error in errors:
        print(error, file=sys.stderr)
    if errors:
        return 1
    print(
        "Frontend design contract check passed: "
        f"raw_colors={report['raw_colors']['occurrences']} "
        f"files={report['raw_colors']['files']} "
        f"surfaces={report['route_inventory']['reviewed_surface_count']} "
        f"route_gaps={report['route_inventory']['known_gap_count']} "
        f"screenshots={report['visual_inventory']['screenshot_call_count']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
