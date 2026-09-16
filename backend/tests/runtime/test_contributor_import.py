"""The spawn main import must not compose a server or touch its data root."""

import os
from pathlib import Path
import subprocess
import sys

import pytest


@pytest.mark.parametrize("mode", ["import", "spawn-main"])
def test_contributor_import_does_not_load_server_dependencies(tmp_path, mode):
    backend = Path(__file__).resolve().parents[2]
    source = r"""
import importlib, importlib.abc, pathlib, runpy, sys
class RejectServerDependencies(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path, target=None):
        if fullname in {'app.runtime.configuration', 'app.main', 'uvicorn'}:
            raise AssertionError('spawn main loaded server dependency: ' + fullname)
sys.meta_path.insert(0, RejectServerDependencies())
if sys.argv[1] == 'spawn-main':
    runpy.run_module('app.runtime.contributor_backend', run_name='__mp_main__')
else:
    importlib.import_module('app.runtime.contributor_backend')
assert not pathlib.Path(sys.argv[2]).exists()
"""
    data_root = tmp_path / "untouched"
    result = subprocess.run(
        [sys.executable, "-c", source, mode, str(data_root)],
        cwd=backend,
        env={**os.environ, "PYTHONPATH": str(backend),
             "ANGMOO_CONTRIBUTOR_DATA_ROOT": str(data_root),
             "ANGMOO_FRONTEND_ORIGIN": "http://127.0.0.1:3000"},
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == ""
    assert not data_root.exists()


@pytest.mark.parametrize("missing,code", [
    ("ANGMOO_CONTRIBUTOR_DATA_ROOT", "contributor_data_root_required"),
    ("ANGMOO_FRONTEND_ORIGIN", "contributor_frontend_origin_required"),
])
def test_reload_factory_rejects_missing_input_before_data_preparation(tmp_path, monkeypatch, missing, code):
    from app.runtime.contributor_backend import create_contributor_runtime_app_from_environment

    root = tmp_path / "untouched"
    monkeypatch.setenv("ANGMOO_CONTRIBUTOR_DATA_ROOT", str(root))
    monkeypatch.setenv("ANGMOO_FRONTEND_ORIGIN", "http://127.0.0.1:3000")
    monkeypatch.delenv(missing, raising=False)
    with pytest.raises(RuntimeError, match=code):
        create_contributor_runtime_app_from_environment()
    assert not root.exists()


def test_existing_data_without_secret_is_not_reinitialized(tmp_path):
    from app.runtime.contributor_backend import _prepare_contributor_data_root

    canonical = tmp_path / "canonical"
    canonical.mkdir()
    marker = canonical / "existing-data"
    marker.write_bytes(b"preserve")
    with pytest.raises(RuntimeError, match="app_secret_missing_for_existing_data"):
        _prepare_contributor_data_root(tmp_path)
    assert marker.read_bytes() == b"preserve"
    assert not (tmp_path / "secrets").exists()
