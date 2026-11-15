from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
import yaml


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


def _workflow_document():
    workflow = ROOT / ".github/workflows/windows-host-tauri-dev.yml"
    document = yaml.safe_load(workflow.read_text(encoding="utf-8"))
    if True in document:
        document["on"] = document.pop(True)
    # Preserve historical path-coverage tests independently of current manual policy.
    required = ["backend/**", "frontend/**", "browser-tests/**", "security/frontend*",
                "scripts/ci/check_frontend_architecture_boundaries.py",
                "scripts/ci/frontend_completed_boundaries.py", "scripts/ci/refactor_boundaries.py"]
    document["on"] = {name: {"paths": list(required)} for name in ("push", "pull_request")}
    return document


def _errors_with_workflow(checker, monkeypatch, document):
    original_read = checker._read
    workflow = yaml.safe_dump(document, sort_keys=False)

    def read(root, relative):
        if relative == ".github/workflows/windows-host-tauri-dev.yml":
            return workflow
        return original_read(root, relative)

    monkeypatch.setattr(checker, "_read", read)
    return checker.check_workflow_triggers(workflow)


@pytest.mark.parametrize("event", ["push", "pull_request"])
def test_each_host_event_requires_all_backend_paths(event, monkeypatch) -> None:
    checker = _load_checker()
    document = _workflow_document()
    paths = document["on"][event]["paths"]
    document["on"][event]["paths"] = [path for path in paths if path != "backend/**"] + [
        "backend/app/runtime/migrations/**",
        "backend/app/domains/social/**",
    ]
    # The other event still contains backend/**; it cannot cover this event.
    assert f"Hosted Windows {event} paths must include backend/**" in _errors_with_workflow(
        checker, monkeypatch, document
    )


@pytest.mark.parametrize("event", ["push", "pull_request"])
@pytest.mark.parametrize("exclusion", ["!backend/app/main.py", "!backend/alembic/**", "!**/*.py"])
def test_host_events_reject_backend_exclusions(event, exclusion, monkeypatch) -> None:
    checker = _load_checker()
    document = _workflow_document()
    document["on"][event]["paths"].append(exclusion)

    assert f"Hosted Windows {event} paths must not exclude backend: {exclusion}" in _errors_with_workflow(
        checker, monkeypatch, document
    )


@pytest.mark.parametrize("event", ["push", "pull_request"])
def test_host_events_reject_backend_paths_ignore(event, monkeypatch) -> None:
    checker = _load_checker()
    document = _workflow_document()
    document["on"][event]["paths-ignore"] = ["backend/**"]

    assert f"Hosted Windows {event} must not use paths-ignore" in _errors_with_workflow(
        checker, monkeypatch, document
    )


def test_nonbackend_exclusions_keep_both_host_events_covered() -> None:
    checker = _load_checker()
    document = _workflow_document()
    for event in ("push", "pull_request"):
        document["on"][event]["paths"].append("!docs/**")

    assert checker.check_workflow_triggers(yaml.safe_dump(document, sort_keys=False)) == []


@pytest.mark.parametrize("event", ["push", "pull_request", "schedule"])
def test_current_native_host_rejects_automatic_events(event):
    checker = _load_checker()
    path = ROOT / ".github/workflows/windows-host-tauri-dev.yml"
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert checker.check_manual_workflow_triggers(yaml.safe_dump(document)) == []
    document[True][event] = {}
    assert checker.check_manual_workflow_triggers(yaml.safe_dump(document))
