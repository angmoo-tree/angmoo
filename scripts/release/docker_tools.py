"""Verify independently produced historical Docker migration tools."""
import json

from launcher.termux.payload import digest_file, require


def download(github, *, source, run, attempt, artifact, directory):
    # Workflow tooling may be newer than the preserved 0.1.4 product checkout.
    metadata = github.read(f"actions/runs/{run}/attempts/{attempt}")
    tooling_source = metadata["head_sha"]
    github.main_source(tooling_source)
    github.main_source(source)
    producer = github.run(run, attempt, workflow="docker-migration-tools.yml", source=tooling_source)
    original = github.artifact(artifact, producer, name=f"docker-migration-tools-{source}-{attempt}")
    root = github.download(original, directory)
    receipt = json.loads((root / "angmoo-migration-tools.json").read_text(encoding="utf-8"))
    require(receipt.get("schema") == "angmoo-migration-tools.v1" and
            receipt.get("source_sha") == source and receipt.get("source_version") == "0.1.3" and
            receipt.get("target_version") == "0.1.4", "docker_tools_identity_invalid")
    names = {"angmoo-migrate.exe", "angmoo-migrate.py"}
    require(set(receipt.get("files", {})) == names and
            {p.name for p in root.iterdir()} == names | {"angmoo-migration-tools.json"},
            "docker_tools_file_set_invalid")
    for name, digest in receipt["files"].items():
        require(digest_file(root / name) == "sha256:" + digest, "docker_tools_hash_mismatch")
    return {name: root / name for name in names}
