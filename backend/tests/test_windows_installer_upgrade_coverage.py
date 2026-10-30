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


def test_current_hosted_wiring_preserves_bounds_actions_and_exact_union():
    document=yaml.safe_load((ROOT/'.github/workflows/windows-installer.yml').read_text())
    job=document['jobs']['windows-installer-supported-upgrade']
    assert 'strategy' not in job and job['timeout-minutes']==35 and 'continue-on-error' not in job
    assert any('-Kind upgrade-013' in step.get('run','') for step in job['steps'])
    upload=next(step for step in job['steps'] if step.get('name')=='Preserve exact qualification checks')
    assert upload['if']=='always()' and upload['with']['if-no-files-found']=='error'
    aggregate=document['jobs']['windows-installer']
    assert aggregate['if']=='always()' and aggregate['timeout-minutes']==5
    assert any('windows_postgresql_coverage.py' in step.get('run','') and '--run-attempt' in step['run']
               for step in aggregate['steps'])
    source=(ROOT/'scripts/ci/run_windows_postgresql_qualification.py').read_text()
    assert source.index('windows_pg_hosted_only')<source.index('def nsis')
    assert 'windows_pg_existing_installation_refused' in source
    assert 'windows_pg_installer_converted_without_consent' in source
    assert 'interrupted_after_canonical' in source


def test_representative_smoke_cannot_claim_full_predecessor_coverage():
    versions = coverage.readable_predecessors()
    receipt = reports()[0]
    receipt.update(partition="representative", versions=list(coverage.partition_versions(versions, "representative")))
    value = coverage.verify_reports([receipt], versions=versions, source_sha="a" * 40, run_id="123", run_attempt="1", profile="installer-smoke")
    assert value["profile"] == "installer-smoke" and value["covered"] == 2
    with pytest.raises(ValueError, match="partitions_missing"):
        coverage.verify_reports([receipt], versions=versions, source_sha="a" * 40, run_id="123", run_attempt="1")


@pytest.mark.parametrize('fault',('case','recovery','union'))
def test_current_matrix_checker_rejects_missing_pg_execution(tmp_path,monkeypatch,fault):
    monkeypatch.syspath_prepend(str(ROOT/'scripts/ci'))
    from check_windows_installer_supported_upgrade_matrix import validate_matrix
    paths=('.github/workflows/windows-installer.yml','scripts/ci/run_windows_postgresql_qualification.py')
    for relative in paths:
        target=tmp_path/relative;target.parent.mkdir(parents=True,exist_ok=True)
        target.write_text((ROOT/relative).read_text())
    assert validate_matrix(tmp_path)==(41,)
    relative,token={'case':(paths[0],'-Kind upgrade-013'),'recovery':(paths[1],'interrupted_after_canonical'),
                    'union':(paths[0],'windows_postgresql_coverage.py')}[fault]
    target=tmp_path/relative;target.write_text(target.read_text().replace(token,'disabled_fixture'))
    with pytest.raises(ValueError,match='windows_installer_'):validate_matrix(tmp_path)
