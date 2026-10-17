"""Validate imported candidate identities, native code and the service pair."""

import argparse
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import uuid

from launcher.termux.payload import digest_file, read_manifest, require, verify_archive
from scripts.ci.check_container_images import _history, validate_history, validate_image_document
from scripts.release.candidate import ROOT, write_json, loaded_image, candidate_ref
from scripts.release.scan import scan


def validate(manifest_path: Path, architecture: str) -> None:
    manifest = read_manifest(manifest_path, require_all=False)
    pair = [i for i in manifest["images"] if i["platform"] == "linux/" + architecture]
    require({i["service"] for i in pair} == {"backend", "frontend"}, "candidate_pair_missing")
    output = manifest_path.parent / f"validation-{architecture}"
    output.mkdir(parents=True, exist_ok=True)
    refs = []
    tag = "candidate-" + manifest["source_sha"] + "-" + architecture
    for item in pair:
        verify_archive(manifest_path.parent / item["archive"], item)
        imported = candidate_ref(item)
        document = loaded_image(item, imported)
        item["uncompressed_size"] = document["Size"]
        require(document["RootFS"]["Layers"] == item["diff_ids"], "runtime_rootfs_mismatch")
        errors = validate_image_document(document, image=item["repository"], expected_revision=manifest["source_sha"], expected_version=manifest["version"], expected_architecture=architecture)
        errors += validate_history(item["repository"], _history(imported))
        require(not errors, "runtime_metadata_invalid: " + "; ".join(errors))
        ref = f"angmoo-{item['service']}-ci:{tag}"
        subprocess.run(["docker", "tag", imported, ref], check=True)
        refs.append(ref)
        if item["service"] == "backend":
            args = ["--mount", f"type=bind,source={ROOT / 'scripts/release/native_smoke.py'},target=/tmp/native_smoke.py,readonly", "--env", "PYTHONPATH=/app", "--entrypoint", "python", ref, "/tmp/native_smoke.py"]
        else:
            args = ["--workdir", "/app/app", "--entrypoint", "node", ref, "-e", "const s=require(require.resolve('sharp',{paths:[require.resolve('next/package.json')]})); s({create:{width:2,height:2,channels:3,background:'red'}}).png().toBuffer().then(b=>{if(!b.length)process.exit(1);console.log(JSON.stringify({status:'PASS',architecture:process.arch,sharp:s.versions.sharp,node:process.version}))})"]
        result = subprocess.run(["docker", "run", "--rm", "--platform", item["platform"], "--network", "none", *args], check=True, text=True, stdout=subprocess.PIPE)
        report = output / f"{item['service']}-native.json"
        report.write_text(result.stdout, encoding="utf-8")
        item["validation"]["native"] = "PASS"
        item["native_report"] = {"name": f"validation-{architecture}/{report.name}", "sha256": digest_file(report)}
    scan(refs, output)
    by_service = {item["service"]: candidate_ref(item) for item in pair}
    from scripts.release.feature_smoke import run as feature_smoke
    from scripts.release.upstream_smoke import run as upstream_smoke
    feature_smoke(by_service["backend"], "linux/" + architecture, output)
    upstream_smoke(by_service["frontend"], by_service["backend"], "linux/" + architecture, output)
    env = {**os.environ, "ANGMOO_CI_PLATFORM": "linux/" + architecture, "ANGMOO_VERSION": manifest["version"]}
    project = "angmoo-candidate-" + uuid.uuid4().hex[:12]
    subprocess.run([sys.executable, "scripts/ci/run_l0_container_smoke.py", "--tag", tag, "--project", project, "--report", str(output / "runtime.json")], cwd=ROOT, env=env, check=True)
    for number, item in enumerate(pair):
        item["validation"].update(runtime="PASS", security="PASS")
        item["environment"] = {"host": platform.machine(), "target": architecture, "android": "NOT_RUN"}
        item["security_report"] = {"name": f"validation-{architecture}/image-{number}.security.json", "sha256": digest_file(output / f"image-{number}.security.json")}
        item["sbom"] = {"name": f"validation-{architecture}/image-{number}.spdx.json", "sha256": digest_file(output / f"image-{number}.spdx.json")}
    write_json(manifest_path, manifest)
    print(f"Candidate validation PASS: {architecture} source={manifest['source_sha']}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--architecture", choices=("amd64", "arm64"), required=True)
    args = parser.parse_args()
    validate(args.manifest.resolve(), args.architecture)
