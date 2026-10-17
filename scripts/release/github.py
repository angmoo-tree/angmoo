"""Bounded GitHub evidence reads and safe artifact extraction; no remote writes."""

import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import zipfile

from launcher.termux.payload import REPOSITORY, SOURCE, require


class GitHub:
    def read(self, path: str):
        result = subprocess.run(["gh", "api", f"repos/{REPOSITORY}/{path}"], check=True, stdout=subprocess.PIPE)
        return json.loads(result.stdout)

    def pages(self, path: str, key: str) -> list:
        separator = "&" if "?" in path else "?"
        rows = []
        for page in range(1, 101):
            data = self.read(f"{path}{separator}per_page=100&page={page}")[key]
            rows.extend(data)
            if len(data) < 100:
                return rows
        raise ValueError("github_pagination_limit")

    def main_source(self, source: str):
        require(SOURCE.fullmatch(source), "source_invalid")
        compare = self.read(f"compare/{source}...main")
        require(compare["status"] in {"ahead", "identical"}, "source_not_main_ancestor")

    def run(self, run_id: str, attempt: str, *, workflow: str, source: str):
        require(str(run_id).isdecimal() and str(attempt).isdecimal(), "run_identity_invalid")
        value = self.read(f"actions/runs/{run_id}/attempts/{attempt}")
        require(value.get("repository", {}).get("full_name") == REPOSITORY and value.get("head_repository", {}).get("full_name") == REPOSITORY, "producer_repository_invalid")
        require(value.get("path") == f".github/workflows/{workflow}" and value.get("head_sha") == source and value.get("head_branch") == "main", "producer_identity_invalid")
        require(value.get("event") in {"push", "workflow_dispatch", "schedule"} and value.get("status") == "completed" and value.get("conclusion") == "success", "producer_not_successful_main")
        require(str(value.get("run_attempt")) == str(attempt), "producer_attempt_mismatch")
        return value

    def artifact(self, artifact_id: str, run: dict, *, name: str) -> dict:
        require(str(artifact_id).isdecimal(), "artifact_id_invalid")
        value = self.read(f"actions/artifacts/{artifact_id}")
        require(not value.get("expired") and value.get("name") == name, "artifact_missing_expired_or_wrong_name")
        owner = value.get("workflow_run", {})
        require(str(owner.get("id")) == str(run["id"]) and owner.get("head_sha") == run["head_sha"], "artifact_run_mismatch")
        require(run["run_started_at"] <= value["created_at"] <= run["updated_at"], "artifact_attempt_mismatch")
        require(re.fullmatch(r"sha256:[0-9a-f]{64}", str(value.get("digest", ""))), "artifact_digest_missing")
        return value

    def named_artifact(self, run: dict, name: str) -> dict:
        values = [a for a in self.pages(f"actions/runs/{run['id']}/artifacts", "artifacts") if a["name"] == name and not a["expired"]]
        require(len(values) == 1, "artifact_not_unique")
        return self.artifact(str(values[0]["id"]), run, name=name)

    def download(self, artifact: dict, directory: Path) -> Path:
        directory.mkdir(parents=True, exist_ok=True)
        archive = directory.parent / f"artifact-{artifact['id']}.zip"
        with archive.open("wb") as stream:
            subprocess.run(["gh", "api", f"repos/{REPOSITORY}/actions/artifacts/{artifact['id']}/zip"], check=True, stdout=stream)
        with archive.open("rb") as stream:
            require("sha256:" + hashlib.file_digest(stream, "sha256").hexdigest() == artifact["digest"], "artifact_zip_hash_mismatch")
        with zipfile.ZipFile(archive) as bundle:
            names = set()
            for item in bundle.infolist():
                path = PurePosixPath(item.filename)
                require(not path.is_absolute() and ".." not in path.parts and "\\" not in item.filename and ":" not in item.filename, "artifact_path_invalid")
                require(item.filename not in names and (item.external_attr >> 16) & 0o170000 != 0o120000, "artifact_link_or_duplicate")
                names.add(item.filename)
            require(sum(i.file_size for i in bundle.infolist()) <= 40 * 1024**3, "artifact_extraction_limit")
            bundle.extractall(directory)
        return directory

    def select_candidate(self, source: str) -> tuple[dict, dict]:
        runs = self.pages(f"actions/workflows/container-candidate.yml/runs?head_sha={source}&status=success", "workflow_runs")
        candidates = [r for r in runs if r["head_branch"] == "main" and r["event"] == "workflow_dispatch"]
        require(bool(candidates), "successful_candidate_missing")
        chosen = max(candidates, key=lambda r: (r["id"], r["run_attempt"]))
        run = self.run(str(chosen["id"]), str(chosen["run_attempt"]), workflow="container-candidate.yml", source=source)
        artifact = self.named_artifact(run, f"release-candidate-{source}-{run['run_attempt']}")
        return run, artifact


def successful_images(manifest: dict):
    from launcher.termux.payload import validate_manifest
    validate_manifest(manifest)
    for image in manifest["images"]:
        require(image.get("validation") == {"runtime": "PASS", "native": "PASS", "security": "PASS"}, "candidate_validation_incomplete")
        require(bool(image.get("attestation_manifests")) and image.get("sbom") and image.get("security_report"), "candidate_supply_chain_missing")
