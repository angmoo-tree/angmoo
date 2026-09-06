import asyncio
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest
from fastapi import FastAPI

from app import main, public_main
from app.config import settings


@pytest.mark.parametrize("profile", ["full", "public"])
def test_single_factory_keeps_both_health_contracts_and_shared_types(profile):
    app = main.create_app(profile=profile, prepare_media_directories=False)
    compatibility = main.app if profile == "full" else public_main.app
    operation = app.openapi()["paths"]["/health"]["get"]
    assert app.openapi() == compatibility.openapi()
    assert operation["operationId"] == (
        "health_health_get" if profile == "full" else "runtime_health_health_get"
    )
    assert operation["responses"]["200"]["content"]["application/json"]["schema"][
        "additionalProperties"
    ] == ({"type": "string"} if profile == "full" else True)
    assert public_main.HostedBackendExtension is main.HostedBackendExtension
    assert (
        public_main.PublicRuntimeConfigurationError
        is main.PublicRuntimeConfigurationError
    )
    assert (
        public_main.HostedExtensionConfigurationError
        is main.HostedExtensionConfigurationError
    )
    assert public_main.create_app is main.create_public_app
    assert public_main.create_lifespan is main.create_public_lifespan
    assert main.create_public_app.func is main.create_app
    assert main.create_public_lifespan.func is main.create_lifespan


def test_public_lifespan_keeps_no_component_default_while_full_uses_its_default(
    monkeypatch,
):
    calls = []

    class Components:
        async def start(self):
            calls.append("start")

        async def stop(self):
            calls.append("stop")

    def components():
        calls.append("construct")
        return Components()

    original = main.create_lifespan.__kwdefaults__
    assert (
        original["component_manager_factory"]
        is main.create_single_backend_runtime_components
    )
    monkeypatch.setattr(
        main.create_lifespan,
        "__kwdefaults__",
        {
            **original,
            "component_manager_factory": components,
        },
    )
    monkeypatch.setattr(settings, "SEED_DEMO_DATA", False)

    async def run():
        app = FastAPI()
        async with main.create_lifespan(security_validator=lambda: None)(app):
            assert calls == ["construct", "start"]
        async with public_main.create_lifespan(security_validator=lambda: None)(app):
            assert calls == ["construct", "start", "stop"]

    asyncio.run(run())
    assert calls == ["construct", "start", "stop"]


@pytest.mark.parametrize("fail_memory_start", [False, True])
def test_shared_lifespan_preserves_recovery_hooks_memory_cleanup_order(
    monkeypatch, fail_memory_start
):
    calls = []
    monkeypatch.setattr(settings, "SEED_DEMO_DATA", False)

    class Components:
        def quiesce_scheduler(self):
            calls.append("quiesce")

        async def start(self):
            calls.append("components:start")

        async def stop(self):
            calls.append("components:stop")

    class Memory:
        async def start(self):
            calls.append("memory:start")
            if fail_memory_start:
                raise RuntimeError("memory startup failed")

        async def stop(self):
            calls.append("memory:stop")

    async def startup():
        calls.append("extension:start")

    async def shutdown():
        calls.append("extension:stop")

    components = Components()
    app = FastAPI()
    coordinator = SimpleNamespace(quiesce=None)
    app.state.memory_shutdown = coordinator
    lifespan = main.create_lifespan(
        main.HostedBackendExtension(
            name="probe", startup_hooks=(startup,), shutdown_hooks=(shutdown,)
        ),
        security_validator=lambda: calls.append("security"),
        component_manager_factory=lambda: components,
        startup_recovery=lambda: calls.append("recovery"),
        runtime_disposer=lambda: calls.append("dispose"),
        memory_runtime=Memory(),
    )

    async def run():
        async with lifespan(app):
            assert not fail_memory_start
            calls.append("request")

    if fail_memory_start:
        with pytest.raises(RuntimeError, match="memory startup failed"):
            asyncio.run(run())
    else:
        asyncio.run(run())
    assert coordinator.quiesce == components.quiesce_scheduler
    assert calls == [
        "security",
        "recovery",
        "extension:start",
        "components:start",
        "memory:start",
        *([] if fail_memory_start else ["request"]),
        "memory:stop",
        "components:stop",
        "extension:stop",
        "dispose",
    ]


def test_both_module_imports_are_lazy_and_explicit_factory_still_prepares_media(
    tmp_path,
):
    source = r"""
import builtins, logging, sys
from pathlib import Path
from app.config import settings
root = Path(sys.argv[1])
settings.MEDIA_ROOT = str(root)
original_import = builtins.__import__
def guarded(name, *args, **kwargs):
    if name == 'psycopg' or name.startswith('psycopg.'):
        raise ImportError('no bundled PostgreSQL DBAPI')
    return original_import(name, *args, **kwargs)
builtins.__import__ = guarded
handlers = tuple(logging.getLogger().handlers)
from app import main, public_main
from app import database as db
assert db._default_engine is None and db._default_session_factory is None
assert not root.exists()
assert tuple(logging.getLogger().handlers) == handlers
assert public_main.app is main.public_app
assert main.app is not main.public_app
assert main.app.state.runtime_composition is None
assert public_main.app.state.runtime_composition is None
assert main.app.state.memory_batch_runtime is None
assert public_main.app.state.memory_batch_runtime is None
main.create_app()
assert all((root / name).is_dir() for name in ('characters', 'posts', 'world-package-imports'))
assert db._default_engine is None and db._default_session_factory is None
"""
    backend = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        [sys.executable, "-c", source, str(tmp_path / "media")],
        cwd=backend,
        env={**os.environ, "PYTHONPATH": str(backend)},
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
