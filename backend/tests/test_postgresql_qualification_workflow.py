"""The manual native lane may upload sanitized receipts, never data or writes."""
import copy
from pathlib import Path

import pytest

from scripts import check_ci_policy as checker


ROOT = Path(__file__).resolve().parents[2]
NAME = "postgresql-docker-qualification.yml"


def document():
    return checker.yaml.load((ROOT / ".github/workflows" / NAME).read_text(encoding="utf-8"),
                             Loader=checker._UniqueKeyLoader)


def check(tmp_path, value):
    path = tmp_path / NAME
    path.write_text(checker.yaml.safe_dump(value, sort_keys=False), encoding="utf-8")
    return checker.check_workflow(path)[0]


def test_native_qualification_contract_passes(tmp_path):
    assert check(tmp_path, document()) == []


def test_shared_policy_accepts_existing_yaml11_contract_caller():
    parsed = checker.yaml.safe_load((ROOT / ".github/workflows" / NAME).read_text(encoding="utf-8"))
    assert True in parsed and "on" not in parsed
    assert checker.workflow_policy.validate(parsed, NAME) == []


def test_source_policy_rejects_actually_serialized_boolean_event_key(tmp_path):
    source = (ROOT / ".github/workflows" / NAME).read_text(encoding="utf-8")
    assert source.count("\non:\n") == 1
    target = tmp_path / NAME
    target.write_text(source.replace("\non:\n", "\ntrue:\n"), encoding="utf-8")
    assert any("event key" in error for error in checker.check_workflow(target)[0])


@pytest.mark.parametrize("change", [
    "trigger", "guard", "emulation", "write", "unbound-input", "unexpected-env",
    "publish-command", "extra-step", "raw-database", "directory-upload", "upload-condition",
    "extra-job", "cancel-existing", "credentials", "unpinned-action",
])
def test_native_qualification_refuses_boundary_changes(tmp_path, change):
    value = copy.deepcopy(document())
    job = value["jobs"]["native-arm64"]
    if change == "trigger":
        value["on"]["pull_request"] = None
    elif change == "guard":
        job["if"] = "always()"
    elif change == "emulation":
        job["runs-on"] = "ubuntu-24.04"
    elif change == "write":
        job["permissions"]["packages"] = "write"
    elif change == "unbound-input":
        value["on"]["workflow_dispatch"]["inputs"]["source"]["required"] = False
    elif change == "unexpected-env":
        job["env"]["DOCKER_HOST"] = "tcp://other-host:2375"
    elif change == "publish-command":
        job["steps"][3]["run"] += "\ndocker push unrelated:latest"
    elif change == "extra-step":
        job["steps"].insert(3, {"run": "echo unrelated"})
    elif change == "raw-database":
        job["steps"][-1]["with"]["path"] += "\n${{ runner.temp }}/angmoo-pg-qualification/backups/data.tar.gz"
    elif change == "directory-upload":
        job["steps"][-1]["with"]["path"] = "${{ runner.temp }}/angmoo-pg-qualification/"
    elif change == "upload-condition":
        job["steps"][-1]["if"] = "success()"
    elif change == "extra-job":
        value["jobs"]["unrelated"] = copy.deepcopy(job)
    elif change == "cancel-existing":
        value["concurrency"]["cancel-in-progress"] = True
    elif change == "credentials":
        job["steps"][0]["with"]["persist-credentials"] = True
    elif change == "unpinned-action":
        job["steps"][1]["uses"] = "docker/setup-buildx-action@v3"
    assert check(tmp_path, value), change
