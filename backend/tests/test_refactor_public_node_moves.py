"""Keep the original public/private test baselines through repeated migrations."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "public_node_baseline", ROOT / "scripts/check_test_node_baseline.py"
)
assert SPEC is not None and SPEC.loader is not None
baseline = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(baseline)


def test_approved_subset_follows_transitive_moves_and_ignores_unrelated_origins():
    moves = {
        "old::test": "pilot::test", "pilot::test": "final::test",
        "later::test": "later_final::test",
        "unrelated_a::test": "unrelated_b::test", "unrelated_b::test": "unrelated_a::test",
    }
    assert baseline.resolve_approved_nodes(["old::test", "unchanged::test"], moves) == ["final::test", "unchanged::test"]


def test_unrelated_profile_move_does_not_count_as_a_second_approved_origin():
    assert baseline.resolve_approved_nodes(
        ["public_old::test"],
        {"public_old::test": "final::test", "private_only::test": "final::test"},
    ) == ["final::test"]


@pytest.mark.parametrize("moves", [
    {"first::test": "final::test", "second::test": "final::test"},
    {"first::test": "second::test"},
    {"first::test": "middle::test", "middle::test": "second::test"},
    {"first::test": "middle::test", "middle::test": "final::test", "second::test": "final::test"},
])
def test_independent_approved_cases_cannot_be_absorbed_into_one_destination(moves):
    with pytest.raises(RuntimeError, match="one-to-one"):
        baseline.resolve_approved_nodes(["first::test", "second::test"], moves)


@pytest.mark.parametrize("moves", [
    {"old::test": "old::test"},
    {"old::test": "middle::test", "middle::test": "old::test"},
    {"old::test": "middle::test", "middle::test": "end::test", "end::test": "middle::test"},
])
def test_reachable_cycle_is_an_error(moves):
    with pytest.raises(RuntimeError, match="cyclic"):
        baseline.resolve_approved_nodes(["old::test"], moves)


@pytest.mark.parametrize("moves", [[], {"old::test": []}, {"old::test": ""}, {1: "new::test"}])
def test_invalid_move_map_is_reported_without_a_type_error(moves):
    with pytest.raises(RuntimeError, match="exact string nodes"):
        baseline.resolve_approved_nodes(["old::test"], moves)


def test_original_baseline_counts_and_public_evidence_remain_unchanged():
    public_file, public_count = baseline.BASELINES["public"]
    private_file, private_count = baseline.BASELINES["private"]
    assert public_count == 604
    assert private_count == 641
    assert public_file.name == "m3_public_test_nodes.txt"
    assert private_file.name == "m3_private_test_nodes.txt"
    assert len(public_file.read_text(encoding="utf-8").splitlines()) == 604


@pytest.mark.parametrize("profile", ["public", "private"])
def test_profile_collection_keeps_existing_ignore_rules(monkeypatch, profile):
    commands = []

    def run(command, **kwargs):
        commands.append((command, kwargs))
        return SimpleNamespace(returncode=0, stdout="tests/test_a.py::test_case\n1 test collected\n", stderr="")

    monkeypatch.setattr(baseline.subprocess, "run", run)
    assert baseline.collect_nodes(profile) == ["tests/test_a.py::test_case"]
    command, options = commands[0]
    assert command[:6] == [baseline.sys.executable, "-m", "pytest", "--collect-only", "-q", "tests"]
    assert options["cwd"] == baseline.BACKEND_ROOT
    ignores = [part for part in command if part.startswith("--ignore=")]
    assert ignores == ([f"--ignore={path}" for path in baseline.IGNORED_TESTS] if profile == "public" else [])


def configure_cli(monkeypatch, tmp_path, current, moves):
    approved_file = tmp_path / "approved.txt"
    approved_file.write_text("old::test\nunchanged::test\n", encoding="utf-8")
    security = tmp_path / "security"
    security.mkdir()
    (security / "refactor_path_map.json").write_text(json.dumps({"test_nodes": moves}), encoding="utf-8")
    monkeypatch.setattr(baseline, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(baseline, "BASELINES", {
        "public": (approved_file, 2), "private": (tmp_path / "absent-private.txt", 3),
    })
    monkeypatch.setattr(baseline, "collect_nodes", lambda profile: current)
    monkeypatch.setattr(baseline.sys, "argv", ["check_test_node_baseline.py", "--profile", "public"])
    return approved_file


def test_cli_uses_the_final_destination_and_never_rewrites_approved_nodes(monkeypatch, tmp_path, capsys):
    approved = configure_cli(
        monkeypatch, tmp_path, ["final::test", "unchanged::test", "new::test"],
        {"old::test": "pilot::test", "pilot::test": "final::test", "later::test": "later_new::test"},
    )
    before = approved.read_bytes()
    assert baseline.main() == 0
    assert "public:approved=2" in capsys.readouterr().out
    assert approved.read_bytes() == before


def test_cli_rejects_missing_final_node_even_when_intermediate_still_collects(monkeypatch, tmp_path, capsys):
    configure_cli(
        monkeypatch, tmp_path, ["pilot::test", "unchanged::test"],
        {"old::test": "pilot::test", "pilot::test": "final::test"},
    )
    assert baseline.main() == 1
    assert "missing=1" in capsys.readouterr().err


def test_cli_rejects_an_independent_case_absorbed_by_an_unmoved_target(monkeypatch, tmp_path, capsys):
    configure_cli(monkeypatch, tmp_path, ["unchanged::test"], {"old::test": "unchanged::test"})
    assert baseline.main() == 1
    assert "one-to-one" in capsys.readouterr().err
