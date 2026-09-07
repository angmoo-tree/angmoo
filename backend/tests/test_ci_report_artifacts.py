"""Test evidence may not broaden CI artifact access to unrelated files."""
from copy import deepcopy

import pytest
import yaml

from test_t2_ci_policy import checker


def report(job):
    prefix = "backend" if job == "backend" else "browser"
    return {
        "name": "Preserve test reports",
        "if": "always()",
        "uses": "actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a",
        "with": {
            "name": prefix + "-tests-${{ github.sha }}-${{ github.run_attempt }}",
            "path": "\n".join(checker.CORE_TEST_REPORT_PATHS[job]),
            "include-hidden-files": True,
            "if-no-files-found": "error",
        },
    }


def errors(step, *, job="backend", workflow="ci.yml"):
    document = {"jobs": {job: {"steps": [step]}}}
    return checker.check_report_uploads(document, workflow, yaml.safe_dump(document))


@pytest.mark.parametrize("job", ["backend", "frontend"])
def test_exact_synthetic_test_report_files_are_allowed(job):
    assert errors(report(job), job=job) == []


@pytest.mark.parametrize("path", [
    "backend/**", "backend/.ci", "backend/.env", "../private",
    "${{ github.workspace }}", "browser-tests/.ci/*.xml",
    "backend/.ci/backend-junit.xml\nbackend/.ci/extra.json",
])
def test_artifact_paths_cannot_expand_or_become_dynamic(path):
    step = report("backend")
    step["with"]["path"] = path
    assert errors(step)


@pytest.mark.parametrize("mutation", ["action", "ignore_missing", "extra_option", "condition", "job", "workflow", "duplicate"])
def test_report_exception_keeps_action_job_and_failure_limits(mutation):
    step = deepcopy(report("backend"))
    job, workflow = "backend", "ci.yml"
    if mutation == "action":
        step["uses"] = "actions/upload-artifact@v7"
    elif mutation == "ignore_missing":
        step["with"]["if-no-files-found"] = "ignore"
    elif mutation == "extra_option":
        step["with"]["overwrite"] = True
    elif mutation == "condition":
        step["if"] = "success()"
    elif mutation == "job":
        job = "other"
    elif mutation == "workflow":
        workflow = "local-smoke.yml"
    else:
        document = {"jobs": {job: {"steps": [step, deepcopy(step)]}}}
        assert checker.check_report_uploads(document, workflow, yaml.safe_dump(document))
        return
    assert errors(step, job=job, workflow=workflow)
