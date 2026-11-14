"""Common release sources/notices, independent of the native Windows installer."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess

from launcher.termux.payload import digest_file, require
from scripts.ci.check_release_tag import expected_release_tag
from scripts.package_postgresql_sources import package
from scripts.release.github import GitHub

FILES = {"angmoo-postgresql-sources.zip", "THIRD_PARTY_NOTICES.md", "LICENSE"}


def validate(directory: Path, source: str, version: str) -> dict:
    receipt = json.loads((directory / "release-assets.json").read_text(encoding="utf-8"))
    require(receipt.get("schema") == "angmoo-release-assets.v1" and
            receipt.get("source_sha") == source and receipt.get("version") == version,
            "common_assets_identity_mismatch")
    require(set(receipt.get("files", {})) == FILES and
            {p.name for p in directory.iterdir()} == FILES | {"release-assets.json"},
            "common_assets_file_set_invalid")
    for name, digest in receipt["files"].items():
        path = directory / name
        require(path.is_file() and not path.is_symlink() and digest_file(path) == digest,
                "common_assets_hash_mismatch")
    return receipt


def download(github: GitHub, *, source, version, run, attempt, artifact, directory):
    producer = github.run(run, attempt, workflow="release-assets.yml", source=source)
    original = github.artifact(artifact, producer, name=f"release-assets-{source}-{attempt}")
    root = github.download(original, directory)
    validate(root, source, version)
    return root


def build(root: Path, output: Path, cache: Path):
    source = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    require(not subprocess.check_output(["git", "status", "--porcelain", "--untracked-files=all"],
                                       cwd=root, text=True).strip(), "release_assets_checkout_dirty")
    version = expected_release_tag(root).removeprefix("release-v")
    require(not output.exists() or not any(output.iterdir()), "release_assets_output_not_empty")
    output.mkdir(parents=True, exist_ok=True)
    package(output / "angmoo-postgresql-sources.zip", cache)
    for name in ("THIRD_PARTY_NOTICES.md", "LICENSE"):
        shutil.copyfile(root / name, output / name)
    receipt = {"schema": "angmoo-release-assets.v1", "source_sha": source, "version": version,
               "files": {name: digest_file(output / name) for name in sorted(FILES)}}
    (output / "release-assets.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    validate(output, source, version)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", required=True, type=Path)
    p.add_argument("--cache", required=True, type=Path)
    a = p.parse_args()
    build(Path(__file__).resolve().parents[2], a.output, a.cache)
