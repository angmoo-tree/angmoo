"""Specific permissions, dispatch and artifact boundaries for release workflows."""

UPLOAD = "actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a"
GUARD = "github.repository == 'angmoo-tree/angmoo'"
MAIN = GUARD + " && github.ref == 'refs/heads/main'"
WORKFLOWS = {"container-candidate.yml", "release-images.yml", "release-publish.yml"}
ARTIFACTS = {
    ("container-candidate.yml", "build-validate"): ("candidate-${{ github.sha }}-${{ github.run_attempt }}-${{ matrix.architecture }}", "artifacts/release-candidate/*.oci.tar\nartifacts/release-candidate/candidate-*.json\nartifacts/release-candidate/validation-*/*.json", 14, 0),
    ("container-candidate.yml", "candidate"): ("release-candidate-${{ github.sha }}-${{ github.run_attempt }}", "artifacts/release-candidate/*.oci.tar\nartifacts/release-candidate/candidate.json\nartifacts/release-candidate/validation-*/*.json", 14, 0),
    ("release-images.yml", "publish-ghcr"): ("image-publication-${{ github.sha }}-${{ github.run_attempt }}", "artifacts/image-publication/image-publication.json", 30, None),
    ("release-publish.yml", "verify"): ("release-verify-${{ github.run_id }}-${{ github.run_attempt }}", "artifacts/release-publication/prepared.json\nartifacts/release-publication/release-publication.json", 30, None),
    ("release-publish.yml", "publish"): ("release-publish-${{ github.run_id }}-${{ github.run_attempt }}", "artifacts/release-publication/prepared.json\nartifacts/release-publication/release-publication.json", 30, None),
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
        condition = "always()" if name == "release-images.yml" else None
        if options != expected or found[0].get("uses") != UPLOAD or found[0].get("if") != condition:
            errors.append("release artifact export exceeds its reviewed paths or identity")
    return errors


def validate(document, name):
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
        if jobs["publish"].get("needs") != "verify":
            errors.append("Release write must follow read-only verification")
    if document.get("concurrency", {}).get("cancel-in-progress") is not False:
        errors.append("release operations must be serialized without cancellation")
    return errors
