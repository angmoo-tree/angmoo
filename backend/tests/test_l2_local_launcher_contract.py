from __future__ import annotations

from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/ci/check_local_launcher_contract.py"
SPEC = importlib.util.spec_from_file_location("check_local_launcher_contract", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
CHECKER = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = CHECKER
SPEC.loader.exec_module(CHECKER)


def _contract() -> dict[str, object]:
    return json.loads(
        (ROOT / "launcher/contract/local-launcher-v1.json").read_text(encoding="utf-8")
    )


def test_repository_launcher_contract_passes() -> None:
    assert CHECKER.check_repo(root=ROOT) == []


def test_launcher_contract_rejects_volume_deletion() -> None:
    payload = deepcopy(_contract())
    payload["safety"]["volume_delete_allowed"] = True
    assert "normal launcher lifecycle must forbid volume deletion" in CHECKER.validate_contract(
        payload, root=ROOT
    )


def test_launcher_contract_keeps_release_and_contributor_paths_separate() -> None:
    payload = deepcopy(_contract())
    payload["compose"]["release_files"] = ["compose.yml", "compose.dev.yml"]
    errors = CHECKER.validate_contract(payload, root=ROOT)
    assert "release launcher must reuse compose.yml" in errors


def test_launcher_contract_uses_stable_exit_codes() -> None:
    payload = deepcopy(_contract())
    payload["exit_codes"]["preflight_failed"] = 12
    assert "launcher exit-code contract mismatch" in CHECKER.validate_contract(
        payload, root=ROOT
    )


def test_launcher_and_runtime_share_host_diagnostic_codes() -> None:
    payload = _contract()
    assert CHECKER.SHARED_RUNTIME_CODES <= set(payload["error_codes"])
    assert CHECKER.SHARED_RUNTIME_CODES <= CHECKER._runtime_diagnostic_values(ROOT)
