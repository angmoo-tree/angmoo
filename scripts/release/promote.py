"""P6 only: copy validated OCI bytes, preserving digests, without rebuilding."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile

from launcher.termux.payload import REPOSITORY, digest_file, read_manifest, require, verify_archive
from scripts.ci.check_release_tag import validate_release_tag
from scripts.release.candidate import write_json
from scripts.release.github import GitHub, successful_images

SKOPEO = "quay.io/skopeo/stable:v1.22.0@sha256:06dd47ee861e143268f0b811cdf1f9d6509b097945de447dbcdfb668ca15364c"


def registry_document(ref: str) -> tuple[str, dict] | None:
    result = subprocess.run(["docker", "buildx", "imagetools", "inspect", "--raw", ref], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if result.returncode:
        error = result.stderr.decode(errors="replace").lower()
        if "manifest unknown" in error or "not found" in error:
            return None
        raise ValueError("registry_inspection_failed")
    raw = result.stdout.rstrip(b"\n")
    return "sha256:" + hashlib.sha256(raw).hexdigest(), json.loads(raw)


def assemble(manifest: dict, service: str, source_dir: Path, target: Path) -> str:
    descriptors = []
    (target / "blobs/sha256").mkdir(parents=True, exist_ok=True)
    for image in [i for i in manifest["images"] if i["service"] == service]:
        path = source_dir / image["archive"]
        verify_archive(path, image)
        with tarfile.open(path) as archive:
            members = {m.name.removeprefix("./"): m for m in archive if m.isfile()}
            def document(name):
                return json.load(archive.extractfile(members[name]))
            def visit(desc):
                doc = document("blobs/sha256/" + desc["digest"][7:])
                if "manifests" in doc:
                    for child in doc["manifests"]:
                        visit(child)
                else:
                    descriptors.append(desc)
            for desc in document("index.json")["manifests"]:
                visit(desc)
            for name, member in members.items():
                if not name.startswith("blobs/sha256/"):
                    continue
                output = target / name
                if not output.exists():
                    with archive.extractfile(member) as incoming, output.open("wb") as outgoing:
                        shutil.copyfileobj(incoming, outgoing)
    document = {"schemaVersion": 2, "mediaType": "application/vnd.oci.image.index.v1+json", "manifests": descriptors}
    raw = json.dumps(document, separators=(",", ":")).encode()
    digest = hashlib.sha256(raw).hexdigest()
    (target / "blobs/sha256" / digest).write_bytes(raw)
    write_json(target / "oci-layout", {"imageLayoutVersion": "1.0.0"})
    write_json(target / "index.json", {"schemaVersion": 2, "manifests": [{"mediaType": document["mediaType"], "digest": "sha256:" + digest, "size": len(raw), "annotations": {"org.opencontainers.image.ref.name": "release"}}]})
    return "sha256:" + digest


def check_index(remote: dict, images: list[dict]) -> None:
    expected = {i["manifest_digest"] for i in images} | {d for i in images for d in i["attestation_manifests"]}
    require({d["digest"] for d in remote.get("manifests", [])} == expected, "published_platform_or_attestation_mismatch")
    require({d.get("platform", {}).get("architecture") for d in remote["manifests"] if d["digest"] in {i["manifest_digest"] for i in images}} == {"amd64", "arm64"}, "published_platform_missing")


def promote(source: str, tag: str, output: Path) -> None:
    require(not validate_release_tag(tag), "official_tag_invalid")
    github = GitHub()
    github.main_source(source)
    require(github.read(f"commits/{tag}")["sha"] == source, "remote_tag_source_mismatch")
    run, artifact = github.select_candidate(source)
    directory = github.download(artifact, output / "candidate")
    manifest = read_manifest(directory / "candidate.json")
    require(manifest["source_sha"] == source and manifest["tag"] == tag, "candidate_source_mismatch")
    successful_images(manifest)
    auth = Path(os.environ.get("DOCKER_CONFIG", str(Path.home() / ".docker"))) / "config.json"
    require(auth.is_file(), "registry_auth_missing")
    receipt = {"source_sha": source, "tag": tag, "candidate_run": run["id"], "candidate_attempt": run["run_attempt"], "candidate_artifact": artifact["id"], "images": {}, "state": "PARTIAL"}
    prepared = {}
    # Check BOTH destinations before any write. Partial upload is still possible;
    # a receipt and immutable hashes make its resumption explicit.
    for service in ("backend", "frontend"):
        layout = output / ("oci-" + service)
        digest = assemble(manifest, service, directory, layout)
        repository = f"ghcr.io/{REPOSITORY}-{service}"
        for alias in (tag, "sha-" + source):
            existing = registry_document(repository + ":" + alias)
            require(existing is None or existing[0] == digest, "existing_image_tag_conflicts")
        prepared[service] = (layout, digest, repository)
    for service, (layout, digest, repository) in prepared.items():
        for alias in (tag, "sha-" + source):
            ref = repository + ":" + alias
            existing = registry_document(ref)
            if existing is None:
                subprocess.run(["docker", "run", "--rm", "--mount", f"type=bind,source={layout.resolve()},target=/payload,readonly", "--mount", f"type=bind,source={auth.resolve()},target=/auth/config.json,readonly", SKOPEO, "copy", "--all", "--preserve-digests", "--authfile", "/auth/config.json", "oci:/payload:release", "docker://" + ref], check=True)
            actual = registry_document(ref)
            require(actual is not None and actual[0] == digest, "published_index_digest_mismatch")
            check_index(actual[1], [i for i in manifest["images"] if i["service"] == service])
        receipt["images"][service] = {"repository": repository, "digest": digest}
        write_json(output / "image-publication.json", receipt)
    receipt["state"] = "PUBLISHED"
    write_json(output / "image-publication.json", receipt)
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as stream:
            for service, (_, digest, _) in prepared.items():
                stream.write(f"{service}_digest={digest}\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    promote(args.source, args.tag, args.output.resolve())
