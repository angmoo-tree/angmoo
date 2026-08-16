"""Validate the L2 Windows thin-launcher contract without starting Angmoo."""

from __future__ import annotations

import ast
import json
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
CONTRACT_PATH = ROOT / "launcher/contract/local-launcher-v1.json"
WINDOWS_LAUNCHER = ROOT / "launcher/windows/Angmoo.Launcher.psm1"
ROOT_WRAPPER = ROOT / "angmoo.ps1"
PUBLIC_DOC = ROOT / "docs/public/local-launcher.md"

EXPECTED_COMMANDS = ["start", "stop", "restart", "status", "logs", "doctor"]
EXPECTED_SERVICES = {
    "backend", "frontend", "neo4j", "postgresql", "projector", "scheduler"
}
EXPECTED_EXIT_CODES = {
    "success": 0,
    "invalid_argument": 2,
    "container_engine_unavailable": 10,
    "preflight_failed": 11,
    "startup_failed": 20,
    "recovery_required": 21,
    "scheduler_singleton_mismatch": 22,
    "doctor_degraded": 30,
    "destructive_command_blocked": 40,
}
SHARED_RUNTIME_CODES = {
    "application_status_unavailable",
    "compose_config_invalid",
    "credential_recovery_required",
    "docker_engine_unavailable",
    "docker_usage_unavailable",
    "host_port_conflict",
    "runtime_disk_space_low",
    "runtime_start_timeout",
}
EXPECTED_LOCAL_ERROR_CODES = SHARED_RUNTIME_CODES | {
    "compose_unavailable",
    "destructive_command_blocked",
    "doctor_degraded",
    "launcher_invalid_argument",
    "lifecycle_lock_held",
    "lifecycle_stop_failed",
    "unsupported_architecture",
}
FORBIDDEN_LAUNCHER_SNIPPETS = (
    "down -v",
    "down --volumes",
    "volume prune",
    "volume rm",
    "system prune",
    "/var/run/docker.sock",
    "APP_SECRET=",
)


def _runtime_diagnostic_values(root: Path) -> set[str]:
    path = root / "backend/app/domains/runtime/domain/diagnostic_codes.py"
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    values: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == "RuntimeDiagnosticCode":
            for statement in node.body:
                if (
                    isinstance(statement, ast.Assign)
                    and len(statement.targets) == 1
                    and isinstance(statement.value, ast.Constant)
                    and isinstance(statement.value.value, str)
                ):
                    values.add(statement.value.value)
    return values


def validate_contract(payload: Any, *, root: Path = ROOT) -> list[str]:
    if not isinstance(payload, dict):
        return ["launcher contract root must be an object"]
    errors: list[str] = []
    if payload.get("contract_id") != "angmoo-local-launcher-v1":
        errors.append("launcher contract_id mismatch")
    if payload.get("result_schema") != "angmoo-launcher-result-v1":
        errors.append("launcher result schema mismatch")
    if payload.get("schema_version") != 1:
        errors.append("launcher schema_version must be 1")
    if payload.get("commands") != EXPECTED_COMMANDS:
        errors.append("launcher command surface mismatch")
    if payload.get("exit_codes") != EXPECTED_EXIT_CODES:
        errors.append("launcher exit-code contract mismatch")
    compose = payload.get("compose", {})
    if set(compose.get("required_services", [])) != EXPECTED_SERVICES:
        errors.append("launcher must target the complete Angmoo stack")
    if compose.get("release_files") != ["compose.yml"]:
        errors.append("release launcher must reuse compose.yml")
    if compose.get("contributor_files") != ["compose.yml", "compose.dev.yml"]:
        errors.append("contributor launcher must reuse the canonical dev overlay")
    safety = payload.get("safety", {})
    if safety.get("volume_delete_allowed") is not False:
        errors.append("normal launcher lifecycle must forbid volume deletion")
    if set(safety.get("forbidden_options", [])) != {
        "--purge", "--volumes", "--volume", "-v"
    }:
        errors.append("destructive option denylist mismatch")
    disk = payload.get("disk_policy_gib", {})
    if not (
        disk.get("filesystem_critical") == 2
        and disk.get("release_fresh_fail") == 10
        and disk.get("release_fresh_warn") == 15
        and disk.get("release_recommended") == 20
        and disk.get("contributor_fail") == 10
        and disk.get("contributor_warn") == 30
        and disk.get("contributor_recommended") == 40
    ):
        errors.append("release and contributor disk policies have drifted")
    error_codes = set(payload.get("error_codes", []))
    if error_codes != EXPECTED_LOCAL_ERROR_CODES:
        errors.append("launcher normalized error-code contract mismatch")
    if not SHARED_RUNTIME_CODES <= error_codes:
        errors.append("launcher is missing shared normalized runtime codes")
    if not SHARED_RUNTIME_CODES <= _runtime_diagnostic_values(root):
        errors.append("backend and launcher normalized runtime codes have drifted")
    return errors


def check_repo(*, root: Path = ROOT) -> list[str]:
    try:
        payload = json.loads((root / CONTRACT_PATH.relative_to(ROOT)).read_text(encoding="utf-8"))
        errors = validate_contract(payload, root=root)
        wrapper = (root / ROOT_WRAPPER.relative_to(ROOT)).read_text(encoding="utf-8")
        module = (root / WINDOWS_LAUNCHER.relative_to(ROOT)).read_text(encoding="utf-8")
        document = (root / PUBLIC_DOC.relative_to(ROOT)).read_text(encoding="utf-8")
    except (OSError, json.JSONDecodeError, SyntaxError) as exc:
        return [f"launcher contract cannot be read: {exc}"]

    for marker in (
        "Invoke-AngmooLauncher",
        "Write-AngmooLauncherHumanResult",
        "ConvertTo-Json -Depth 12 -Compress",
    ):
        if marker not in wrapper:
            errors.append(f"root launcher wrapper is missing: {marker}")
    for marker in (
        "Invoke-AngmooPreflight",
        "Invoke-AngmooLockedLifecycle",
        "Get-AngmooComposeArguments",
        "Get-AngmooLockName",
        "@('stop', '--timeout'",
        "$upArguments.Add('up'); $upArguments.Add('-d')",
        "'--wait-timeout'",
    ):
        if marker not in module:
            errors.append(f"Windows launcher is missing: {marker}")
    lowered = module.lower()
    for snippet in FORBIDDEN_LAUNCHER_SNIPPETS:
        if snippet.lower() in lowered:
            errors.append(f"destructive or privileged launcher path found: {snippet}")
    for marker in (
        ".\\angmoo.ps1 start",
        ".\\angmoo.ps1 doctor --json",
        "docker compose up -d",
        "named volumes",
        "30 GB",
    ):
        if marker not in document:
            errors.append(f"launcher document is missing: {marker}")
    return errors


def main() -> int:
    errors = check_repo()
    for error in errors:
        print(error, file=sys.stderr)
    if errors:
        return 1
    payload = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    print(
        "L2 launcher contract passed: "
        f"commands={len(payload['commands'])} services={len(payload['compose']['required_services'])}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
