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

# Core test jobs use synthetic fixtures and have no repository secrets. Allow
# only these result files, never an entire workspace, log directory or DB.
CORE_TEST_REPORT_PATHS = {
    "backend": (".ci/backend-shard-reports/backend-shard-coverage.json",),
    "backend-preflight": ("backend/.ci/backend-test-identity.json",),
    "backend-tests": (
        "backend/.ci/backend-junit.xml", "backend/.ci/backend-test-identity.json",
        "backend/.ci/backend-shard-report.json", "backend/.ci/backend-shard-events.jsonl",
    ),
    "frontend-work": (
        "browser-tests/.ci/web.xml", "browser-tests/.ci/settings.xml",
        "browser-tests/.ci/static.xml", "browser-tests/.ci/lifecycle.xml",
        "browser-tests/.ci/visual.xml", "browser-tests/.ci/creator-next.xml",
        "browser-tests/.ci/creator-static.xml", "browser-tests/.ci/card-upload.xml",
        "browser-tests/.ci/image-integration.xml",
        # This isolated suite uses only synthetic image fixtures and mocked APIs.
        # Preserve its failure diagnostics, never its entire output directory.
        "artifacts/image-integration/browser/**/test-failed-*.png",
        "artifacts/image-integration/browser/**/trace.zip",
        "browser-tests/.ci/daily-next.xml", "browser-tests/.ci/daily-static.xml",
        "browser-tests/.ci/browser-test-identity.json",
    ),
}
CORE_TEST_REPORT_NAMES = {
    "backend": "backend-coverage-${{ github.sha }}-${{ github.run_attempt }}",
    "backend-preflight": "backend-preflight-${{ github.sha }}-${{ github.run_attempt }}",
    "backend-tests": "backend-tests-${{ github.sha }}-${{ github.run_attempt }}-shard-${{ matrix.shard }}",
    "frontend-work": "browser-tests-${{ github.sha }}-${{ github.run_attempt }}",
}


def check_report_uploads(document: object, workflow_name: str, text: str) -> list[str]:
    if workflow_name == "windows-installer.yml":
        return []  # Its existing private-artifact rejection is checked below.
    jobs = document.get("jobs", {}) if isinstance(document, dict) else {}
    uploads = []
    for job_name, job in jobs.items() if isinstance(jobs, dict) else ():
        if not isinstance(job, dict):
            continue
        for step in job.get("steps", []):
            if isinstance(step, dict) and str(step.get("uses", "")).lower().startswith("actions/upload-artifact@"):
                uploads.append((job_name, step))
    errors = []
    if len(uploads) != text.lower().count("actions/upload-artifact@"):
        errors.append("artifact upload must be a declared bounded step")
    seen = set()
    for job_name, step in uploads:
        if workflow_name == "ci.yml" and job_name == "backend-preflight" and step.get("name") == "Share verified pinned sources with partitions":
            expected_sources = {
                "name": "vec1-sources-${{ github.sha }}-${{ github.run_attempt }}",
                "path": "\n".join("${{ runner.temp }}/angmoo-vec1-sources/sha256-" + sha + ".source-v1" for sha in (
                    "8571bb4f77f9547d11ad11e2f72e0de7d3b2ab44e7930151998bce9377ed4b86",
                    "bf3733d7c71b3ab0f6fd8a9ea0052ad87fa037d94333e14ce09878ba3492c3b0")),
                "if-no-files-found": "error", "retention-days": 3}
            actual_sources = dict(step.get("with", {}))
            actual_sources["path"] = actual_sources.get("path", "").strip()
            if (actual_sources != expected_sources or set(step) != {"name", "uses", "with"}
                    or step.get("uses") != "actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a"):
                errors.append("Vec1 sharing is limited to the two pinned source inputs")
            continue
        paths = CORE_TEST_REPORT_PATHS.get(job_name)
        options = step.get("with", {})
        expected = {
            "name": CORE_TEST_REPORT_NAMES.get(job_name),
            "path": "\n".join(paths or ()),
            "include-hidden-files": True,
            "if-no-files-found": "error",
        }
        actual = dict(options) if isinstance(options, dict) else {}
        if isinstance(actual.get("path"), str):
            actual["path"] = actual["path"].strip()
        if (workflow_name != "ci.yml" or paths is None or job_name in seen
                or step.get("uses") != "actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a"
                or step.get("if") != ("success() && needs.impact.outputs.backend == 'true'" if job_name == "backend" else "always()") or actual != expected
                or set(step) != {"name", "if", "uses", "with"}):
            errors.append("raw artifact upload is limited to the installer or exact Core test reports")
        seen.add(job_name)
    return errors


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


def _check_triggers(document: object, *, release: bool, weekly: bool = False) -> list[str]:
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
        for event in sorted(names - REQUIRED_EVENTS - ({"schedule"} if weekly else set()))
    )
    if weekly and events.get("schedule") != [{"cron": "23 3 * * 1"}]:
        errors.append("full validation requires the reviewed weekly schedule")
    push = events.get("push")
    if not isinstance(push, dict) or push.get("branches") != ["main"]:
        errors.append("push event must be limited to the main branch")
    if weekly and any(isinstance(events.get(event), dict) and any(key in events[event] for key in ("paths", "paths-ignore")) for event in ("push", "pull_request")):
        errors.append("required workflows must classify inside jobs, not skip on paths")
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


def check_pytest_paths(document: dict, root: Path) -> list[str]:
    """Check literal Python test arguments in workflow pytest steps.

    Collection of the full suite cannot detect a separately named smoke test
    left at an old path. Dynamic expressions and shell execution remain the
    responsibility of the actual workflow jobs.
    """
    errors: list[str] = []
    pattern = re.compile(r"(?<![\w/\\])(?:backend[/\\])?tests[/\\][\w./\\-]+\.py\b")
    for job_name, job in document.get("jobs", {}).items():
        if not isinstance(job, dict):
            continue
        for index, step in enumerate(job.get("steps", [])):
            if not isinstance(step, dict):
                continue
            command = step.get("run")
            if not isinstance(command, str) or not re.search(r"\bpytest\b", command):
                continue
            for literal in sorted(set(pattern.findall(command))):
                relative = literal.replace("\\", "/")
                if not relative.startswith("backend/"):
                    relative = "backend/" + relative
                candidate = (root / relative).resolve()
                if not candidate.is_relative_to(root.resolve()) or not candidate.is_file():
                    errors.append(
                        f"{job_name}.steps[{index}]: pytest test file is missing: {literal}"
                    )
    return errors


def check_backend_partitions(jobs: dict) -> list[str]:
    """Allow only a complete, always-run aggregate of the four isolated jobs."""
    if not {"backend-preflight", "backend-tests"}.intersection(jobs):
        return []  # Retain the older unpartitioned policy fixtures.
    backend, tests, preflight = (jobs.get(name, {}) for name in ("backend", "backend-tests", "backend-preflight"))
    errors = []
    if backend.get("if") != "always()" or backend.get("needs") != ["impact", "backend-preflight", "backend-tests"]:
        errors.append("backend aggregate must always require preflight and all partitions")
    if (tests.get("needs") != ["impact", "backend-preflight"] or tests.get("if") != "needs.impact.outputs.backend == 'true'"
            or tests.get("timeout-minutes") != 75
            or tests.get("strategy") != {"fail-fast": False, "matrix": {"shard": [0, 1, 2, 3]}}):
        errors.append("backend partitions must retain all four jobs without fail-fast or filtering")
    runner = 'uv run python ../scripts/ci/run_backend_shard.py --index "${{ matrix.shard }}" --source-sha "$TEST_SOURCE_SHA" --impact-plan ../.ci/impact.json'
    if sum(step.get("run") == runner and step.get("working-directory") == "backend"
            for step in tests.get("steps", [])) != 1:
        errors.append("backend partitions must use the whole-corpus execution owner")
    baseline = "python scripts/ci/check_ci_selection.py"
    if sum(step.get("run") == baseline for step in preflight.get("steps", [])) != 1:
        errors.append("backend preflight must verify current checkout selection")
    command = 'python scripts/ci/check_backend_shards.py --directory .ci/backend-shard-reports --source-sha "$TEST_SOURCE_SHA" --checkout-sha "$GITHUB_SHA" --impact-plan .ci/impact.json'
    if sum(str(step.get("run", "")).strip() == command for step in backend.get("steps", [])) != 1:
        errors.append("backend aggregate must verify every result and exact full coverage")
    return errors


def valid_required_gate(name: str, value: dict, jobs: dict) -> bool:
    if name not in {"backend", "frontend", "embedded-data-migration", "local-core-smoke", "local-autonomy-smoke", "local-full-graph"}:
        return False
    required = ["backend-preflight", "backend-tests"] if name == "backend" else [name + "-work"]
    expected_env = {"CI_IMPACT_PLAN": "${{ needs.impact.outputs.plan }}", "CI_NEEDS": "${{ toJSON(needs) }}"}
    if (value.get("if") != "always()" or value.get("needs") != ["impact", *required]
            or value.get("env") != expected_env or "continue-on-error" in value):
        return False
    selector = jobs.get("impact", {})
    if not any(step.get("id") == "select" and step.get("run") == "python scripts/ci/impact.py" for step in selector.get("steps", [])):
        return False
    if any(jobs.get(work, {}).get("if") != f"needs.impact.outputs.{name.replace('-', '_')} == 'true'" for work in required):
        return False
    return any(step.get("run") == f"python scripts/ci/gate.py --gate {name}" and "if" not in step and "continue-on-error" not in step for step in value.get("steps", []))


def check_installer_selection(jobs: dict) -> list[str]:
    """Keep the installer gate complete while distinguishing smoke and full."""
    conditions = {
        "release-candidate": "needs.impact.outputs.windows_installer == 'true'",
        "installed-runtime-smoke": "needs.impact.outputs.windows_installer == 'true'",
        "windows-installer-supported-upgrade": "needs.impact.outputs.windows == 'full'",
        "windows-installer-failure-recovery": "needs.impact.outputs.windows == 'full'",
        "windows-installer-representative-upgrade": "needs.impact.outputs.windows == 'installer-smoke'",
    }
    gate = jobs.get("windows-installer", {})
    errors = []
    if (gate.get("if") != "always()" or gate.get("needs") != ["impact", *conditions]
            or "continue-on-error" in gate):
        errors.append("installer aggregate must always require every selected producer")
    if any(jobs.get(name, {}).get("if") != condition or "continue-on-error" in jobs.get(name, {})
           for name, condition in conditions.items()):
        errors.append("installer profile conditions must preserve clean install, upgrade and recovery")
    selector = jobs.get("impact", {})
    if ("if" in selector or "continue-on-error" in selector or not any(
        step.get("id") == "select" and step.get("run") == "python scripts/ci/impact.py"
        and "if" not in step and "continue-on-error" not in step
        for step in selector.get("steps", [])
    )):
        errors.append("installer impact selection must run unconditionally")
    expected = "python scripts/ci/gate.py --gate windows-installer\necho windows_installer_required_matrix_pass"
    if not any(str(step.get("run", "")).strip() == expected and "if" not in step
               and "continue-on-error" not in step for step in gate.get("steps", [])):
        errors.append("installer required gate must verify actual producer results")
    coverage = 'python scripts/ci/windows_installer_upgrade_coverage.py --directory .ci/windows-upgrade-reports --source-sha "$SOURCE_SHA" --run-id "$GITHUB_RUN_ID" --run-attempt "$GITHUB_RUN_ATTEMPT" --profile "${{ needs.impact.outputs.windows }}"'
    if not any(step.get("run") == coverage and step.get("if") == conditions["release-candidate"]
               and "continue-on-error" not in step for step in gate.get("steps", [])):
        errors.append("installer gate must verify exact selected upgrade coverage")
    if gate.get("env", {}).get("CI_IMPACT_PLAN") != "${{ needs.impact.outputs.plan }}" or gate.get("env", {}).get("CI_NEEDS") != "${{ toJSON(needs) }}":
        errors.append("installer gate must use its current selection and job results")
    return errors


def check_workflow(path: Path, *, root: Path | None = None) -> tuple[list[str], list[str]]:
    text = path.read_text(encoding="utf-8")
    errors: list[str] = []
    try:
        document = yaml.load(text, Loader=_UniqueKeyLoader)
    except yaml.YAMLError as exc:
        return [f"workflow YAML is invalid: {exc}"], []
    errors.extend(_check_triggers(document, release=path.name == "release-images.yml", weekly=path.name in {"ci.yml", "local-smoke.yml", "windows-installer.yml"}))
    errors.extend(
        f"forbidden workflow feature: {label}"
        for marker, label in FORBIDDEN_TEXT.items()
        if marker in text
    )
    errors.extend(check_report_uploads(document, path.name, text))
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
    partition_errors = check_backend_partitions(jobs) if path.name == "ci.yml" else []
    errors.extend(partition_errors)
    if path.name == "windows-installer.yml":
        errors.extend(check_installer_selection(jobs))
    for job_name, value in jobs.items():
        if not isinstance(value, dict):
            errors.append(f"job must be a mapping: {job_name}")
            continue
        if "timeout-minutes" not in value:
            errors.append(f"job timeout is missing: {job_name}")
        complete_aggregate = valid_required_gate(job_name, value, jobs) and not partition_errors
        if job_name in REQUIRED_JOBS and "if" in value and not complete_aggregate:
            errors.append(f"required job must not be conditionally skipped: {job_name}")
    for label, image in _service_images(jobs):
        if "@sha256:" not in image:
            errors.append(f"service image is not pinned by digest: {label}={image}")
    if root is not None:
        errors.extend(check_pytest_paths(document, root))
    return errors, [str(name) for name in jobs]


def check_repo(root: Path = REPO_ROOT) -> list[str]:
    workflow_root = root / WORKFLOW_DIR
    actual = {path.name for path in workflow_root.glob("*.yml")}
    errors = [
        f"workflow set mismatch: expected={sorted(EXPECTED_WORKFLOWS)} actual={sorted(actual)}"
    ] if actual != EXPECTED_WORKFLOWS else []
    all_jobs: list[str] = []
    for name in sorted(actual):
        workflow_errors, jobs = check_workflow(workflow_root / name, root=root)
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
