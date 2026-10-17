"""Run selected existing feature contracts against an unmodified candidate.

Only pure Python test tooling from the shared lock is mounted alongside tests.
The image's app and production dependencies are never replaced.
"""
import hashlib
import io
import json
from pathlib import Path
import subprocess
import tomllib
import urllib.request
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
    args = ["docker", "run", "--rm", "--network", "none", "--platform", platform,
            "--mount", f"type=bind,source={ROOT / 'backend/tests'},target=/validation/tests,readonly",
            "--mount", f"type=bind,source={tooling.resolve()},target=/test-tools,readonly",
            "--env", "PYTHONPATH=/app:/validation/tests:/test-tools",
            "--env", "PYTEST_DISABLE_PLUGIN_AUTOLOAD=1",
            "--env", "ANGMOO_DENY_EXTERNAL_NETWORK=1",
            "--env", "ANGMOO_TEST_VEC1_EXTENSION=/app/app/runtime/resources/vec1/vec1.so",
            "--entrypoint", "python", image, "-m", "pytest", "-q", "-p", "no:cacheprovider",
            *("/validation/tests/" + test for test in TESTS)]
    result = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8")
    (output / "features.txt").write_text(result.stdout, encoding="utf-8")
    require(result.returncode == 0 and " skipped" not in result.stdout, "candidate_feature_smoke_failed: " + result.stdout[-4000:])
    (output / "features.json").write_text(json.dumps({"status": "PASS", "platform": platform, "tests": TESTS, "external_network": "disabled", "summary": result.stdout.strip().splitlines()[-1]}) + "\n")
