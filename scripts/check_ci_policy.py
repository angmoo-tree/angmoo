"""Validate Angmoo's single-repository Local OSS workflow policy."""

from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path
import re
import sys

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_DIR = Path(".github/workflows")
EXPECTED_WORKFLOWS = {
    "ci.yml",
    "local-smoke.yml",
    "native-runtime-spike.yml",
    "security.yml",
    "windows-host-tauri-dev.yml",
    "windows-installer.yml",
    "windows-smoke.yml",
    "release-images.yml",
}
REQUIRED_JOBS = {
    "backend",
    "frontend",
    "embedded-data-migration",
    "sqlite-canonical-migration",
    "local-core-smoke",
    "local-autonomy-smoke",
    "local-full-graph",
    "oss-boundary",
    "dependency-license",
    "dco",
    "architecture-boundary",
}
ADVISORY_JOBS = {"windows-local-smoke"}
REQUIRED_EVENTS = {"push", "pull_request", "workflow_dispatch"}
ACTION = re.compile(r"(?m)^\s*-\s+uses:\s+([^\s#]+)")
FULL_SHA = re.compile(r"^[^@]+@[0-9a-f]{40}$")
FORBIDDEN_TEXT = {
    "pull_request_target": "pull_request_target event",
    "repository_dispatch": "repository_dispatch event",
    "self-hosted": "self-hosted runner",
    "${{ secrets.": "repository secret reference",
    "secrets: inherit": "inherited secrets",
    "angmoo-private": "private repository reference",
    "permissions: write": "write permission",
}


class _UniqueKeyLoader(yaml.SafeLoader):
    pass


def _construct_unique_mapping(
    loader: _UniqueKeyLoader,
    node: yaml.MappingNode,
    deep: bool = False,
) -> dict[object, object]:
    mapping: dict[object, object] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in mapping:
            raise yaml.constructor.ConstructorError(
                "while constructing a mapping",
                node.start_mark,
                f"found duplicate key {key!r}",
                key_node.start_mark,
            )
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


_UniqueKeyLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_unique_mapping,
)


def _events(document: dict[object, object]) -> object:
    if "on" in document:
        return document["on"]
    return document.get(True)


def _check_triggers(document: object, *, release: bool) -> list[str]:
    if not isinstance(document, dict):
        return ["workflow root must be a mapping"]
    events = _events(document)
    if not isinstance(events, dict):
        return ["workflow events must be a mapping"]
    names = set(events)
    if release:
        if names != {"push"}:
            return ["release workflow must be triggered only by push"]
        push = events.get("push")
        if not isinstance(push, dict) or push.get("tags") != ["v*.*.*"]:
            return ["release workflow must be limited to semantic v*.*.* tags"]
        if "branches" in push:
            return ["release workflow must not publish from a branch push"]
        return []
    errors = [
        f"required workflow event is missing: {event}"
        for event in sorted(REQUIRED_EVENTS - names)
    ]
    errors.extend(
        f"unexpected workflow event: {event}"
        for event in sorted(names - REQUIRED_EVENTS)
    )
    push = events.get("push")
    if not isinstance(push, dict) or push.get("branches") != ["main"]:
        errors.append("push event must be limited to the main branch")
    return errors


def _service_images(jobs: dict[object, object]) -> list[tuple[str, str]]:
    images: list[tuple[str, str]] = []
    for job_name, value in jobs.items():
        if not isinstance(value, dict):
            continue
        services = value.get("services", {})
        if not isinstance(services, dict):
            continue
        for service_name, service in services.items():
            if isinstance(service, dict) and isinstance(service.get("image"), str):
                images.append((f"{job_name}.{service_name}", service["image"]))
    return images


def check_workflow(path: Path) -> tuple[list[str], list[str]]:
    text = path.read_text(encoding="utf-8")
    errors: list[str] = []
    try:
        document = yaml.load(text, Loader=_UniqueKeyLoader)
    except yaml.YAMLError as exc:
        return [f"workflow YAML is invalid: {exc}"], []
    errors.extend(_check_triggers(document, release=path.name == "release-images.yml"))
    errors.extend(
        f"forbidden workflow feature: {label}"
        for marker, label in FORBIDDEN_TEXT.items()
        if marker in text
    )
    if "actions/upload-artifact@" in text and path.name != "windows-installer.yml":
        errors.append("raw artifact upload is limited to windows-installer.yml")
    if path.name == "windows-installer.yml":
        for forbidden_path in (
            "release-candidate-backup.json",
            "synthetic-fixture.json",
            "app-secret",
        ):
            if forbidden_path not in text:
                errors.append(
                    "installer private-artifact rejection is missing: "
                    f"{forbidden_path}"
                )
    for action in ACTION.findall(text):
        if not action.startswith("./") and not FULL_SHA.fullmatch(action):
            errors.append(f"action is not pinned to a full commit SHA: {action}")
    if not isinstance(document, dict):
        return errors, []
    if document.get("permissions") != {"contents": "read"}:
        errors.append("top-level permissions must be exactly contents: read")
    jobs = document.get("jobs")
    if not isinstance(jobs, dict):
        errors.append("workflow jobs must be a mapping")
        return errors, []
    for job_name, value in jobs.items():
        if not isinstance(value, dict):
            errors.append(f"job must be a mapping: {job_name}")
            continue
        if "timeout-minutes" not in value:
            errors.append(f"job timeout is missing: {job_name}")
        if job_name in REQUIRED_JOBS and "if" in value:
            errors.append(f"required job must not be conditionally skipped: {job_name}")
    for label, image in _service_images(jobs):
        if "@sha256:" not in image:
            errors.append(f"service image is not pinned by digest: {label}={image}")
    return errors, [str(name) for name in jobs]


def check_repo(root: Path = REPO_ROOT) -> list[str]:
    workflow_root = root / WORKFLOW_DIR
    actual = {path.name for path in workflow_root.glob("*.yml")}
    errors = [
        f"workflow set mismatch: expected={sorted(EXPECTED_WORKFLOWS)} actual={sorted(actual)}"
    ] if actual != EXPECTED_WORKFLOWS else []
    all_jobs: list[str] = []
    for name in sorted(actual):
        workflow_errors, jobs = check_workflow(workflow_root / name)
        errors.extend(f"{name}: {error}" for error in workflow_errors)
        all_jobs.extend(jobs)
    counts = Counter(all_jobs)
    for job in sorted(REQUIRED_JOBS | ADVISORY_JOBS):
        if counts[job] != 1:
            errors.append(f"job must appear exactly once: {job} count={counts[job]}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    args = parser.parse_args()
    try:
        errors = check_repo(args.repo_root.resolve())
    except OSError as exc:
        print(f"CI policy check failed: {exc}", file=sys.stderr)
        return 1
    for error in errors:
        print(error, file=sys.stderr)
    if errors:
        return 1
    print(
        "Local OSS CI policy check passed: "
        f"required={len(REQUIRED_JOBS)} advisory={len(ADVISORY_JOBS)} "
        f"workflows={len(EXPECTED_WORKFLOWS)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
