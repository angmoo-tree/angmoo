from __future__ import annotations

import json
import logging
import os
from pathlib import Path
import shutil
import subprocess
import sys
from types import SimpleNamespace

import pytest
from uvicorn.config import LOGGING_CONFIG

from app.runtime import logging_config


BACKEND = Path(__file__).resolve().parents[2]
ROOT = BACKEND.parent


def process(source: str, *arguments: str) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(BACKEND)
    return subprocess.run([sys.executable, "-c", source, *arguments], cwd=BACKEND,
                          env=environment, capture_output=True, text=True, encoding="utf-8", timeout=30)


def test_ini_preserves_uvicorn_defaults_and_root_warning_without_handlers():
    assert logging_config.uvicorn_logging_config() == LOGGING_CONFIG
    result = process("import logging; from app.runtime.logging_config import configure_application_logging; configure_application_logging(); configure_application_logging(); assert logging.getLogger().level == logging.WARNING; assert logging.getLogger().handlers == []")
    assert result.returncode == 0, result.stderr
    assert result.stdout == ""
    assert result.stderr == ""


def test_repeated_factories_preserve_embedding_handlers_levels_and_caplog(caplog, monkeypatch):
    import app.main as legacy
    import app.public_main as local

    root = logging.getLogger()
    caplog.set_level(logging.INFO)
    handlers = list(root.handlers)
    levels = [handler.level for handler in handlers]
    formatters = [handler.formatter for handler in handlers]
    for _ in range(3):
        legacy.create_app()
        local.create_app(prepare_media_directories=False)
    logging.getLogger("angmoo.logging-test").info("retained diagnostic")
    assert root.handlers == handlers
    assert [handler.level for handler in root.handlers] == levels
    assert [handler.formatter for handler in root.handlers] == formatters
    assert root.level == logging.INFO
    assert caplog.messages.count("retained diagnostic") == 1


def test_explicit_root_level_without_handlers_is_preserved(monkeypatch):
    root = logging.getLogger()
    monkeypatch.setattr(root, "handlers", [])
    monkeypatch.setattr(root, "level", logging.DEBUG)
    logging_config.configure_application_logging()
    assert root.level == logging.DEBUG
    assert root.handlers == []


def test_source_resource_is_independent_of_working_directory(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "logging.ini").write_text("untrusted cwd configuration", encoding="utf-8")
    assert logging_config.logging_config_path() == BACKEND / "logging.ini"
    assert logging_config.uvicorn_logging_config() == LOGGING_CONFIG


@pytest.mark.parametrize("layout", ["_MEI12345", "sidecar/_internal"])
def test_frozen_onefile_and_onedir_read_only_the_bundle_resource(tmp_path, monkeypatch, layout):
    bundle = tmp_path / layout
    bundle.mkdir(parents=True)
    shutil.copyfile(BACKEND / "logging.ini", bundle / "logging.ini")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(bundle), raising=False)
    monkeypatch.chdir(tmp_path)
    assert logging_config.logging_config_path() == bundle / "logging.ini"
    assert logging_config.uvicorn_logging_config() == LOGGING_CONFIG
    (bundle / "logging.ini").unlink()
    shutil.copyfile(BACKEND / "logging.ini", tmp_path / "logging.ini")
    with pytest.raises(logging_config.RuntimeLoggingConfigurationError, match="runtime_logging_configuration_missing"):
        logging_config.configure_application_logging()


def test_ini_is_consumed_and_invalid_configuration_fails_before_startup(tmp_path, monkeypatch):
    config = tmp_path / "logging.ini"
    original = (BACKEND / "logging.ini").read_text(encoding="utf-8")
    config.write_text(original.replace("level = WARNING", "level = ERROR"), encoding="utf-8")
    monkeypatch.setattr(logging_config, "logging_config_path", lambda: config)
    root = logging.getLogger()
    monkeypatch.setattr(root, "handlers", [])
    monkeypatch.setattr(root, "level", logging.WARNING)
    logging_config.configure_application_logging()
    assert root.level == logging.ERROR
    config.write_text(original.replace("level = WARNING", "level = INVALID"), encoding="utf-8")
    with pytest.raises(logging_config.RuntimeLoggingConfigurationError, match="runtime_logging_configuration_invalid"):
        logging_config.configure_application_logging()


def test_noconsole_subprocess_with_missing_stdio_has_no_formatter_crash():
    result = process("""
import sys, logging
from app.runtime.logging_config import configure_application_logging, uvicorn_logging_config
from uvicorn import Config
stdout, stderr = sys.stdout, sys.stderr
sys.stdout = sys.stderr = None
configure_application_logging()
Config(lambda scope, receive, send: None, log_config=uvicorn_logging_config())
logging.getLogger('uvicorn.error').info('no GUI console')
logging.warning('no GUI stderr')
sys.stdout, sys.stderr = stdout, stderr
print('completed')
""")
    assert result.returncode == 0, result.stderr
    assert result.stdout == "completed\n"
    assert result.stderr == ""


def test_missing_bundle_resource_keeps_content_free_sidecar_fatal_protocol(tmp_path):
    result = process("""
import runpy, sys
sys.frozen = True
sys._MEIPASS = sys.argv[1]
runpy.run_module('app.runtime.desktop_sidecar', run_name='__main__')
""", str(tmp_path))
    assert result.returncode == 1
    assert result.stdout == ""
    assert json.loads(result.stderr) == {"event": "fatal", "code": "desktop_sidecar_startup_failed"}
    assert str(tmp_path) not in result.stderr


@pytest.mark.parametrize("reload", [False, True])
def test_contributor_server_and_reload_child_receive_the_same_logging_configuration(tmp_path, monkeypatch, reload):
    from app.runtime import contributor_backend

    args = SimpleNamespace(data_root=tmp_path, host="127.0.0.1", port=8080,
                           frontend_origin="http://127.0.0.1:3000", diagnostics=False, reload=reload)
    monkeypatch.setattr(contributor_backend, "_parse_args", lambda: args)
    app = object()
    monkeypatch.setattr(contributor_backend, "create_contributor_runtime_app", lambda **kwargs: app)
    calls = []
    monkeypatch.setattr(contributor_backend.uvicorn, "run", lambda *args, **kwargs: calls.append((args, kwargs)))
    monkeypatch.setenv("ANGMOO_CONTRIBUTOR_DATA_ROOT", "temporary")
    monkeypatch.setenv("ANGMOO_FRONTEND_ORIGIN", "temporary")
    contributor_backend.main()
    assert len(calls) == 1
    positional, kwargs = calls[0]
    assert kwargs["log_config"] == LOGGING_CONFIG
    if reload:
        assert positional == ("app.runtime.contributor_backend:create_contributor_runtime_app_from_environment",)
        assert kwargs["factory"] is True
        assert kwargs["reload"] is True
    else:
        assert positional == (app,)


def test_public_and_legacy_cli_keep_their_existing_asgi_target(monkeypatch):
    import app.main as legacy
    import app.public_main as local

    calls = []
    monkeypatch.setattr(legacy.uvicorn, "run", lambda *args, **kwargs: calls.append((args, kwargs)))
    legacy.main()
    local.main()
    assert len(calls) == 2
    for args, kwargs in calls:
        assert args == ("app.public_main:app",)
        assert kwargs == {"host": "0.0.0.0", "port": 8080, "reload": True, "log_config": LOGGING_CONFIG}


def test_installer_json_stdout_and_existing_redaction_are_unchanged(tmp_path):
    result = process("""
import logging, sys
from pathlib import Path
from app.core.redaction import redact_secret_text
from app.runtime import desktop_sidecar
root = Path(sys.argv[1])
sys.argv = ['sidecar', '--installer-data-preflight', '--data-root', str(root), '--runtime-root', str(root/'runtime'), '--legacy-data-root', str(root/'legacy'), '--payload-manifest', str(root/'payload.json')]
def operation(*args, **kwargs):
    logging.warning(redact_secret_text('sk-' + 'x' * 24))
    return {'status': 'compatible', 'schema_version': 1}
desktop_sidecar._run_installer_operation = operation
raise SystemExit(desktop_sidecar.main())
""", str(tmp_path))
    assert result.returncode == 0, result.stderr
    expected = {"status": "compatible", "schema_version": 1, "operation": "preflight"}
    assert json.loads(result.stdout) == expected
    assert json.loads((tmp_path / "runtime/installer-data-upgrade-result.json").read_text(encoding="utf-8")) == expected
    assert "[REDACTED_OPENAI_API_KEY]" in result.stderr
    assert "x" * 24 not in result.stderr


def test_sidecar_serve_health_and_shutdown_preserve_silent_streams_and_endpoint_protocol(tmp_path):
    result = process("""
import json, os, sys, threading, time, urllib.request
from pathlib import Path
from types import SimpleNamespace
from fastapi import FastAPI
import app.public_main as composition
from app.runtime import desktop_sidecar, configuration
root = Path(sys.argv[1])
token, origin = 'a' * 64, 'http://tauri.localhost'
os.environ['DESKTOP_LAUNCH_TOKEN'], os.environ['DESKTOP_ALLOWED_ORIGIN'] = token, origin
sys.argv = ['sidecar', '--parent-pid', str(os.getpid()), '--data-root', str(root), '--runtime-root', str(root/'runtime'), '--legacy-data-root', str(root/'legacy'), '--launch-id', 'logging-handshake', '--runtime-profile', 'TEST']
app = FastAPI()
app.state.runtime_composition = SimpleNamespace(session_factory=lambda: None)
@app.get('/health')
async def health():
    return {'status': 'ok'}
composition.create_app = lambda **kwargs: app
configuration.initialize_local_installation_identity = lambda factory: None
desktop_sidecar._build_embedded_runtime_config = lambda *args, **kwargs: object()
observed = {}
def client():
    endpoint = root/'runtime/sidecar.endpoint.json'
    for attempt in range(150):
        try:
            payload = json.loads(endpoint.read_text())
            url = f"http://127.0.0.1:{payload['dynamic_port']}"
            headers = {'X-Angmoo-Launcher-Token': token, 'Origin': origin}
            with urllib.request.urlopen(urllib.request.Request(url+'/health', headers=headers), timeout=0.3) as response:
                observed['health'] = json.load(response)
            with urllib.request.urlopen(urllib.request.Request(url+'/__angmoo/desktop/shutdown', data=b'', headers=headers, method='POST'), timeout=1) as response:
                observed['shutdown'] = json.load(response)
            return
        except (OSError, ValueError):
            time.sleep(0.05)
threading.Thread(target=client, daemon=True).start()
watchdog = threading.Timer(15, lambda: os._exit(91))
watchdog.daemon = True
watchdog.start()
observed['exit_code'] = desktop_sidecar.main()
watchdog.cancel()
observed['endpoint_removed'] = not (root/'runtime/sidecar.endpoint.json').exists()
print(json.dumps(observed))
""", str(tmp_path))
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {
        "health": {"status": "ok"}, "shutdown": {"status": "stopping"},
        "exit_code": 0, "endpoint_removed": True,
    }
    assert result.stderr == ""


def test_container_and_both_pyinstaller_layouts_include_logging_resource():
    dockerfile = (ROOT / "Dockerfile.backend").read_text(encoding="utf-8")
    build = (ROOT / "desktop/scripts/build-sidecar.ps1").read_text(encoding="utf-8")
    assert "COPY --chown=angmoo:angmoo backend/logging.ini ./" in dockerfile
    assert '$loggingConfig = Join-Path $backendRoot "logging.ini"' in build
    assert '$loggingConfigData = "$loggingConfig;."' in build
    assert "--add-data $loggingConfigData" in build
    assert '$Layout -eq "OneFile"' in build
    assert '"--onefile"' in build and '"--onedir"' in build
    assert "--noconsole" in build
