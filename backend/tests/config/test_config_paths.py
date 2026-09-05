from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

from app.config import Settings


BACKEND_ROOT = Path(__file__).resolve().parents[2]


def _clean_settings_environment() -> dict[str, str]:
    fields = {name.casefold() for name in Settings.model_fields}
    return {key: value for key, value in os.environ.items() if key.casefold() not in fields}


def _run(script: str, *, cwd: Path, env: dict[str, str]) -> dict:
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return json.loads(result.stdout)


def test_relocated_config_preserves_backend_paths_and_dotenv_precedence(tmp_path: Path) -> None:
    """Load the real source in an isolated backend without touching developer dotenv."""
    backend = tmp_path / "isolated-backend"
    package = backend / "app"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "config.py").write_bytes((BACKEND_ROOT / "app/config.py").read_bytes())
    (backend / ".env").write_text("PROJECT_NAME=from-dotenv\n", encoding="utf-8")
    elsewhere = tmp_path / "unrelated-working-directory"
    elsewhere.mkdir()
    (elsewhere / ".env").write_text("PROJECT_NAME=wrong-working-directory\n", encoding="utf-8")
    env = _clean_settings_environment()
    env["PYTHONPATH"] = str(backend)
    script = """
import json
from app.config import BACKEND_DIR, Settings, settings
print(json.dumps({
    'backend': str(BACKEND_DIR),
    'dotenv': str(Settings.model_config['env_file']),
    'database': settings.DATABASE_URL,
    'media': settings.MEDIA_ROOT,
    'graph': settings.LADYBUG_DATABASE_ROOT,
    'selected': settings.PROJECT_NAME,
    'explicit': Settings(PROJECT_NAME='explicit-constructor').PROJECT_NAME,
}))
"""
    actual = _run(script, cwd=elsewhere, env=env)
    assert Path(actual["backend"]) == backend
    assert Path(actual["dotenv"]) == backend / ".env"
    assert actual["database"] == f"sqlite+pysqlite:///{(backend / '.angmoo-dev/angmoo.sqlite3').as_posix()}"
    assert Path(actual["media"]) == backend / "uploads"
    assert Path(actual["graph"]) == backend / ".angmoo-dev/graph"
    assert actual["selected"] == "from-dotenv"
    assert actual["explicit"] == "explicit-constructor"

    env["PROJECT_NAME"] = "from-environment"
    overridden = _run(script, cwd=elsewhere, env=env)
    assert overridden["selected"] == "from-environment"
    assert overridden["explicit"] == "explicit-constructor"


def test_cold_runtime_consumers_share_config_without_a_legacy_module(tmp_path: Path) -> None:
    env = _clean_settings_environment()
    env.update(
        PYTHONPATH=str(BACKEND_ROOT),
        APP_ENV="test",
        DATABASE_URL="sqlite+pysqlite:///:memory:",
        MEDIA_ROOT=str(tmp_path / "media"),
        LADYBUG_DATABASE_ROOT=str(tmp_path / "graph"),
        SEED_DEMO_DATA="false",
        RESIDENT_TICK_SCHEDULER_ENABLED="false",
        POST_IMAGE_JOB_WORKER_ENABLED="false",
    )
    script = """
import importlib.util
import json
import sys
from app import config, main, public_main
from app.core import db, security
from app.runtime import configuration
print(json.dumps({
    'shared': config.settings is db.settings is security.settings is main.settings is public_main.settings,
    'type': config.Settings is configuration.Settings is public_main.Settings,
    'legacy_spec': importlib.util.find_spec('app.core.config') is None,
    'legacy_loaded': 'app.core.config' in sys.modules,
    'settings_module': config.Settings.__module__,
}))
"""
    actual = _run(script, cwd=tmp_path, env=env)
    assert actual == {
        "shared": True,
        "type": True,
        "legacy_spec": True,
        "legacy_loaded": False,
        "settings_module": "app.config",
    }
