"""Manual PostgreSQL update checks cannot become a PR or publication lane."""
from scripts.release.workflow_policy import MAIN

NAME = "postgresql-update-qualification.yml"
FIELDS = ("source", "candidate_run", "candidate_attempt", "candidate_artifact")
COMMAND = ('python -m scripts.ci.qualify_postgresql_update \\\n'
    '  --source "$PRODUCT_SOURCE" --candidate-run "$CANDIDATE_RUN" \\\n'
    '  --candidate-attempt "$CANDIDATE_ATTEMPT" --candidate-artifact "$CANDIDATE_ARTIFACT" \\\n'
    '  --architecture "$NATIVE_ARCHITECTURE" --work-root "$RUNNER_TEMP/angmoo-pg-update"')


def validate(document):
    errors = []
    events = document.get("on", document.get(True, {}))
    inputs = events.get("workflow_dispatch", {}).get("inputs", {})
    if set(events) != {"workflow_dispatch"} or set(inputs) != set(FIELDS) or any(
            v.get("type") != "string" or v.get("required") is not True or "default" in v for v in inputs.values()):
        errors.append("PG update requires explicit source-bound manual inputs")
    jobs = document.get("jobs", {})
    if set(jobs) != {"native-update"}:
        return errors + ["PG update job set changed"]
    job = jobs["native-update"]
    matrix = {"fail-fast": False, "matrix": {"include": [
        {"architecture": "amd64", "runner": "ubuntu-24.04"},
        {"architecture": "arm64", "runner": "ubuntu-24.04-arm"}]}}
    if (job.get("if") != MAIN or job.get("runs-on") != "${{ matrix.runner }}"
            or job.get("strategy") != matrix or job.get("timeout-minutes") != 45
            or job.get("permissions") != {"contents": "read", "actions": "read"}
            or set(job) != {"if", "strategy", "runs-on", "timeout-minutes", "permissions", "env", "steps"}):
        errors.append("PG update must use the two read-only native runners")
    expected_env = {"GH_TOKEN": "${{ github.token }}", "NATIVE_ARCHITECTURE": "${{ matrix.architecture }}",
        **{key: "${{ inputs." + value + " }}" for key, value in zip(
            ("PRODUCT_SOURCE", "CANDIDATE_RUN", "CANDIDATE_ATTEMPT", "CANDIDATE_ARTIFACT"), FIELDS)}}
    if job.get("env") != expected_env:
        errors.append("PG update environment is not bound to reviewed inputs")
    steps = job.get("steps", [])
    if (len(steps) != 4 or steps[0] != {"uses": "actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1",
            "with": {"fetch-depth": 0, "persist-credentials": False}}
            or steps[1] != {"uses": "docker/setup-buildx-action@f87e5991a6d7451dcb8d9637bfbc97413f497069"}
            or set(steps[2]) != {"name", "run"} or str(steps[2].get("run", "")).strip() != COMMAND
            or set(steps[-1]) != {"name", "if", "uses", "with"}):
        errors.append("PG update steps exceed the reviewed qualification boundary")
    if document.get("concurrency") != {"group": "postgresql-update-qualification-${{ inputs.source }}", "cancel-in-progress": False}:
        errors.append("PG update must serialize a source without cancellation")
    return errors
