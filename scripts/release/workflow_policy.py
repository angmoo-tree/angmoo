"""Specific permissions, dispatch and artifact boundaries for release workflows."""

UPLOAD = "actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a"
GUARD = "github.repository == 'angmoo-tree/angmoo'"
MAIN = GUARD + " && github.ref == 'refs/heads/main'"
QUALIFICATION = "postgresql-docker-qualification.yml"
WORKFLOWS = {"container-candidate.yml", "release-images.yml", "release-publish.yml", QUALIFICATION}
ARTIFACTS = {
    ("container-candidate.yml", "build-validate"): ("candidate-${{ github.sha }}-${{ github.run_attempt }}-${{ matrix.architecture }}", "artifacts/release-candidate/*.oci.tar\nartifacts/release-candidate/candidate-*.json\nartifacts/release-candidate/validation-*/*.json", 14, 0),
    ("container-candidate.yml", "candidate"): ("release-candidate-${{ github.sha }}-${{ github.run_attempt }}", "artifacts/release-candidate/*.oci.tar\nartifacts/release-candidate/candidate.json\nartifacts/release-candidate/validation-*/*.json", 14, 0),
    ("release-images.yml", "publish-ghcr"): ("image-publication-${{ github.sha }}-${{ github.run_attempt }}", "artifacts/image-publication/image-publication.json", 30, None),
    ("release-publish.yml", "verify"): ("release-verify-${{ github.run_id }}-${{ github.run_attempt }}", "artifacts/release-publication/prepared.json\nartifacts/release-publication/release-publication.json", 30, None),
    ("release-publish.yml", "publish"): ("release-publish-${{ github.run_id }}-${{ github.run_attempt }}", "artifacts/release-publication/prepared.json\nartifacts/release-publication/release-publication.json", 30, None),
    (QUALIFICATION, "native-arm64"): ("postgresql-docker-native-arm64-${{ inputs.source }}-${{ github.run_id }}-${{ github.run_attempt }}", "${{ runner.temp }}/angmoo-pg-qualification/records/source.json\n${{ runner.temp }}/angmoo-pg-qualification/records/n6-docker-arm64.json\n${{ runner.temp }}/angmoo-pg-qualification/records/n6-docker-arm64-migrated-search.json", 30, None),
}


def uploads(document, name):
    errors = []
    for job, value in document.get("jobs", {}).items():
        found = [s for s in value.get("steps", []) if str(s.get("uses", "")).startswith("actions/upload-artifact@")]
        if len(found) != 1 or (name, job) not in ARTIFACTS:
            errors.append("release job requires its single bounded artifact export")
            continue
        expected_name, path, days, compression = ARTIFACTS[(name, job)]
        expected = {"name": expected_name, "path": path, "if-no-files-found": "error", "retention-days": days}
        if compression is not None:
            expected["compression-level"] = compression
        options = dict(found[0].get("with", {}))
        options["path"] = str(options.get("path", "")).strip()
        condition = "always()" if name in {"release-images.yml", QUALIFICATION} else None
        if options != expected or found[0].get("uses") != UPLOAD or found[0].get("if") != condition:
            errors.append("release artifact export exceeds its reviewed paths or identity")
    return errors


def validate(document, name):
    if name == QUALIFICATION:
        return validate_qualification(document)
    errors = []
    jobs = document.get("jobs", {})
    events = document.get("on", document.get(True, {}))
    expected_jobs = {"container-candidate.yml": {"build-validate", "candidate"}, "release-images.yml": {"publish-ghcr"}, "release-publish.yml": {"verify", "publish"}}[name]
    if set(jobs) != expected_jobs:
        return ["release workflow job set differs from the reviewed contract"]
    if name == "container-candidate.yml":
        if set(events) != {"workflow_dispatch"} or jobs["build-validate"].get("if") != MAIN or jobs["candidate"].get("needs") != "build-validate":
            errors.append("candidate must be an explicit main-only read-only run")
        if any("permissions" in job for job in jobs.values()):
            errors.append("candidate cannot acquire write permissions")
        matrix = jobs["build-validate"].get("strategy", {}).get("matrix", {}).get("include")
        if matrix != [{"architecture": "amd64", "runner": "ubuntu-24.04"}, {"architecture": "arm64", "runner": "ubuntu-24.04-arm"}]:
            errors.append("candidate requires both native platform runners")
        text = str(document)
        if "scripts.release.validate" not in text or "successful_images" not in text or any(marker in text for marker in ("scripts.release.promote", "scripts.release.publish", "docker/login-action", "push: true")):
            errors.append("candidate must validate and cannot publish")
    elif name == "release-images.yml":
        job = jobs["publish-ghcr"]
        if events != {"push": {"tags": ["release-v*.*.*"]}} or job.get("if") != GUARD:
            errors.append("image publication must use official repository release-v tags only")
        if job.get("permissions") != {"contents": "read", "actions": "read", "packages": "write", "id-token": "write", "attestations": "write"}:
            errors.append("image promotion permissions differ from the minimum contract")
        text = str(document)
        if "scripts.release.promote" not in text or "check_release_tag.py" not in text or "build-push-action" in text or "docker build " in text:
            errors.append("image publication must promote verified bytes without rebuilding")
    else:
        if document.get("defaults") != {"run": {"working-directory": "release-tools"}} or document.get("env", {}).get("RELEASE_PRODUCT_ROOT") != "${{ github.workspace }}/product" or document.get("env", {}).get("RELEASE_OUTPUT") != "${{ github.workspace }}/artifacts/release-publication":
            errors.append("Release tooling and original product checkout must be separate")
        inputs = events.get("workflow_dispatch", {}).get("inputs", {})
        if set(events) != {"workflow_dispatch"} or inputs.get("operation", {}).get("default") != "verify" or inputs.get("operation", {}).get("options") != ["verify", "draft", "publish"]:
            errors.append("Release dispatch must default to verify")
        for key in ("verify", "publish"):
            job = jobs[key]
            if job.get("permissions") != {"contents": "write" if key == "publish" else "read", "actions": "read", "attestations": "read"}:
                errors.append("Release write permissions must be confined to publish")
            guard = MAIN + (" && inputs.operation != 'verify'" if key == "publish" else "")
            if job.get("if") != guard or job.get("env", {}).get("RELEASE_OPERATION") != ("${{ inputs.operation }}" if key == "publish" else "verify"):
                errors.append("Release operation or main guard invalid")
            if not any(s.get("run") == "python -m scripts.release.dispatch" for s in job.get("steps", [])):
                errors.append("Release evidence verifier is missing")
            steps = job.get("steps", [])
            checkouts = [(i, s) for i, s in enumerate(steps) if str(s.get("uses", "")).startswith("actions/checkout@")]
            expected = [{"persist-credentials": False, "ref": "${{ github.sha }}", "path": "release-tools"}, {"persist-credentials": False, "ref": "${{ inputs.source }}", "path": "product"}]
            guards = [i for i, s in enumerate(steps) if s.get("run") == 'python -c "import os; from scripts.release.github import GitHub; GitHub().main_source(os.environ[\'RELEASE_SOURCE\'])"']
            if [s.get("with") for _, s in checkouts] != expected or len(guards) != 1 or not (checkouts[0][0] < guards[0] < checkouts[1][0]):
                errors.append("Release must check main ancestry before selecting the original product checkout")
        if jobs["publish"].get("needs") != "verify":
            errors.append("Release write must follow read-only verification")
    if document.get("concurrency", {}).get("cancel-in-progress") is not False:
        errors.append("release operations must be serialized without cancellation")
    return errors


def validate_qualification(document):
    """Read-only native check of immutable originals, never a publishing lane."""
    errors = []
    events = document.get("on", {})
    fields = ("source", "candidate_run", "candidate_artifact", "windows_run", "windows_attempt", "windows_artifact")
    dispatch = events.get("workflow_dispatch", {}) if isinstance(events, dict) else {}
    inputs = dispatch.get("inputs", {}) if isinstance(dispatch, dict) else {}
    if (not isinstance(events, dict) or set(events) != {"workflow_dispatch"}
            or set(inputs) != set(fields) or any(inputs[key].get("type") != "string"
                or inputs[key].get("required") is not True or "default" in inputs[key] for key in fields if key in inputs)):
        errors.append("native qualification requires explicit immutable-source dispatch inputs")
    jobs = document.get("jobs", {})
    if set(jobs) != {"native-arm64"}:
        return errors + ["native qualification requires its single reviewed job"]
    job = jobs["native-arm64"]
    if (job.get("if") != MAIN or job.get("runs-on") != "ubuntu-24.04-arm"
            or job.get("timeout-minutes") != 40
            or job.get("permissions") != {"contents": "read", "actions": "read"}
            or set(job) != {"if", "runs-on", "timeout-minutes", "permissions", "env", "steps"}):
        errors.append("native qualification must remain main-only, native ARM64 and read-only")
    expected_env = {"GH_TOKEN": "${{ github.token }}", **{
        key: "${{ inputs." + field + " }}" for key, field in zip(
            ("PRODUCT_SOURCE", "CANDIDATE_RUN", "CANDIDATE_ARTIFACT", "WINDOWS_RUN", "WINDOWS_ATTEMPT", "WINDOWS_ARTIFACT"), fields)}}
    if job.get("env") != expected_env:
        errors.append("native qualification environment must bind only the reviewed inputs")
    steps = job.get("steps", [])
    prepare = ('python -m scripts.ci.prepare_docker_postgresql_qualification \\\n'
        '  --source "$PRODUCT_SOURCE" --candidate-run "$CANDIDATE_RUN" --candidate-artifact "$CANDIDATE_ARTIFACT" \\\n'
        '  --windows-run "$WINDOWS_RUN" --windows-attempt "$WINDOWS_ATTEMPT" --windows-artifact "$WINDOWS_ARTIFACT" \\\n'
        '  --work-root "$RUNNER_TEMP/angmoo-pg-qualification"')
    qualify = ('python scripts/ci/qualify_docker_postgresql.py arm64 \\\n'
        '  --inputs "$RUNNER_TEMP/angmoo-pg-qualification/inputs.json" \\\n'
        '  --work-root "$RUNNER_TEMP/angmoo-pg-qualification"')
    if (len(steps) != 5 or steps[0].get("uses") != "actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1"
            or steps[0].get("with") != {"fetch-depth": 0, "persist-credentials": False}
            or set(steps[0]) != {"uses", "with"}
            or steps[1] != {"uses": "docker/setup-buildx-action@bb05f3f5519dd87d3ba754cc423b652a5edd6d2c"}
            or str(steps[2].get("run", "")).strip() != prepare
            or str(steps[3].get("run", "")).strip() != qualify
            or any(set(steps[index]) != {"name", "run"} for index in (2, 3))
            or set(steps[-1]) != {"name", "if", "uses", "with"}):
        errors.append("native qualification must execute only the reviewed source-bound preparation and check")
    if document.get("concurrency") != {"group": "postgresql-docker-qualification-${{ inputs.source }}", "cancel-in-progress": False}:
        errors.append("native qualification must serialize the same source without cancellation")
    return errors
