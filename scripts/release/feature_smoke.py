"""Run selected existing feature contracts against an unmodified candidate.

Only pure Python test tooling from the shared lock is staged alongside tests.
The image's app and production dependencies are never replaced.
"""
import hashlib
import io
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import tomllib
import urllib.request
import uuid
import zipfile

from launcher.termux.payload import require
from scripts.release.candidate import ROOT

TESTS = (
    "memory/test_hybrid_native_pipeline.py::test_real_fts_vec1_fusion_hydrates_authorized_sources_and_rejects_stale_version[blocked-group_or_v1]",
    "memory/test_hybrid_native_pipeline.py::test_real_fts_vec1_fusion_hydrates_authorized_sources_and_rejects_stale_version[deleted_source-group_or_v1]",
    "memory/test_hybrid_native_pipeline.py::test_real_fts_vec1_fusion_hydrates_authorized_sources_and_rejects_stale_version[memory_off-group_or_v1]",
    "memory/test_sqlite_vec1.py",
    "memory/test_vector_pending_work.py::test_snapshot_preparation_allows_wal_writer_and_rejects_changed_proof",
    "memory/test_vector_work_recovery.py::test_vector_commit_before_budget_or_ack_failure_reuses_receipt",
    "memory/test_search_diagnostics.py::test_worker_deadline_keeps_last_native_stage_and_does_not_return_late_success",
    "memory/test_search_diagnostics.py::test_cancel_preserves_last_stage_count_and_cleans_process",
)


def test_tools(output):
    destination = output / "test-tools"
    destination.mkdir(parents=True, exist_ok=True)
    packages = tomllib.loads((ROOT / "backend/uv.lock").read_text())["package"]
    for name in ("pytest", "pluggy", "iniconfig", "pygments", "packaging"):
        package = next(p for p in packages if p["name"] == name)
        wheel = next(w for w in package["wheels"] if w["url"].endswith("-py3-none-any.whl"))
        with urllib.request.urlopen(wheel["url"], timeout=60) as response:
            raw = response.read(8 * 1024 * 1024)
        require("sha256:" + hashlib.sha256(raw).hexdigest() == wheel["hash"], "test_tool_hash_mismatch")
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            for item in archive.infolist():
                require((destination / item.filename).resolve().is_relative_to(destination.resolve()), "test_tool_path_invalid")
            archive.extractall(destination)
    return destination


def run(image, platform, output):
    tooling = test_tools(output)
    name = "angmoo-feature-" + uuid.uuid4().hex[:12]
    args = ["docker", "create", "--name", name, "--network", "none", "--platform", platform,
            "--no-healthcheck",
            "--env", "PYTHONPATH=/app:/validation/tests:/validation/test-tools",
            "--env", "PYTEST_DISABLE_PLUGIN_AUTOLOAD=1",
            "--env", "ANGMOO_DENY_EXTERNAL_NETWORK=1",
            "--env", "ANGMOO_TEST_VEC1_EXTENSION=/app/app/runtime/resources/vec1/vec1.so",
            "--entrypoint", "python", image, "-m", "pytest", "-q", "-p", "no:cacheprovider",
            *("/validation/tests/" + test for test in TESTS)]
    # Host bind mounts and foreign .pyc files add cross-VM import overhead to
    # spawned workers. Stage only test inputs on the container's filesystem;
    # leave /app and its installed production dependencies untouched. This
    # command runs pytest, so the API-server healthcheck has no server to probe.
    with tempfile.TemporaryDirectory(prefix="angmoo-feature-") as directory:
        # Keep the host temporary parent private. docker cp creates root-owned
        # entries, so the copied input directory must be traversable by the
        # candidate's unchanged non-root user (TemporaryDirectory is 0700).
        stage = Path(directory) / "validation"
        stage.mkdir()
        stage.chmod(0o755)
        ignore = shutil.ignore_patterns("__pycache__", "*.pyc", ".pytest_cache")
        shutil.copytree(ROOT / "backend/tests", stage / "tests", ignore=ignore)
        shutil.copytree(tooling, stage / "test-tools", ignore=ignore)
        subprocess.run(args, check=True, stdout=subprocess.DEVNULL)
        try:
            subprocess.run(["docker", "cp", str(stage), name + ":/validation"], check=True)
            result = subprocess.run(["docker", "start", "-a", name], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8")
            status = subprocess.check_output(["docker", "inspect", "--format", "{{.State.ExitCode}}", name], text=True).strip()
        finally:
            subprocess.run(["docker", "rm", "-f", name], check=True, stdout=subprocess.DEVNULL)
    (output / "features.txt").write_text(result.stdout, encoding="utf-8")
    require(result.returncode == 0 and status == "0" and " skipped" not in result.stdout, "candidate_feature_smoke_failed: " + result.stdout[-4000:])
    (output / "features.json").write_text(json.dumps({"status": "PASS", "platform": platform, "tests": TESTS, "external_network": "disabled", "summary": result.stdout.strip().splitlines()[-1]}) + "\n")
