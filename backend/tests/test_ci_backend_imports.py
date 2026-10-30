"""The shard entry point must resolve application and repository test tools."""
import os
from pathlib import Path
import subprocess
import sys


def test_shard_import_setup_resolves_repository_tools_from_backend_directory(tmp_path):
    root = Path(__file__).resolve().parents[2]
    probe = tmp_path / "import-probe.py"
    probe.write_text('''import importlib.util,runpy,sys
from pathlib import Path
root=Path(sys.argv[1])
runner=runpy.run_path(str(root/'scripts/ci/run_backend_shard.py'),run_name='import_probe')
runner['configure_test_import_paths']()
spec=importlib.util.find_spec('scripts.ci.windows_postgresql_coverage')
assert Path(spec.origin).resolve()==(root/'scripts/ci/windows_postgresql_coverage.py').resolve()
assert importlib.util.find_spec('app.runtime.windows_postgresql') is not None
print('repository and application import roots verified')
''', encoding="utf-8")
    env = dict(os.environ, PYTHONPATH=str(root / "scripts/ci"))
    result = subprocess.run([sys.executable, str(probe), str(root)],
                            cwd=root / "backend", env=env, capture_output=True,
                            text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "repository and application import roots verified"
