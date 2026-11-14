"""Changed-path scope is conservative and required gates fail closed."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/ci"))
from impact import build_plan, classify, changed_paths, digest, plan_reference, read_plan, select_nodes
from gate import verify
from test_t2_ci_policy import checker as ci_policy


@pytest.mark.parametrize("path", [".github/workflows/ci.yml", "scripts/build_vec1.py", "security/license_policy.json", "backend/conftest.py", "backend/tests/conftest.py", "new/runtime/tool", "backend/app/runtime/migrations/upgrade.py", "desktop/src-tauri/installer-hooks.nsh"])
def test_unknown_shared_security_and_migrations_select_full(path):
    selection = classify([path])
    assert selection["backend"] == "full" and selection["windows"] == "none"
    assert_supported_full(selection)


def test_documentation_is_explicitly_not_applicable_but_no_diff_is_full():
    result = classify(["docs/operations/example.md"])
    assert not any(result["jobs"].values()) and result["reasons"]
    assert_supported_full(classify([]))
    assert_supported_full(classify(["README.md"], unknown_diff=True))


def test_backend_test_only_selects_owning_suite_without_installation():
    result = classify(["backend/tests/memory/test_search.py"])
    assert result["backend"] == "scoped"
    assert result["test_paths"] == ["tests/memory/test_search.py"]
    assert result["windows"] == "none"
    assert result["jobs"]["backend"] and not result["jobs"]["windows-installer"]


def test_manual_native_opt_in_retains_original_matrix():
    assert classify(["frontend/src/features/chat/example.tsx"], native_windows=True)["windows"] == "build"
    assert classify(["backend/app/domains/chat/service/messages.py"])["backend"] == "full"
    assert classify(["backend/uv.lock", "frontend/src/features/chat/example.tsx"], native_windows=True)["windows"] == "installer-smoke"
    assert classify(["backend/uv.lock", "desktop/src-tauri/installer-hooks.nsh"], native_windows=True)["windows"] == "full"


def test_rename_keeps_both_sides_and_deleted_paths(tmp_path):
    def git(*args):
        return subprocess.check_output(["git", *args], cwd=tmp_path, text=True).strip()
    git("init", "--quiet")
    git("config", "user.name", "Synthetic fixture")
    git("config", "user.email", "fixture@example.test")
    (tmp_path / "danger.py").write_text("old source")
    git("add", ".")
    git("-c", "commit.gpgsign=false", "commit", "--quiet", "-m", "old")
    base = git("rev-parse", "HEAD")
    (tmp_path / "danger.py").rename(tmp_path / "notes.md")
    git("add", ".")
    git("-c", "commit.gpgsign=false", "commit", "--quiet", "-m", "new")
    assert changed_paths(base, git("rev-parse", "HEAD"), pull_request=True, root=tmp_path) == ["danger.py", "notes.md"]


def test_large_change_uses_small_reference_without_losing_paths_or_gate_checks(tmp_path,monkeypatch):
    def git(*args):
        return subprocess.check_output(["git", *args], cwd=tmp_path, text=True).strip()
    git("init", "--quiet");git("config", "user.name", "Synthetic fixture")
    git("config", "user.email", "fixture@example.test")
    policy=tmp_path/'scripts/ci/impact.py';policy.parent.mkdir(parents=True)
    policy.write_bytes((ROOT/'scripts/ci/impact.py').read_bytes())
    git("add", ".");git("-c", "commit.gpgsign=false", "commit", "--quiet", "-m", "base")
    base=git("rev-parse", "HEAD")
    for index in range(700):
        path=tmp_path/('backend/app/domains/characters/service/fixture_'+str(index)+'x'*75+'.py')
        path.parent.mkdir(parents=True,exist_ok=True);path.write_text('VALUE = 1\n')
    git("add", ".");git("-c", "commit.gpgsign=false", "commit", "--quiet", "-m", "large change")
    source=git("rev-parse", "HEAD")
    event={'pull_request':{'head':{'sha':source},'base':{'sha':base}}}
    event_file=tmp_path/'event.json';event_file.write_text(json.dumps(event))
    monkeypatch.setenv('GITHUB_EVENT_PATH',str(event_file));monkeypatch.setenv('GITHUB_EVENT_NAME','pull_request')
    plan=build_plan(event=event,event_name='pull_request',mode='active',requested='auto',root=tmp_path)
    assert len(json.dumps(plan).encode())>131072
    reference=plan_reference(plan)
    assert len(json.dumps(reference).encode())<2048
    transmitted=tmp_path/'received.json';transmitted.write_text(json.dumps(reference))
    actual=read_plan(transmitted,root=tmp_path)
    assert actual==plan and len(actual['effective']['paths'])==700
    assert actual['effective']['backend'] == 'full'
    assert actual['effective']['jobs'] == plan['effective']['jobs']
    reference['selection_sha256']='0'*64;transmitted.write_text(json.dumps(reference))
    with pytest.raises(ValueError,match='actual_event'):read_plan(transmitted,root=tmp_path)


def test_scoped_collection_includes_cross_suite_import_consumers(tmp_path):
    root = tmp_path / "backend/tests"
    for name, text in {"memory/test_index.py": "VALUE = 1", "memory/test_query.py": "pass", "chat/test_search.py": "from memory.test_index import VALUE", "social/test_view.py": "from chat.test_search import VALUE", "worlds/test_unrelated.py": "pass"}.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    nodes = [f"tests/{name}::test_case" for name in ("memory/test_index.py", "memory/test_query.py", "chat/test_search.py", "social/test_view.py", "worlds/test_unrelated.py")]
    result = select_nodes(nodes, classify(["backend/tests/memory/test_index.py"]), root=tmp_path)
    assert result == nodes[:-1]


@pytest.mark.parametrize("import_text", [
    "from ..memory.test_index import VALUE",
    "from tests.memory import test_index",
    "import tests.memory.test_index",
    "import importlib\nvalue = importlib.import_module('tests.memory.test_index')",
])
def test_relative_and_package_import_consumers_are_selected(tmp_path, import_text):
    root = tmp_path / "backend/tests"
    for name, text in {"memory/test_index.py": "VALUE = 1", "chat/test_consumer.py": import_text,
                       "worlds/test_unrelated.py": "pass"}.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    nodes = [f"tests/{name}::test_case" for name in ("memory/test_index.py", "chat/test_consumer.py", "worlds/test_unrelated.py")]
    assert select_nodes(nodes, classify(["backend/tests/memory/test_index.py"]), root=tmp_path) == nodes[:-1]


def test_unknown_dynamic_import_expands_to_complete_corpus(tmp_path):
    root = tmp_path / "backend/tests"
    root.mkdir(parents=True)
    (root / "test_a.py").write_text("VALUE = 1")
    (root / "test_b.py").write_text("import importlib\nvalue = importlib.import_module(name)")
    nodes = ["tests/test_a.py::test_a", "tests/test_b.py::test_b"]
    assert select_nodes(nodes, classify(["backend/tests/test_a.py"]), root=tmp_path) == nodes


@pytest.mark.parametrize("damage", ["missing_recovery", "skip_gate", "skip_selector", "weaken_full", "fake_gate", "omit_coverage"])
def test_installer_policy_rejects_incomplete_profile_wiring(damage):
    jobs = ci_policy.yaml.load((ROOT / ".github/workflows/windows-installer.yml").read_text(encoding="utf-8"), Loader=ci_policy._UniqueKeyLoader)["jobs"]
    assert ci_policy.check_installer_selection(jobs) == []
    if damage == "missing_recovery":
        jobs["windows-installer"]["needs"].remove("windows-installer-failure-recovery")
    elif damage == "skip_gate":
        jobs["windows-installer"]["if"] = "success()"
    elif damage == "skip_selector":
        jobs["impact"]["if"] = "false"
    elif damage == "weaken_full":
        jobs["windows-installer-failure-recovery"]["if"] = "false"
    else:
        text = "gate.py" if damage == "fake_gate" else "windows_postgresql_coverage.py"
        step = next(step for step in jobs["windows-installer"]["steps"] if text in str(step.get("run")))
        step["run"] = "echo success"
    assert ci_policy.check_installer_selection(jobs)


@pytest.mark.parametrize("state", ["failure", "cancelled", "skipped", None])
def test_required_selected_work_cannot_be_hidden(state):
    selection = classify(["frontend/src/page.tsx"])
    plan = {"effective": selection, "selection_sha256": digest(selection)}
    with pytest.raises(ValueError, match="required_work"):
        verify("frontend", plan, {"impact": {"result": "success"}, "frontend-work": {"result": state}})


def test_not_applicable_requires_successful_impact_and_skipped_or_successful_work():
    selection = classify(["docs/guide.md"])
    plan = {"effective": selection, "selection_sha256": digest(selection)}
    needs = {"impact": {"result": "success"}, "frontend-work": {"result": "skipped"}}
    assert verify("frontend", plan, needs)["status"] == "not_applicable"
    needs["impact"]["result"] = "failure"
    with pytest.raises(ValueError, match="impact"):
        verify("frontend", plan, needs)


def test_automatic_frontend_gate_has_no_native_dependency():
    selection = classify(["frontend/src/page.tsx"])
    assert selection["windows"] == "none"
    plan = {"effective": selection, "selection_sha256": digest(selection)}
    needs = {"impact": {"result": "success"}, "frontend-work": {"result": "success"}}
    assert verify("frontend", plan, needs)["required_jobs"] == ["frontend-work"]


def test_browser_only_changes_do_not_require_an_unselected_windows_build():
    selection = classify(["browser-tests/chat.spec.ts"])
    plan = {"effective": selection, "selection_sha256": digest(selection)}
    needs = {"impact": {"result": "success"}, "frontend-work": {"result": "success"},
             "tauri-windows": {"result": "skipped"}}
    assert verify("frontend", plan, needs)["required_jobs"] == ["frontend-work"]


@pytest.mark.parametrize("damage", ["missing_dependency", "skip_build", "ignore_build_failure"])
def test_frontend_policy_keeps_supported_work_in_the_required_gate(damage):
    jobs = ci_policy.yaml.load((ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8"), Loader=ci_policy._UniqueKeyLoader)["jobs"]
    assert ci_policy.valid_required_gate("frontend", jobs["frontend"], jobs)
    if damage == "missing_dependency":
        jobs["frontend"]["needs"].remove("frontend-work")
    elif damage == "skip_build":
        jobs["frontend-work"]["if"] = "false"
    else:
        jobs["frontend-work"]["continue-on-error"] = True
    assert not ci_policy.valid_required_gate("frontend", jobs["frontend"], jobs)


def test_full_installer_requires_every_partition_and_recovery():
    selection = classify([], force_full=True, native_windows=True)
    plan = {"effective": selection, "selection_sha256": digest(selection)}
    needs = {name: {"result": "success"} for name in ("impact", "release-candidate", "installed-runtime-smoke", "windows-installer-supported-upgrade", "windows-installer-failure-recovery")}
    assert verify("windows-installer", plan, needs)["status"] == "passed"
    del needs["windows-installer-failure-recovery"]
    with pytest.raises(ValueError, match="required_work"):
        verify("windows-installer", plan, needs)


def assert_supported_full(selection):
    native = {"windows-installer", "windows-native", "tauri-windows", "tauri-windows-host-dev"}
    assert all(value is (name not in native) for name, value in selection["jobs"].items())


@pytest.mark.parametrize("event", ["pull_request", "push", "schedule"])
def test_automatic_events_cannot_opt_into_native(monkeypatch, event):
    import impact
    monkeypatch.setattr(impact, "git", lambda *a, **kw: "a" * 40)
    monkeypatch.setattr(impact, "changed_paths", lambda *a, **kw: ["backend/uv.lock"])
    monkeypatch.setattr(impact.subprocess, "run", lambda *a, **kw: None)
    monkeypatch.setenv("GITHUB_WORKFLOW", "Windows Installer")
    plan = build_plan(event={"inputs": {"native_windows": "true"}}, event_name=event, mode="observe", requested="full")
    assert_supported_full(plan["effective"])
