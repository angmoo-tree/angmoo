"""Build once to OCI, then load and verify those exact candidate bytes.

Run from the repository root: python -m scripts.release.candidate --help.
No command in this module writes a registry, Git ref or GitHub Release.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import subprocess
import tarfile
import tempfile
import time

from launcher.termux.payload import (
    PLATFORMS, REPOSITORY, SERVICES, digest_file, inspect_oci, read_manifest,
    require, verify_archive,
)
from scripts.ci.check_release_tag import expected_release_tag

ROOT = Path(__file__).resolve().parents[2]


def run(*args: str, capture: bool = False) -> str:
    result = subprocess.run(args, cwd=ROOT, check=True, text=True, encoding="utf-8", stdout=subprocess.PIPE if capture else None)
    return result.stdout.strip() if capture else ""


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def build(output: Path, service: str, platform: str, builder: str | None) -> Path:
    source = run("git", "rev-parse", "HEAD", capture=True)
    require(not run("git", "status", "--porcelain", "--untracked-files=all", capture=True), "candidate_requires_clean_source")
    tag = expected_release_tag(ROOT)
    version = tag.removeprefix("release-v")
    arch = platform.split("/")[1]
    output.mkdir(parents=True, exist_ok=True)
    archive = output / f"angmoo-{service}-{arch}.oci.tar"
    metadata = output / f"{service}-{arch}.build.json"
    require(not archive.exists(), "candidate_archive_already_exists")
    args = ["docker", "buildx", "build"]
    if builder:
        args += ["--builder", builder]
    args += ["--file", f"Dockerfile.{service}", "--target", "runtime", "--platform", platform,
             "--build-arg", f"VCS_REF={source}", "--build-arg", f"VERSION={version}",
             "--tag", f"angmoo-{service}-candidate:{source}-{arch}",
             "--provenance=mode=max", "--sbom=true", "--metadata-file", str(metadata),
             "--output", f"type=oci,dest={archive},compression=gzip,force-compression=true", "."]
    started = time.monotonic()
    run(*args)
    build_seconds = time.monotonic() - started
    image = inspect_oci(archive, service=service, platform=platform, source=source, version=version)
    image["build_seconds"] = round(build_seconds, 3)
    base = re.search(r"ARG (?:PYTHON|NODE)_IMAGE=(.+)", (ROOT / f"Dockerfile.{service}").read_text())[1]
    base_index = json.loads(run("docker", "buildx", "imagetools", "inspect", "--raw", base, capture=True))
    base_child = next(d for d in base_index["manifests"] if d.get("platform", {}).get("os") == "linux" and d.get("platform", {}).get("architecture") == arch)
    image["base_manifest_digest"] = base_child["digest"]
    image["validation"] = {"runtime": "NOT_RUN", "native": "NOT_RUN", "security": "NOT_RUN"}
    record = {
        "schema": "angmoo-release-candidate.v1", "repository": REPOSITORY,
        "source_sha": source, "source_tree": run("git", "rev-parse", "HEAD^{tree}", capture=True),
        "clean": True, "version": version, "tag": tag,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "producer": {"run_id": os.environ.get("GITHUB_RUN_ID"), "attempt": os.environ.get("GITHUB_RUN_ATTEMPT")},
        "locks": {name: digest_file(ROOT / name) for name in ("backend/uv.lock", "frontend/pnpm-lock.yaml")},
        "bases": {s: re.search(r"ARG (?:PYTHON|NODE)_IMAGE=(.+)", (ROOT / f"Dockerfile.{s}").read_text())[1] for s in SERVICES},
        "tools": {"docker": run("docker", "--version", capture=True), "buildx": run("docker", "buildx", "version", capture=True)},
        "images": [image], "publication": {"state": "NOT_PUBLISHED"},
        "android": "NOT_RUN", "proot": "NOT_RUN",
    }
    result = output / f"{service}-{arch}.candidate.json"
    write_json(result, record)
    return result


def loaded_image(item: dict, ref: str) -> dict:
    config = json.loads(run("docker", "image", "inspect", "--platform", item["platform"], ref, capture=True))[0]
    require(config["RootFS"]["Layers"] == item["diff_ids"], "loaded_rootfs_mismatch")
    require(f"{config['Os']}/{config['Architecture']}" == item["platform"], "loaded_platform_mismatch")
    # Classic Docker uses config digest as Id; containerd uses manifest digest.
    # A format conversion may change the manifest while preserving config.
    if config["Id"] != item["config_digest"] and config.get("Descriptor", {}).get("digest") != item["manifest_digest"]:
        with tempfile.TemporaryDirectory(prefix="angmoo-image-proof-") as directory:
            saved = Path(directory) / "loaded.tar"
            run("docker", "image", "save", "--platform", item["platform"], "--output", str(saved), ref)
            with tarfile.open(saved) as archive:
                from launcher.termux.payload import digest_stream
                records = json.load(archive.extractfile("manifest.json"))
                require(len(records) == 1, "loaded_config_ambiguous")
                with archive.extractfile(records[0]["Config"]) as stream:
                    require(digest_stream(stream) == item["config_digest"], "loaded_config_mismatch")
    return config


def candidate_ref(item: dict) -> str:
    return f"angmoo-{item['service']}-candidate:{item['source_sha']}-{item['platform'].split('/')[1]}"


def load(path: Path) -> None:
    manifest = read_manifest(path, require_all=False)
    for item in manifest["images"]:
        archive = path.parent / item["archive"]
        verify_archive(archive, item)
        ref = candidate_ref(item)
        result = subprocess.run(["docker", "load", "--input", str(archive)], capture_output=True, text=True)
        conversion = False
        if result.returncode:
            # Classic graphdriver engines cannot import an OCI index. Convert
            # only its transport envelope, then prove the actual loaded config.
            require(any(s in result.stderr.lower() for s in ("manifest.json", "unsupported", "invalid tar header")), "oci_import_failed")
            from scripts.release.promote import SKOPEO
            run("docker", "run", "--rm", "--volume", "/var/run/docker.sock:/var/run/docker.sock", "--mount", f"type=bind,source={archive.parent},target=/candidate,readonly", SKOPEO,
                "--override-os", "linux", "--override-arch", item["platform"].split("/")[1], "copy", f"oci-archive:/candidate/{archive.name}", f"docker-daemon:{ref}")
            conversion = True
        config = loaded_image(item, ref)
        write_json(path.parent / f"{item['service']}-{item['platform'].split('/')[1]}.loaded.json", {
            "source_sha": manifest["source_sha"], "archive_digest": item["archive_digest"],
            "config_digest": item["config_digest"], "runtime_image_id": config["Id"], "diff_ids": config["RootFS"]["Layers"], "transport_conversion": conversion,
            "platform": item["platform"], "ref": ref,
        })


def combine(paths: list[Path], output: Path, platform: str | None = None) -> None:
    records = [read_manifest(path, require_all=False) for path in paths]
    require(bool(records), "candidate_inputs_missing")
    result = records[0].copy()
    for record in records:
        require(all(record[k] == result[k] for k in ("source_sha", "source_tree", "version", "tag", "locks", "bases")), "candidate_inputs_differ")
    result["images"] = [item for record in records for item in record["images"]]
    from launcher.termux.payload import validate_manifest
    validate_manifest(result, require_all=platform is None)
    if platform:
        require({(i["service"], i["platform"]) for i in result["images"]} == {(s, platform) for s in SERVICES}, "candidate_pair_missing")
    write_json(output, result)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    build_parser = commands.add_parser("build")
    build_parser.add_argument("--output", type=Path, required=True)
    build_parser.add_argument("--service", choices=SERVICES, required=True)
    build_parser.add_argument("--platform", choices=PLATFORMS, required=True)
    build_parser.add_argument("--builder")
    for command in ("load", "verify"):
        p = commands.add_parser(command)
        p.add_argument("manifest", type=Path)
    p = commands.add_parser("combine")
    p.add_argument("manifests", type=Path, nargs="+")
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--platform", choices=PLATFORMS)
    args = parser.parse_args()
    if args.command == "build":
        print(build(args.output.resolve(), args.service, args.platform, args.builder))
    elif args.command == "load":
        load(args.manifest.resolve())
    elif args.command == "combine":
        combine(args.manifests, args.output, args.platform)
    else:
        manifest = read_manifest(args.manifest, require_all=False)
        for item in manifest["images"]:
            verify_archive(args.manifest.parent / item["archive"], item)


if __name__ == "__main__":
    main()
