"""An aggregate PASS must prove all normal pytest phases of the complete corpus."""
from copy import deepcopy
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest
from test_t2_ci_policy import checker as ci_policy

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("backend_shard_proof", ROOT / "scripts/ci/backend_shard_contract.py")
contract = importlib.util.module_from_spec(spec)
spec.loader.exec_module(contract)
IDENTITY = {"source_sha": "1" * 40, "checkout_sha": "2" * 40, "checkout_tree": "3" * 40,
            "python": "3.13.15", "lock_sha256": "4" * 64}


def actual_partition(tmp_path, index, source):
    work = tmp_path / str(index)
    work.mkdir()
    (work / "test_corpus.py").write_text(source, encoding="utf-8")
    program = work / "probe.py"
    program.write_text(
        "import json, pathlib, sys, pytest\n"
        f"sys.path.insert(0, {str(ROOT / 'scripts/ci')!r})\n"
        "from backend_shard_contract import ExecutionCoverage\n"
        f"coverage=ExecutionCoverage({index}, pathlib.Path('events.jsonl'))\n"
        "code=int(pytest.main(['-q', 'test_corpus.py'], plugins=[coverage]))\n"
        f"pathlib.Path('report.json').write_text(json.dumps(coverage.report({IDENTITY!r}, code)))\n"
        "sys.exit(code)\n", encoding="utf-8")
    env = os.environ.copy()
    env.pop("PYTEST_ADDOPTS", None)
    env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    result = subprocess.run([sys.executable, str(program)], cwd=work, env=env,
        capture_output=True, text=True, timeout=40)
    return result, json.loads((work / "report.json").read_text()), work


@pytest.fixture(scope="module")
def completed_partitions(tmp_path_factory):
    root = tmp_path_factory.mktemp("complete_backend_partitions")
    corpus = "\n\n".join(f"def test_case_{index}():\n    assert {index} >= 0" for index in range(80))
    reports = []
    for index in range(contract.SHARD_COUNT):
        result, report, work = actual_partition(root, index, corpus)
        assert result.returncode == 0, result.stdout + result.stderr
        events = [json.loads(line) for line in (work / "events.jsonl").read_text().splitlines()]
        assert {event["node"] for event in events} == set(report["selected_nodes"])
        assert len(events) == 3 * len(report["selected_nodes"])
        reports.append(report)
    return reports


def test_four_real_pytest_sessions_cover_each_original_case_exactly_once(completed_partitions):
    result = contract.verify_reports(completed_partitions,
        source_sha=IDENTITY["source_sha"], checkout_sha=IDENTITY["checkout_sha"])
    assert result["collected"] == result["covered"] == result["passed"] == 80
    assert result["skipped"] == 0
    assert result["shards"] == 4
    assert all(report["selected_nodes"] for report in completed_partitions)


@pytest.mark.parametrize("mutation", ["missing_shard", "duplicate_shard", "wrong_source",
    "changed_collection", "missing_result", "unexecuted", "teardown_failure", "wrong_selection"])
def test_missing_failed_or_unexecuted_coverage_cannot_become_aggregate_success(completed_partitions, mutation):
    reports = deepcopy(completed_partitions)
    node = reports[0]["selected_nodes"][0]
    if mutation == "missing_shard": reports.pop()
    elif mutation == "duplicate_shard": reports[-1] = deepcopy(reports[0])
    elif mutation == "wrong_source": reports[0]["identity"]["source_sha"] = "5" * 40
    elif mutation == "changed_collection": reports[0]["all_nodes"].pop()
    elif mutation == "missing_result": del reports[0]["results"][node]
    elif mutation == "unexecuted": reports[0]["results"][node]["phases"].pop("call")
    elif mutation == "teardown_failure": reports[0]["results"][node]["phases"]["teardown"] = "failed"
    elif mutation == "wrong_selection": reports[0]["selected_nodes"].append(reports[1]["selected_nodes"][0])
    with pytest.raises(ValueError):
        contract.verify_reports(reports, source_sha=IDENTITY["source_sha"], checkout_sha=IDENTITY["checkout_sha"])


def test_real_fixture_teardown_failure_is_failed_even_when_the_call_passes(tmp_path):
    source = "import pytest\n@pytest.fixture\ndef broken():\n    yield\n    raise RuntimeError('synthetic teardown failure')\ndef test_call(broken):\n    assert True\n"
    index = contract.shard_for("test_corpus.py::test_call")
    result, report, _ = actual_partition(tmp_path, index, source)
    assert result.returncode == 1
    assert report["results"]["test_corpus.py::test_call"]["phases"]["call"] == "passed"
    assert report["results"]["test_corpus.py::test_call"]["outcome"] == "failed"


def test_real_fixture_setup_skip_is_recorded_without_inventing_a_call(tmp_path):
    source = "import pytest\n@pytest.fixture\ndef optional():\n    pytest.skip('existing optional fixture')\ndef test_call(optional):\n    raise AssertionError('must not run')\n"
    index = contract.shard_for("test_corpus.py::test_call")
    result, report, _ = actual_partition(tmp_path, index, source)
    assert result.returncode == 0
    value = report["results"]["test_corpus.py::test_call"]
    assert "call" not in value["phases"]
    assert value["outcome"] == "skipped"


@pytest.mark.parametrize("damage", ["missing_dependency", "missing_partition", "fail_fast",
    "filtering", "missing_baseline", "aggregate_without_coverage"])
def test_ci_policy_rejects_incomplete_partition_wiring(damage):
    document = ci_policy.yaml.load((ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8"), Loader=ci_policy._UniqueKeyLoader)
    jobs = document["jobs"]
    assert ci_policy.check_backend_partitions(jobs) == []
    if damage == "missing_dependency": jobs["backend"]["needs"] = ["backend-tests"]
    elif damage == "missing_partition": jobs["backend-tests"]["strategy"]["matrix"]["shard"].pop()
    elif damage == "fail_fast": jobs["backend-tests"]["strategy"]["fail-fast"] = True
    elif damage == "filtering":
        step = next(step for step in jobs["backend-tests"]["steps"] if "run_backend_shard.py" in str(step.get("run")))
        step["run"] += " --ignore tests/migrations"
    elif damage == "missing_baseline":
        jobs["backend-preflight"]["steps"] = [step for step in jobs["backend-preflight"]["steps"] if "check_test_node_baseline.py" not in str(step.get("run"))]
    else:
        step = next(step for step in jobs["backend"]["steps"] if "check_backend_shards.py" in str(step.get("run")))
        step["run"] = "echo success"
    assert ci_policy.check_backend_partitions(jobs)
