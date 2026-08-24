from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CHECKER = ROOT / "scripts" / "ci" / "check_windows_host_tauri_dev_contract.py"


def _load_checker():
    spec = importlib.util.spec_from_file_location(
        "check_windows_host_tauri_dev_contract", CHECKER
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_windows_host_tauri_dev_contract_is_complete() -> None:
    checker = _load_checker()
    assert checker.check_repo(root=ROOT) == []
