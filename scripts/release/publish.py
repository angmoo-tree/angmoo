"""P6 Release state machine: verify by default, resumable draft then publish."""

import argparse
import hashlib
import json
from pathlib import Path
import subprocess

from launcher.termux.payload import REPOSITORY, digest_file, require
from scripts.release.candidate import ROOT, run, write_json
from scripts.release.github import GitHub
from scripts.release.prepare import prepare
from scripts.release.promote import registry_document


class ReleaseAPI:
    def find(self, tag):
        # The tag endpoint only returns published releases. The authenticated
        # list includes drafts and lets an interrupted upload resume by identity.
        matches = []
        for page in range(1, 101):
            result = subprocess.run(["gh", "api", f"repos/{REPOSITORY}/releases?per_page=100&page={page}"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            require(result.returncode == 0, "release_lookup_failed")
            values = json.loads(result.stdout)
            require(isinstance(values, list) and all(isinstance(v, dict) for v in values), "release_lookup_invalid")
            matches.extend(v for v in values if v.get("tag_name") == tag)
            require(len(matches) <= 1, "release_tag_ambiguous")
            if len(values) < 100:
                return matches[0] if matches else None
        raise ValueError("release_pagination_limit")

    def write(self, path, method, payload):
        result = subprocess.run(["gh", "api", f"repos/{REPOSITORY}/{path}", "--method", method, "--input", "-"], input=json.dumps(payload).encode(), stdout=subprocess.PIPE, check=True)
        return json.loads(result.stdout)

    def create(self, expected):
        return self.write("releases", "POST", {"tag_name": expected["tag"], "target_commitish": expected["source_sha"], "name": expected["name"], "body": expected["notes"], "draft": True, "prerelease": False, "make_latest": "false"})

    def upload(self, tag, file):
        subprocess.run(["gh", "release", "upload", tag, str(file), "--repo", REPOSITORY], check=True)

    def asset_digest(self, asset):
        process = subprocess.Popen(["gh", "api", f"repos/{REPOSITORY}/releases/assets/{asset['id']}", "--header", "Accept: application/octet-stream"], stdout=subprocess.PIPE)
        digest = hashlib.file_digest(process.stdout, "sha256").hexdigest()
        require(process.wait() == 0, "release_asset_download_failed")
        return "sha256:" + digest

    def publish(self, release):
        return self.write(f"releases/{release['id']}", "PATCH", {"draft": False, "make_latest": "true"})


def synchronize(expected: dict, directory: Path, operation: str, api, authorize) -> dict:
    require(operation in {"verify", "draft", "publish"}, "release_operation_invalid")
    assets = {a["name"]: a for a in expected["assets"]}
    require(len(assets) == len(expected["assets"]) and set(p.name for p in directory.iterdir()) == set(assets), "release_staging_extra_files")
    for name, record in assets.items():
        path = directory / name
        require(path.is_file() and not path.is_symlink() and path.stat().st_size == record["size"] and digest_file(path) == record["sha256"], "release_staging_hash_mismatch")
    if operation == "verify":
        return {"state": "VERIFIED", "publication_ready": expected["publication_ready"], "remote_writes": 0}
    require(expected["publication_ready"], "release_publication_not_ready")
    authorize()
    release = api.find(expected["tag"])
    if release is None:
        release = api.create(expected)
    require(release["tag_name"] == expected["tag"] and release["name"] == expected["name"] and (release.get("body") or "") == expected["notes"] and not release["prerelease"], "release_metadata_conflict")
    current = {a["name"]: a for a in release["assets"]}
    require(len(current) == len(release["assets"]) and set(current) <= set(assets), "release_unexpected_assets")
    for name, record in assets.items():
        if name in current:
            require(current[name]["size"] == record["size"] and api.asset_digest(current[name]) == record["sha256"], "release_existing_asset_conflict")
        else:
            require(release["draft"], "published_release_incomplete")
            authorize()
            # On a network failure leave the draft intact. A rerun reads remote
            # state and hashes before uploading any missing file; never clobber.
            api.upload(expected["tag"], directory / name)
    release = api.find(expected["tag"])
    require(release is not None and {a["name"] for a in release["assets"]} == set(assets), "release_upload_incomplete")
    for asset in release["assets"]:
        require(asset["size"] == assets[asset["name"]]["size"] and api.asset_digest(asset) == assets[asset["name"]]["sha256"], "release_uploaded_hash_mismatch")
    if operation == "publish" and release["draft"]:
        authorize()
        api.publish(release)
        release = api.find(expected["tag"])
        require(release is not None and not release["draft"], "release_publication_unconfirmed")
    return {"state": "DRAFT" if release["draft"] else "PUBLISHED", "release_id": release["id"], "url": release["html_url"], "tag": expected["tag"], "source_sha": expected["source_sha"], "assets": [{"id": a["id"], "name": a["name"]} for a in release["assets"]]}


def verify_product_checkout(root: Path, source: str) -> Path:
    root = root.resolve()
    require(Path(run("git", "-C", str(root), "rev-parse", "--show-toplevel", capture=True)).resolve() == root, "release_product_root_invalid")
    require(run("git", "-C", str(root), "rev-parse", "HEAD", capture=True) == source, "release_checkout_source_mismatch")
    require(not run("git", "-C", str(root), "status", "--porcelain", "--untracked-files=all", capture=True), "release_product_checkout_dirty")
    return root


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--operation", choices=("verify", "draft", "publish"), default="verify")
    for field in ("source", "tag", "windows-run", "windows-attempt", "windows-artifact", "candidate-run", "candidate-attempt", "candidate-artifact"):
        parser.add_argument("--" + field, required=True)
    parser.add_argument("--review-ref")
    parser.add_argument("--product-root", type=Path, default=ROOT)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    product_root = verify_product_checkout(args.product_root, args.source)
    output = args.output.resolve()
    expected = prepare(source=args.source, tag=args.tag, windows_run=args.windows_run, windows_attempt=args.windows_attempt, windows_artifact=args.windows_artifact, candidate_run=args.candidate_run, candidate_attempt=args.candidate_attempt, candidate_artifact=args.candidate_artifact, review_ref=args.review_ref or None, output=output, product_root=product_root)
    manifest = read_json(output / "assets/release-manifest.json")
    def authorize():
        github = GitHub()
        github.main_source(args.source)
        require(github.read(f"commits/{args.tag}")["sha"] == args.source, "release_tag_changed")
        github.run(args.windows_run, args.windows_attempt, workflow="windows-installer.yml", source=args.source)
        github.run(args.candidate_run, args.candidate_attempt, workflow="container-candidate.yml", source=args.source)
        for service, digest in manifest["indexes"].items():
            remote = registry_document(f"ghcr.io/{REPOSITORY}-{service}:{args.tag}")
            require(remote is not None and remote[0] == digest, "release_images_changed")
    receipt = synchronize(expected, output / "assets", args.operation, ReleaseAPI(), authorize)
    receipt["tooling_source_sha"] = run("git", "rev-parse", "HEAD", capture=True)
    write_json(output / "release-publication.json", receipt)
    print(json.dumps({"validation": expected["validation"], "result": receipt}))


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
