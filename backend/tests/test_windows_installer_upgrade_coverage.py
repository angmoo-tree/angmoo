"""Every readable native predecessor must finish, even across separate runners."""
from copy import deepcopy
import importlib.util
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("native_upgrade_coverage", ROOT / "scripts/ci/windows_installer_upgrade_coverage.py")
coverage = importlib.util.module_from_spec(spec)
spec.loader.exec_module(coverage)


def reports():
    versions = coverage.readable_predecessors()
    return [{"schema": coverage.SCHEMA, "status": "completed", "source_sha": "a" * 40,
        "run_id": "123", "run_attempt": "1", "partition": part,
        "versions": list(coverage.partition_versions(versions, part)), "idempotent": True}
        for part in coverage.PARTITIONS]


def test_native_upgrade_partitions_cover_current_registry_without_overlap():
    versions = coverage.readable_predecessors()
    first, second = (coverage.partition_versions(versions, part) for part in coverage.PARTITIONS)
    assert first and second and first + second == versions
    assert not set(first) & set(second)
    assert abs(len(first) - len(second)) <= 1
    assert coverage.partition_versions(versions, "all") == versions
    result = coverage.verify_reports(reports(), versions=versions, source_sha="a" * 40, run_id="123", run_attempt="1")
    assert result["covered"] == len(versions) and result["versions"] == list(versions)


@pytest.mark.parametrize("fault", ("missing", "duplicate_partition", "missing_version", "duplicated_version",
    "reordered_versions", "different_source", "different_run", "different_attempt", "no_idempotence", "unfinished", "extra_private_data"))
def test_native_upgrade_union_rejects_incomplete_wrong_run_or_private_reports(fault):
    values = deepcopy(reports())
    if fault == "missing": values.pop()
    elif fault == "duplicate_partition": values[1] = deepcopy(values[0])
    elif fault == "missing_version": values[0]["versions"].pop()
    elif fault == "duplicated_version": values[0]["versions"].append(values[0]["versions"][0])
    elif fault == "reordered_versions": values[0]["versions"].reverse()
    elif fault == "different_source": values[0]["source_sha"] = "b" * 40
    elif fault == "different_run": values[0]["run_id"] = "456"
    elif fault == "different_attempt": values[0]["run_attempt"] = "2"
    elif fault == "no_idempotence": values[0]["idempotent"] = False
    elif fault == "unfinished": values[0]["status"] = "running"
    elif fault == "extra_private_data": values[0]["data_root"] = "not allowed in the public receipt"
    with pytest.raises(ValueError):
        coverage.verify_reports(values, versions=coverage.readable_predecessors(), source_sha="a" * 40, run_id="123", run_attempt="1")


@pytest.mark.parametrize("versions,part", (((), "first"), ((1, 3), "second"), ((1, 2), "unsupported")))
def test_native_upgrade_partition_rejects_invalid_selection(versions, part):
    with pytest.raises(ValueError):
        coverage.partition_versions(versions, part)


def test_native_upgrade_hosted_wiring_preserves_bounds_actions_and_exact_union():
    document = yaml.safe_load((ROOT / ".github/workflows/windows-installer.yml").read_text(encoding="utf-8"))
    job = document["jobs"]["windows-installer-supported-upgrade"]
    assert job["strategy"] == {"fail-fast": False, "matrix": {"partition": ["first", "second"]}}
    assert job["timeout-minutes"] == 30 and "continue-on-error" not in job
    steps = job["steps"]
    assert any("-UpgradePartition ${{ matrix.partition }}" in step.get("run", "") for step in steps)
    upload = next(step for step in steps if step.get("name") == "Upload exact native upgrade coverage")
    assert upload["if"] == "always()" and upload["with"]["if-no-files-found"] == "error"
    assert upload["with"]["path"] == "${{ runner.temp }}/angmoo-supported-upgrade-${{ matrix.partition }}.json"
    aggregate = document["jobs"]["windows-installer"]
    assert aggregate["if"] == "always()" and aggregate["timeout-minutes"] == 5
    assert "windows-installer-supported-upgrade" in aggregate["needs"]
    assert any("windows_installer_upgrade_coverage.py" in step.get("run", "")
        and '--run-attempt "$GITHUB_RUN_ATTEMPT"' in step["run"] for step in aggregate["steps"])
    source = (ROOT / "scripts/ci/run_windows_installer_supported_upgrade.ps1").read_text(encoding="utf-8")
    assert "--select-partition $UpgradePartition" in source
    for version in coverage.readable_predecessors():
        assert f"if ($selectedVersions -contains {version})" in source
        assert f"Restore-IsolatedFixture $SupportedV{version}FixtureArchive" in source
        assert f"$supportedContract.source_data_version -ne {version}" in source
        assert f"$completedVersions.Add({version})" in source
    assert "windows_installer_idempotent_marker_changed" in source
    assert source.index("windows_installer_hosted_runner_only") < source.index("foreach ($required")
    assert source.index("Assert-SyntheticFixtureArchive $Archive") < source.index("Remove-IsolatedFixture", source.index("Assert-SyntheticFixtureArchive $Archive"))
