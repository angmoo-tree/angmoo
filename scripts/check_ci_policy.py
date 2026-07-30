"""Reject unsafe or unpinned GitHub Actions workflow configuration."""

from __future__ import annotations

import argparse
from pathlib import Path
import re
import sys

import yaml


ACTION = re.compile(r"(?m)^\s*-\s+uses:\s+([^\s#]+)")
FULL_SHA = re.compile(r"^[^@]+@[0-9a-f]{40}$")
FORBIDDEN = {
    "pull_request_target": "pull_request_target event",
    "repository_dispatch": "repository_dispatch event",
    "self-hosted": "self-hosted runner",
    "${{ secrets.": "repository secret reference",
    "secrets: inherit": "inherited secrets",
    "angmoo-private": "private repository reference",
    "actions/upload-artifact@": "raw artifact upload",
    "permissions: write": "write permission",
}
REQUIRED_JOBS = {
    "backend-contract",
    "hosted-impact",
    "frontend",
    "quickstart",
    "security-export",
    "dependency-audit",
}
REQUIRED_EVENTS = {"push", "pull_request", "workflow_dispatch"}


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


def _check_triggers(document: object) -> list[str]:
    if not isinstance(document, dict):
        return ["workflow root must be a mapping"]
    trigger_key: object | None = None
    if "on" in document:
        trigger_key = "on"
    elif True in document:
        # PyYAML's YAML 1.1 resolver treats the plain key `on` as boolean true.
        trigger_key = True
    if trigger_key is None or not isinstance(document[trigger_key], dict):
        return ["workflow events must be a mapping"]

    events = document[trigger_key]
    event_names = set(events)
    errors = [
        f"required workflow event is missing: {event}"
        for event in sorted(REQUIRED_EVENTS - event_names)
    ]
    errors.extend(
        f"unexpected workflow event: {event}"
        for event in sorted(event_names - REQUIRED_EVENTS)
    )
    push = events.get("push")
    if not isinstance(push, dict) or push.get("branches") != ["main"]:
        errors.append("push event must be limited to the main branch")
    return errors


def check(workflow: Path) -> list[str]:
    text = workflow.read_text(encoding="utf-8")
    errors: list[str] = []
    document: object | None = None
    try:
        document = yaml.load(text, Loader=_UniqueKeyLoader)
    except yaml.YAMLError as exc:
        errors.append(f"workflow YAML is invalid: {exc}")
    if document is not None:
        errors.extend(_check_triggers(document))
    errors.extend(
        [
        f"forbidden workflow feature: {label}"
        for marker, label in FORBIDDEN.items()
        if marker in text
        ]
    )
    actions = ACTION.findall(text)
    errors.extend(
        f"action is not pinned to a full commit SHA: {action}"
        for action in actions
        if not action.startswith("./") and not FULL_SHA.fullmatch(action)
    )
    if "permissions:\n  contents: read\n" not in text:
        errors.append("top-level permissions must be contents: read")
    missing_jobs = sorted(
        job for job in REQUIRED_JOBS if not re.search(rf"(?m)^  {re.escape(job)}:\s*$", text)
    )
    errors.extend(f"required job is missing: {job}" for job in missing_jobs)
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--workflow", type=Path, default=Path(".github/workflows/ci.yml")
    )
    args = parser.parse_args()
    try:
        errors = check(args.workflow)
    except OSError as exc:
        print(f"CI policy check failed: {exc}", file=sys.stderr)
        return 1
    for error in errors:
        print(error, file=sys.stderr)
    if errors:
        return 1
    print("CI policy check passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
