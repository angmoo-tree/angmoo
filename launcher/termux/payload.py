"""Dependency-free verification shared by candidate tooling and the host launcher.

OCI archives are inspected without extracting them. The installer delegates
whiteouts and rootfs materialization to the pinned PRoot-Distro implementation.
"""

from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import re
import tarfile

REPOSITORY = "angmoo-tree/angmoo"
SERVICES = ("backend", "frontend")
PLATFORMS = ("linux/amd64", "linux/arm64")
SHA = re.compile(r"[0-9a-f]{64}")
SOURCE = re.compile(r"[0-9a-f]{40}")
VERSION = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+")


def require(condition: object, code: str) -> None:
    if not condition:
        raise ValueError(code)


def digest_file(path: Path) -> str:
    with path.open("rb") as stream:
        return digest_stream(stream)


def digest_stream(stream) -> str:
    digest = hashlib.sha256()
    for chunk in iter(lambda: stream.read(1024 * 1024), b""):
        digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def valid_digest(value: object) -> bool:
    return isinstance(value, str) and value.startswith("sha256:") and SHA.fullmatch(value[7:]) is not None


def read_manifest(path: Path, *, require_all: bool = True) -> dict:
    require(path.stat().st_size <= 4 * 1024 * 1024, "manifest_too_large")
    value = json.loads(path.read_text(encoding="utf-8"))
    validate_manifest(value, require_all=require_all)
    return value


def validate_manifest(value: dict, *, require_all: bool = True) -> None:
    require(isinstance(value, dict) and value.get("schema") == "angmoo-release-candidate.v1", "manifest_schema_invalid")
    require(value.get("repository") == REPOSITORY, "manifest_repository_invalid")
    require(SOURCE.fullmatch(str(value.get("source_sha", ""))), "manifest_source_invalid")
    require(SOURCE.fullmatch(str(value.get("source_tree", ""))) and value.get("clean") is True, "manifest_tree_invalid")
    require(VERSION.fullmatch(str(value.get("version", ""))), "manifest_version_invalid")
    require(value.get("tag") == "release-v" + value["version"], "manifest_tag_invalid")
    images = value.get("images")
    require(isinstance(images, list) and images, "manifest_images_missing")
    seen = set()
    for item in images:
        require(isinstance(item, dict), "manifest_image_invalid")
        key = (item.get("service"), item.get("platform"))
        require(key[0] in SERVICES and key[1] in PLATFORMS and key not in seen, "manifest_platform_invalid")
        seen.add(key)
        require(item.get("source_sha") == value["source_sha"] and item.get("version") == value["version"], "manifest_pair_mismatch")
        require(item.get("repository") == f"ghcr.io/{REPOSITORY}-{key[0]}", "manifest_image_repository_invalid")
        for field in ("manifest_digest", "config_digest", "archive_digest"):
            require(valid_digest(item.get(field)), f"manifest_{field}_invalid")
        require(isinstance(item.get("layers"), list) and item["layers"] and all(valid_digest(d) for d in item["layers"]), "manifest_layers_invalid")
        require(isinstance(item.get("diff_ids"), list) and len(item["diff_ids"]) == len(item["layers"]) and all(valid_digest(d) for d in item["diff_ids"]), "manifest_diff_ids_invalid")
        require(isinstance(item.get("attestation_manifests"), list) and item["attestation_manifests"] and all(valid_digest(d) for d in item["attestation_manifests"]), "manifest_attestations_invalid")
        name = item.get("archive", "")
        require(isinstance(name, str) and re.fullmatch(r"[a-zA-Z0-9_.-]+\.oci\.tar", name), "manifest_archive_path_invalid")
        require(type(item.get("archive_size")) is int and item["archive_size"] > 0, "manifest_archive_size_invalid")
    if require_all:
        require(seen == {(s, p) for s in SERVICES for p in PLATFORMS}, "manifest_platform_missing")


def inspect_oci(path: Path, *, service: str, platform: str, source: str, version: str) -> dict:
    require(service in SERVICES and platform in PLATFORMS, "oci_target_invalid")
    with tarfile.open(path, "r:*") as archive:
        members = {}
        for member in archive:
            name = member.name.removeprefix("./").rstrip("/")
            require(not PurePosixPath(name).is_absolute() and ".." not in PurePosixPath(name).parts, "oci_path_invalid")
            require(member.isfile() or member.isdir(), "oci_entry_invalid")
            require(name not in members, "oci_duplicate_entry")
            if member.isfile():
                require(name in ("oci-layout", "index.json") or re.fullmatch(r"blobs/sha256/[0-9a-f]{64}", name), "oci_unexpected_file")
                members[name] = member

        def raw(name: str, limit: int = 8 * 1024 * 1024) -> bytes:
            require(name in members and members[name].size <= limit, "oci_metadata_missing_or_large")
            with archive.extractfile(members[name]) as stream:
                return stream.read()

        def descriptor(desc: dict, *, parse: bool = False):
            require(valid_digest(desc.get("digest")), "oci_digest_invalid")
            name = "blobs/sha256/" + desc["digest"][7:]
            require(name in members and members[name].size == desc.get("size"), "oci_blob_size_mismatch")
            if name not in checked:
                with archive.extractfile(members[name]) as stream:
                    require(digest_stream(stream) == desc["digest"], "oci_blob_hash_mismatch")
                checked.add(name)
            return json.loads(raw(name)) if parse else None

        require(json.loads(raw("oci-layout")) == {"imageLayoutVersion": "1.0.0"}, "oci_layout_invalid")
        checked: set[str] = set()
        index = json.loads(raw("index.json"))
        found = []
        attestations = []
        attestation_subjects = set()
        predicates = set()

        def walk(desc: dict, depth: int = 0):
            require(depth < 5, "oci_index_depth_invalid")
            doc = descriptor(desc, parse=True)
            if "manifests" in doc:
                for child in doc["manifests"]:
                    walk(child, depth + 1)
                return
            config = descriptor(doc["config"], parse=True)
            for layer in doc["layers"]:
                descriptor(layer)
            if desc.get("annotations", {}).get("vnd.docker.reference.type") == "attestation-manifest":
                subject = desc.get("annotations", {}).get("vnd.docker.reference.digest")
                require(valid_digest(subject), "oci_attestation_subject_invalid")
                attestation_subjects.add(subject)
                for layer in doc["layers"]:
                    statement = descriptor(layer, parse=True)
                    require(any(s.get("digest", {}).get("sha256") == subject[7:] for s in statement.get("subject", [])), "oci_attestation_subject_mismatch")
                    predicates.add(statement.get("predicateType"))
                attestations.append(desc["digest"])
                return
            require(f"{config.get('os')}/{config.get('architecture')}" == platform, "oci_architecture_mismatch")
            labels = config.get("config", {}).get("Labels", {})
            require(labels.get("org.opencontainers.image.revision") == source, "oci_source_mismatch")
            require(labels.get("org.opencontainers.image.version") == version, "oci_version_mismatch")
            require(labels.get("org.opencontainers.image.source") == f"https://github.com/{REPOSITORY}", "oci_repository_mismatch")
            user = config["config"].get("User")
            require(user in ({"angmoo", "10001", "10001:10001"} if service == "backend" else {"node", "1000", "1000:1000"}), "oci_user_invalid")
            expected_cmd = ["contributor-api"] if service == "backend" else ["node", "app/server.js"]
            require(config["config"].get("Cmd") == expected_cmd, "oci_command_invalid")
            if service == "backend":
                require(config["config"].get("Entrypoint") == ["/usr/local/bin/angmoo-backend-entrypoint"], "oci_entrypoint_invalid")
            require(config["config"].get("WorkingDir") == "/app", "oci_workdir_invalid")
            found.append({
                "service": service, "platform": platform, "source_sha": source,
                "version": version, "repository": f"ghcr.io/{REPOSITORY}-{service}",
                "manifest_digest": desc["digest"], "config_digest": doc["config"]["digest"],
                "layers": [layer["digest"] for layer in doc["layers"]],
                "diff_ids": config["rootfs"]["diff_ids"], "user": user,
                "entrypoint": config["config"].get("Entrypoint", []), "command": expected_cmd,
            })

        for desc in index["manifests"]:
            walk(desc)
        require(len(found) == 1, "oci_execution_manifest_ambiguous")
        require(attestation_subjects == {found[0]["manifest_digest"]}, "oci_attestation_target_mismatch")
        require("https://spdx.dev/Document" in predicates and any(str(p).startswith("https://slsa.dev/provenance/") for p in predicates), "oci_supply_chain_evidence_missing")
        result = found[0]
        result.update(archive=path.name, archive_size=path.stat().st_size, archive_digest=digest_file(path), attestation_manifests=attestations)
        return result


def verify_archive(path: Path, item: dict) -> dict:
    require(path.is_file() and not path.is_symlink(), "archive_missing_or_symlink")
    require(path.stat().st_size == item["archive_size"] and digest_file(path) == item["archive_digest"], "archive_hash_mismatch")
    actual = inspect_oci(path, service=item["service"], platform=item["platform"], source=item["source_sha"], version=item["version"])
    for key in ("manifest_digest", "config_digest", "diff_ids", "layers"):
        require(actual[key] == item[key], "archive_identity_mismatch")
    return actual


def proot_archive(source: Path, target: Path, item: dict) -> None:
    """Flatten only the OCI index for PRoot-Distro's single-level importer.

    Every original blob (including SBOM/provenance) is copied unchanged. The
    execution manifest, config and compressed layers remain the same image;
    this temporary transport envelope is never used as a release artifact.
    """
    verify_archive(source, item)
    require(source.resolve() != target.resolve(), "archive_source_overwrite")
    with tarfile.open(source, "r:*") as original:
        members = {m.name.removeprefix("./").rstrip("/"): m for m in original}
        def document(name):
            with original.extractfile(members[name]) as stream:
                return json.load(stream)
        index = document("index.json")
        leaves = []
        def flatten(desc):
            doc = document("blobs/sha256/" + desc["digest"][7:])
            if "manifests" in doc:
                for child in doc["manifests"]:
                    flatten(child)
            else:
                leaves.append(desc)
        for desc in index["manifests"]:
            flatten(desc)
        raw = json.dumps({**index, "manifests": leaves}, separators=(",", ":")).encode()
        with target.open("xb") as stream, tarfile.open(fileobj=stream, mode="w") as output:
            for name, member in members.items():
                if name == "index.json":
                    replacement = tarfile.TarInfo("index.json")
                    replacement.size = len(raw)
                    output.addfile(replacement, io.BytesIO(raw))
                else:
                    with original.extractfile(member) if member.isfile() else io.BytesIO() as blob:
                        output.addfile(member, blob if member.isfile() else None)
    actual = inspect_oci(target, service=item["service"], platform=item["platform"], source=item["source_sha"], version=item["version"])
    for key in ("manifest_digest", "config_digest", "layers", "diff_ids", "attestation_manifests"):
        require(actual[key] == item[key], "proot_transport_identity_mismatch")
