"""Validate Angmoo's current GPL-3.0-only license surface and scope."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import sys
import tomllib
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = Path("security/license_policy.json")
EXPECTED_PROJECT_SPDX = "GPL-3.0-only"
OFFICIAL_GPL_V3_SHA256_LF = (
    "3972dc9744f6499f0f9b2dbf76696f2ae7ad8af9b23dde66d6af86c9dfb36986"
)
EXPECTED_SCOPE_KEYS = {"application", "world_packages", "runtime_data", "third_party"}
EXPECTED_CONDITIONAL_REVIEWS = {
    ("python", "certifi"),
    ("python", "crc32c"),
    ("python", "orjson"),
    ("node", "caniuse-lite"),
}


class ProjectLicenseError(RuntimeError):
    pass


def _repo_path(root: Path, value: str) -> Path:
    if not isinstance(value, str) or not value or "\0" in value or "\\" in value:
        raise ProjectLicenseError(f"invalid repository path: {value!r}")
    pure = PurePosixPath(value)
    if pure.is_absolute() or ".." in pure.parts or pure.as_posix() != value:
        raise ProjectLicenseError(f"invalid repository path: {value!r}")
    return root.joinpath(*pure.parts)


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ProjectLicenseError(f"could not read JSON policy: {path}") from exc
    if not isinstance(payload, dict):
        raise ProjectLicenseError("license policy root must be an object")
    return payload


def _lf_sha256(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _require_string(record: dict[str, Any], key: str, label: str, errors: list[str]) -> str:
    value = record.get(key)
    if not isinstance(value, str) or not value.strip():
        errors.append(f"{label}: {key} must be a non-empty string")
        return ""
    return value


def _validate_project(root: Path, policy: dict[str, Any], errors: list[str]) -> None:
    if policy.get("schema_version") != 1:
        errors.append("license policy schema_version must be 1")
    project = policy.get("project")
    if not isinstance(project, dict):
        errors.append("license policy project must be an object")
        return
    if project.get("spdx") != EXPECTED_PROJECT_SPDX:
        errors.append(f"project SPDX must be exactly {EXPECTED_PROJECT_SPDX}")
    if project.get("license_sha256_lf") != OFFICIAL_GPL_V3_SHA256_LF:
        errors.append("policy GPLv3 digest does not match the official LF-normalized text")

    license_value = project.get("license_path")
    try:
        license_path = _repo_path(root, license_value)
    except ProjectLicenseError as exc:
        errors.append(str(exc))
    else:
        if not license_path.is_file():
            errors.append(f"missing project license: {license_value}")
        elif _lf_sha256(license_path) != OFFICIAL_GPL_V3_SHA256_LF:
            errors.append("LICENSE is not the official GNU GPL version 3 text")

    required = project.get("required_current_legal_files")
    if required != ["LICENSE", "THIRD_PARTY_NOTICES.md"]:
        errors.append("current legal files must be LICENSE and THIRD_PARTY_NOTICES.md")
    elif not all(_repo_path(root, value).is_file() for value in required):
        errors.append("one or more required current legal files are missing")

    forbidden = project.get("forbidden_current_legal_files")
    if not isinstance(forbidden, list) or not forbidden:
        errors.append("forbidden current legal file list is missing")
    else:
        for value in forbidden:
            try:
                path = _repo_path(root, value)
            except ProjectLicenseError as exc:
                errors.append(str(exc))
                continue
            if path.exists():
                errors.append(f"obsolete or historical legal file must not exist: {value}")

    declarations = project.get("declarations")
    if not isinstance(declarations, list) or not declarations:
        errors.append("project declarations must be a non-empty list")
    else:
        seen: set[str] = set()
        for index, declaration in enumerate(declarations):
            label = f"project.declarations[{index}]"
            if not isinstance(declaration, dict):
                errors.append(f"{label} must be an object")
                continue
            relative = _require_string(declaration, "path", label, errors)
            if not relative:
                continue
            if relative in seen:
                errors.append(f"duplicate project declaration path: {relative}")
                continue
            seen.add(relative)
            try:
                path = _repo_path(root, relative)
            except ProjectLicenseError as exc:
                errors.append(str(exc))
                continue
            if not path.is_file():
                errors.append(f"missing project declaration file: {relative}")
                continue
            text = path.read_text(encoding="utf-8")
            required_markers = declaration.get("required")
            forbidden_markers = declaration.get("forbidden")
            if not isinstance(required_markers, list) or not all(
                isinstance(value, str) and value for value in required_markers
            ):
                errors.append(f"{label}: required markers are invalid")
            else:
                errors.extend(
                    f"{relative}: missing project license marker {marker}"
                    for marker in required_markers
                    if marker not in text
                )
            if not isinstance(forbidden_markers, list) or not all(
                isinstance(value, str) and value for value in forbidden_markers
            ):
                errors.append(f"{label}: forbidden markers are invalid")
            else:
                errors.extend(
                    f"{relative}: stale project license marker {marker}"
                    for marker in forbidden_markers
                    if marker in text
                )


def _validate_metadata(root: Path, errors: list[str]) -> None:
    try:
        backend = tomllib.loads((root / "backend/pyproject.toml").read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        errors.append(f"backend project metadata could not be read: {exc}")
    else:
        if backend.get("project", {}).get("license") != EXPECTED_PROJECT_SPDX:
            errors.append("backend project license must be GPL-3.0-only")

    try:
        frontend = json.loads((root / "frontend/package.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(f"frontend package metadata could not be read: {exc}")
    else:
        if frontend.get("license") != EXPECTED_PROJECT_SPDX:
            errors.append("frontend package license must be GPL-3.0-only")
        if frontend.get("private") is not True:
            errors.append("frontend package must remain private=true")


def _validate_scope(policy: dict[str, Any], errors: list[str]) -> None:
    scope = policy.get("scope")
    if not isinstance(scope, dict) or set(scope) != EXPECTED_SCOPE_KEYS:
        errors.append("license scope must separate application, World Packages, runtime data, and third parties")
        return
    if not all(isinstance(value, str) and value.strip() for value in scope.values()):
        errors.append("every license scope statement must be non-empty")
    if "does not automatically apply" not in scope.get("world_packages", ""):
        errors.append("World Package scope must reject automatic application GPL assignment")
    if "local user data" not in scope.get("runtime_data", ""):
        errors.append("runtime data scope must identify local user data")


def _validate_dependency_policy(policy: dict[str, Any], errors: list[str]) -> None:
    allowed = policy.get("allowed_license_ids")
    review_required = policy.get("review_required_license_ids")
    forbidden = policy.get("forbidden_license_ids")
    if not all(isinstance(value, list) for value in (allowed, review_required, forbidden)):
        errors.append("license id policy lists are missing")
        return
    allowed_set = set(allowed)
    required_set = set(review_required)
    forbidden_set = set(forbidden)
    if len(allowed_set) != len(allowed) or len(required_set) != len(review_required):
        errors.append("license id policy lists contain duplicates")
    if required_set - allowed_set:
        errors.append("review-required license ids must also be allowed ids")
    if allowed_set & forbidden_set:
        errors.append("allowed and forbidden license ids overlap")
    if "GPL-2.0-only" not in forbidden_set or "AGPL-3.0-only" not in forbidden_set:
        errors.append("GPL-2.0-only and AGPL-3.0-only must be fail-closed")

    reviews = policy.get("dependency_reviews")
    if not isinstance(reviews, list):
        errors.append("dependency reviews must be a list")
        return
    actual: set[tuple[str, str]] = set()
    for index, review in enumerate(reviews):
        label = f"dependency_reviews[{index}]"
        if not isinstance(review, dict):
            errors.append(f"{label} must be an object")
            continue
        ecosystem = _require_string(review, "ecosystem", label, errors)
        name = _require_string(review, "name", label, errors)
        for key in (
            "version",
            "reported_expression",
            "normalized_expression",
            "distribution_boundary",
            "source",
        ):
            _require_string(review, key, label, errors)
        obligations = review.get("obligations")
        if not isinstance(obligations, list) or not obligations or not all(
            isinstance(value, str) and value.strip() for value in obligations
        ):
            errors.append(f"{label}: obligations must be a non-empty string list")
        key = (ecosystem, name)
        if key in actual:
            errors.append(f"duplicate dependency review: {ecosystem}/{name}")
        actual.add(key)
    if actual != EXPECTED_CONDITIONAL_REVIEWS:
        errors.append(
            "conditional dependency reviews must be exactly: "
            + ", ".join(f"{ecosystem}/{name}" for ecosystem, name in sorted(EXPECTED_CONDITIONAL_REVIEWS))
        )


def _validate_references(root: Path, policy: dict[str, Any], errors: list[str]) -> None:
    for collection in ("bundled_content", "infrastructure", "actions", "assets"):
        records = policy.get(collection)
        if not isinstance(records, list) or not records:
            errors.append(f"{collection} inventory must be a non-empty list")
            continue
        for index, record in enumerate(records):
            label = f"{collection}[{index}]"
            if not isinstance(record, dict):
                errors.append(f"{label} must be an object")
                continue
            path_value = record.get("path") or record.get("source_path")
            try:
                path = _repo_path(root, path_value)
            except ProjectLicenseError as exc:
                errors.append(str(exc))
                continue
            if not path.exists():
                errors.append(f"{label}: referenced path does not exist: {path_value}")
                continue
            if sha256 := record.get("sha256"):
                if not isinstance(sha256, str) or hashlib.sha256(path.read_bytes()).hexdigest() != sha256:
                    errors.append(f"{label}: asset digest mismatch for {path_value}")
            if marker := record.get("notice_marker"):
                if not isinstance(marker, str) or marker not in path.read_text(encoding="utf-8"):
                    errors.append(f"{label}: missing notice marker in {path_value}")
            if reference := record.get("reference"):
                if not isinstance(reference, str) or reference not in path.read_text(encoding="utf-8"):
                    errors.append(f"{label}: pinned reference not found in {path_value}")

    notice = root / "THIRD_PARTY_NOTICES.md"
    if notice.is_file():
        text = notice.read_text(encoding="utf-8")
        required_notice_markers = [
            "## Reviewed conditional dependencies",
            "## Infrastructure and build tooling",
            "## Bundled assets and content",
        ]
        for review in policy.get("dependency_reviews", []):
            if isinstance(review, dict):
                required_notice_markers.append(
                    f"{review.get('name')} {review.get('version')}"
                )
        for record in policy.get("infrastructure", []):
            if isinstance(record, dict):
                required_notice_markers.append(str(record.get("name", "")))
        for record in policy.get("actions", []):
            if isinstance(record, dict):
                required_notice_markers.append(str(record.get("name", "")))
        for record in policy.get("assets", []):
            if isinstance(record, dict):
                required_notice_markers.append(str(record.get("name", "")))
        errors.extend(
            f"THIRD_PARTY_NOTICES.md: missing policy marker {marker}"
            for marker in required_notice_markers
            if marker and marker not in text
        )


def check(repo_root: Path, policy_path: Path | None = None) -> list[str]:
    root = repo_root.resolve()
    selected_policy = policy_path or (root / POLICY_PATH)
    try:
        policy = _read_json(selected_policy.resolve())
    except ProjectLicenseError as exc:
        return [str(exc)]
    errors: list[str] = []
    try:
        _validate_project(root, policy, errors)
        _validate_metadata(root, errors)
        _validate_scope(policy, errors)
        _validate_dependency_policy(policy, errors)
        _validate_references(root, policy, errors)
    except (OSError, UnicodeError, ValueError) as exc:
        errors.append(f"project license validation failed: {exc}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    parser.add_argument("--policy", type=Path)
    args = parser.parse_args()
    errors = check(args.repo_root, args.policy)
    for error in errors:
        print(error, file=sys.stderr)
    if errors:
        return 1
    print(
        "Project license check passed: "
        f"spdx={EXPECTED_PROJECT_SPDX} "
        f"license_sha256_lf={OFFICIAL_GPL_V3_SHA256_LF}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
