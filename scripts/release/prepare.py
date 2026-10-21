"""Read-only remote verification and a bounded, hash-addressed Release staging set."""

import base64
import json
from pathlib import Path
import shutil
import subprocess
import zipfile

from launcher.termux.payload import REPOSITORY, SOURCE, VERSION, digest_file, read_manifest, require
from scripts.ci.check_release_tag import validate_release_tag
from scripts.release.candidate import ROOT, write_json
from scripts.release.github import GitHub, successful_images
from scripts.release.promote import check_index, registry_document
from scripts.release.windows_receipt import tested_installer

WINDOWS_FILES = ("SHA256SUMS", "angmoo-installer.spdx.json", "angmoo-installer.provenance.json", "THIRD_PARTY_NOTICES.md", "LICENSE")


def package_termux_tools(target: Path, root: Path = ROOT) -> None:
    """Stable bytes across reruns/checkouts, so draft recovery can compare hashes."""
    tools = ("angmoo.py", "payload.py", "processes.py", "service_logs.py", "log_policy.py", "requirements.txt", "setup.sh")
    files = [(name, root / "launcher/termux" / name) for name in tools]
    files.append(("LICENSE", root / "LICENSE"))
    with zipfile.ZipFile(target, "w") as archive:
        for name, path in files:
            entry = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            entry.create_system = 3
            entry.external_attr = (0o100755 if name == "setup.sh" else 0o100644) << 16
            entry.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(entry, path.read_bytes(), compresslevel=9)


def package_termux_installer(target: Path, tools: Path, version: str, root: Path = ROOT) -> None:
    """Bind the first-install entry point to this release's exact adapter ZIP."""
    require(VERSION.fullmatch(version), "termux_installer_version_invalid")
    source = (root / "launcher/termux/bootstrap.py").read_text(encoding="utf-8")
    for marker, value in (("@ANGMOO_RELEASE@", version),
                          ("@ANGMOO_TOOLS_SHA256@", digest_file(tools)[7:]),
                          ("@ANGMOO_TOOLS_SIZE@", str(tools.stat().st_size))):
        require(source.count(marker) == 1, "termux_installer_template_invalid")
        source = source.replace(marker, value)
    target.write_bytes(source.encode("utf-8"))


def unique(root: Path, name: str) -> Path:
    files = list(root.rglob(name))
    require(len(files) == 1 and not files[0].is_symlink(), "release_file_missing_or_ambiguous: " + name)
    return files[0]


def reviewed_file(github, revision: str, path: str) -> bytes:
    github.main_source(revision)
    value = github.read(f"contents/{path}?ref={revision}")
    require(value.get("type") == "file" and value.get("encoding") == "base64" and value.get("size", 0) <= 1024 * 1024, "reviewed_file_invalid")
    return base64.b64decode(value["content"], validate=False)


def validate_p5(github, report: dict, manifest: dict, windows: dict):
    require(report.get("schema") == "angmoo-p5.v1" and report.get("source_sha") == manifest["source_sha"], "p5_source_mismatch")
    require(report.get("windows") == {"sha256": windows["exe"]["sha256"], "run_id": windows["run_id"], "attempt": windows["attempt"]}, "p5_windows_mismatch")
    expected = {i["service"] + "/" + i["platform"]: i["manifest_digest"] for i in manifest["images"]}
    require(report.get("images") == expected, "p5_images_mismatch")
    checks = report.get("checks", [])
    require({c.get("workflow") for c in checks} == {"ci.yml", "local-smoke.yml", "security.yml"} and len(checks) == 3, "p5_ci_evidence_missing")
    for check in checks:
        github.run(str(check["run_id"]), str(check["attempt"]), workflow=check["workflow"], source=manifest["source_sha"])
    user = report.get("windows_user_check", {})
    require(user.get("result") == "PASS" and user.get("reviewer") == "jingujeon" and user.get("exe_sha256") == windows["exe"]["sha256"] and isinstance(user.get("evidence"), str) and len(user["evidence"]) >= 20 and user.get("checked_at"), "p5_user_evidence_missing")
    require(report.get("android_support") == "experimental-not-certified", "p5_android_support_unverified")


def prepare(*, source: str, tag: str, windows_run: str, windows_attempt: str, windows_artifact: str,
            candidate_run: str, candidate_attempt: str, candidate_artifact: str,
            review_ref: str | None, output: Path, github=None) -> dict:
    github = github or GitHub()
    require(SOURCE.fullmatch(source) and not validate_release_tag(tag), "release_identity_invalid")
    github.main_source(source)
    work = output / "evidence"
    stage = output / "assets"
    require(not stage.exists() or not any(stage.iterdir()), "release_staging_not_empty")
    stage.mkdir(parents=True, exist_ok=True)
    crun = github.run(candidate_run, candidate_attempt, workflow="container-candidate.yml", source=source)
    cart = github.artifact(candidate_artifact, crun, name=f"release-candidate-{source}-{candidate_attempt}")
    candidate_dir = github.download(cart, work / "candidate")
    manifest = read_manifest(candidate_dir / "candidate.json")
    require(manifest["source_sha"] == source and manifest["tag"] == tag, "release_candidate_mismatch")
    successful_images(manifest)
    # Artifact digest authenticates the entire archive. Per-file receipts bind
    # the reports that the producer used; no artifact code is executed here.
    for image in manifest["images"]:
        for field in ("sbom", "security_report"):
            report = image[field]
            file = candidate_dir / report["name"]
            require(file.resolve().is_relative_to(candidate_dir.resolve()) and digest_file(file) == report["sha256"], "candidate_report_hash_mismatch")
    wrun = github.run(windows_run, windows_attempt, workflow="windows-installer.yml", source=source)
    wart = github.artifact(windows_artifact, wrun, name=f"angmoo-windows-installer-{source}-{windows_attempt}")
    windows_dir = github.download(wart, work / "windows")
    validation_art = github.named_artifact(wrun, f"windows-release-validation-{source}-{windows_attempt}")
    validation_dir = github.download(validation_art, work / "windows-validation")
    validation = json.loads(unique(validation_dir, "windows-release-validation.json").read_text())
    exe = tested_installer(windows_dir)
    require(validation.get("schema") == "angmoo-windows-release-validation.v1" and validation.get("status") == "PASS" and validation.get("profile") == "full" and validation.get("exe") == exe, "windows_full_validation_missing")
    require((validation.get("source_sha"), str(validation.get("run_id")), str(validation.get("attempt")), str(validation.get("artifact_id"))) == (source, windows_run, windows_attempt, windows_artifact), "windows_validation_identity_mismatch")
    require(exe["name"] == f"Angmoo_{manifest['version']}_x64-setup.exe", "release_installer_name_invalid")
    provenance = json.loads(unique(windows_dir, "angmoo-installer.provenance.json").read_text())
    definition = provenance["predicate"]["buildDefinition"]
    require(definition["externalParameters"] == {"version": manifest["version"], "commit": source} and definition["internalParameters"].get("sourceWorktreeDirty") is False, "windows_provenance_mismatch")
    require(provenance["subject"] == [{"name": exe["name"], "digest": {"sha256": exe["sha256"][7:]}}], "windows_provenance_subject_mismatch")
    spdx = json.loads(unique(windows_dir, "angmoo-installer.spdx.json").read_text())
    require(any(f.get("fileName") == exe["name"] and {"algorithm": "SHA256", "checksumValue": exe["sha256"][7:]} in f.get("checksums", []) for f in spdx.get("files", [])), "windows_sbom_subject_mismatch")
    signed_art = github.named_artifact(wrun, f"windows-attestation-{source}-{windows_attempt}")
    signed = github.download(signed_art, work / "signed")
    bundle_files = [p for p in signed.rglob("*") if p.is_file()]
    require(len(bundle_files) == 1, "windows_attestation_ambiguous")
    subprocess.run(["gh", "attestation", "verify", str(unique(windows_dir, exe["name"])), "--bundle", str(bundle_files[0]), "--repo", REPOSITORY, "--signer-workflow", f"{REPOSITORY}/.github/workflows/windows-installer.yml", "--source-digest", source, "--deny-self-hosted-runners"], check=True)
    for name in (*WINDOWS_FILES, exe["name"]):
        shutil.copyfile(unique(windows_dir, name), stage / name)
    shutil.copyfile(bundle_files[0], stage / "windows-installer.attestation.jsonl")
    # Package only the reviewed adapter, not arbitrary artifact scripts or data.
    package_termux_tools(stage / "angmoo-termux-tools.zip")
    package_termux_installer(stage / "install-termux.py", stage / "angmoo-termux-tools.zip", manifest["version"])
    for locale in ("en", "ko"):
        shutil.copyfile(ROOT / f"docs/public/termux.{locale}.md", stage / f"termux.{locale}.md")
    publication = {"candidate_validation": "PASS", "p5": "NOT_RUN", "tag": "NOT_READY", "images": "NOT_READY"}
    notes = ""
    if review_ref:
        require(SOURCE.fullmatch(review_ref), "review_ref_invalid")
        prefix = f"docs/releases/{manifest['version']}"
        raw = reviewed_file(github, review_ref, prefix + "/p5.json")
        validate_p5(github, json.loads(raw), manifest, validation)
        manifest["p5"] = {"review_ref": review_ref, "report_sha256": "sha256:" + __import__("hashlib").sha256(raw).hexdigest(), "evidence": json.loads(raw)}
        publication["p5"] = "PASS"
        for locale in ("ko", "en"):
            body = reviewed_file(github, review_ref, prefix + f"/notes.{locale}.md")
            require(len(body) > 40 and b"TODO" not in body and b"NOT_RELEASED" not in body, "release_notes_not_ready")
            (stage / f"release-notes.{locale}.md").write_bytes(body)
            notes += body.decode("utf-8") + "\n\n"
    try:
        remote_source = github.read(f"commits/{tag}")["sha"]
    except subprocess.CalledProcessError:
        remote_source = None
    require(remote_source in (None, source), "release_tag_conflict")
    if remote_source == source:
        publication["tag"] = "READY"
    indexes = {}
    for service in ("backend", "frontend"):
        remote = registry_document(f"ghcr.io/{REPOSITORY}-{service}:{tag}")
        if remote:
            check_index(remote[1], [i for i in manifest["images"] if i["service"] == service])
            indexes[service] = remote[0]
    if len(indexes) == 2:
        publication["images"] = "READY"
    manifest.update(windows=validation, candidate_producer={"run_id": candidate_run, "attempt": candidate_attempt, "artifact_id": candidate_artifact}, windows_producer={"run_id": windows_run, "attempt": windows_attempt, "artifact_id": windows_artifact}, indexes=indexes)
    manifest["assets"] = [{"name": p.name, "size": p.stat().st_size, "sha256": digest_file(p)} for p in sorted(stage.iterdir())]
    write_json(stage / "release-manifest.json", manifest)
    (stage / "RELEASE-SHA256SUMS").write_text("".join(f"{digest_file(p)[7:]}  {p.name}\n" for p in sorted(stage.iterdir())), encoding="ascii")
    ready = all(publication.get(k) == v for k, v in (("p5", "PASS"), ("tag", "READY"), ("images", "READY")))
    result = {"source_sha": source, "tag": tag, "name": f"Angmoo {manifest['version']}", "notes": notes, "publication_ready": ready, "validation": publication, "assets": [{"name": p.name, "size": p.stat().st_size, "sha256": digest_file(p)} for p in sorted(stage.iterdir())]}
    write_json(output / "prepared.json", result)
    return result
