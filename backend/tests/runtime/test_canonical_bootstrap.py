"""Fresh product bootstrap must not depend on the temporary public module."""

import os
from pathlib import Path
import subprocess
import sys


def test_contributor_and_sidecar_register_models_without_the_compatibility_module(
    tmp_path,
):
    backend = Path(__file__).resolve().parents[2]
    source = r"""
import importlib.abc, sys
from pathlib import Path
class RejectCompatibility(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path, target=None):
        if fullname == 'app.public_main':
            raise AssertionError('product bootstrap used the compatibility module')
sys.meta_path.insert(0, RejectCompatibility())
from app.runtime import contributor_backend, desktop_sidecar
from app.runtime.configuration import RuntimeProfile
root = Path(sys.argv[1])
app = contributor_backend.create_contributor_runtime_app(data_root=root / 'contributor')
try:
    from app import main
    from app.core.db import Base
    assert app.state.runtime_config.database_path.is_file()
    assert len(Base.metadata.tables) > 50
    assert app.openapi()['paths']['/health']['get']['operationId'] == 'runtime_health_health_get'
    assert app.state.runtime_composition.session_factory is not None
finally:
    app.state.restore_process_settings()
side_root = root / 'sidecar'
config = desktop_sidecar._build_embedded_runtime_config(
    side_root, side_root / 'runtime', profile=RuntimeProfile.TEST,
    desktop_launch_token='a' * 64, desktop_allowed_origin='http://tauri.localhost',
)
assert config.database_path.is_file()
assert 'app.public_main' not in sys.modules
"""
    result = subprocess.run(
        [sys.executable, "-c", source, str(tmp_path)],
        cwd=backend,
        env={**os.environ, "PYTHONPATH": str(backend)},
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == ""
