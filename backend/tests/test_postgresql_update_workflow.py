"""Reject accidental PR triggers, emulation, write permissions and raw data exports."""
from pathlib import Path
from types import SimpleNamespace

import pytest
from scripts import check_ci_policy as checker
from scripts.ci import qualify_postgresql_update as qualifier

ROOT = Path(__file__).resolve().parents[2]
NAME = "postgresql-update-qualification.yml"


def document():
    return checker.yaml.load((ROOT / ".github/workflows" / NAME).read_text(), Loader=checker._UniqueKeyLoader)


def check(tmp_path, value):
    path = tmp_path / NAME
    path.write_text(checker.yaml.safe_dump(value, sort_keys=False))
    return checker.check_workflow(path)[0]


def test_manual_native_update_contract(tmp_path):
    assert check(tmp_path, document()) == []


@pytest.mark.parametrize("boundary", ["pr", "emulation", "write", "unbound", "raw-data", "extra-command", "credentials"])
def test_update_lane_rejects_unsafe_expansion(tmp_path, boundary):
    value = document()
    job = value["jobs"]["native-update"]
    if boundary == "pr":
        value["on"]["pull_request"] = None
    elif boundary == "emulation":
        job["strategy"]["matrix"]["include"][1]["runner"] = "ubuntu-24.04"
    elif boundary == "write":
        job["permissions"]["packages"] = "write"
    elif boundary == "unbound":
        job["env"]["CANDIDATE_ATTEMPT"] = "1"
    elif boundary == "raw-data":
        job["steps"][-1]["with"]["path"] += "\n${{ runner.temp }}/angmoo-pg-update/backups/**"
    elif boundary == "extra-command":
        job["steps"][2]["run"] += "\ndocker push unexpected:latest"
    else:
        job["steps"][0]["with"]["persist-credentials"] = True
    assert check(tmp_path, value)


def test_native_check_rejects_wrong_host_before_docker(monkeypatch):
    args = SimpleNamespace(source="a" * 40, candidate_run="1", candidate_attempt="2",
        candidate_artifact="3", architecture="arm64")
    monkeypatch.setattr(qualifier.platform, "machine", lambda: "AMD64")
    monkeypatch.setattr(qualifier, "run", lambda *args: pytest.fail("must not contact Docker"))
    with pytest.raises(ValueError, match="native_host"):
        qualifier.validate_inputs(args)


def test_host_match_cannot_hide_foreign_docker_engine(monkeypatch):
    args = SimpleNamespace(source="a" * 40, candidate_run="1", candidate_attempt="2",
        candidate_artifact="3", architecture="arm64")
    monkeypatch.setattr(qualifier.platform, "machine", lambda: "aarch64")
    monkeypatch.setattr(qualifier, "run", lambda *args: "x86_64")
    with pytest.raises(ValueError, match="native_docker"):
        qualifier.validate_inputs(args)
