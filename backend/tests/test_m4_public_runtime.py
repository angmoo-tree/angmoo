import asyncio

from fastapi import APIRouter
import httpx
import pytest

from app.core.config import settings
from app.public_main import (
    HostedBackendExtension,
    HostedExtensionConfigurationError,
    PublicRuntimeConfigurationError,
    app,
    create_app,
    create_lifespan,
    validate_public_runtime_settings,
)
from app.services import agent_runs as agent_run_service
from app.services.hosted_configuration import (
    HOSTED_EXTENSION_CONTRACT_VERSION,
    HostedConfigurationRegistrationError,
    get_hosted_prompt,
    get_hosted_setting,
)
from app.services.runtime_boundary import (
    OpenClawGatewayClient,
    ResidentRuntimeUnavailableError,
    get_resident_runtime_adapter,
    openclaw_auth_profiles,
    register_resident_runtime_adapter,
    unregister_resident_runtime_adapter,
)


PRIVATE_ROUTE_PREFIXES = (
    "/api/v1/admin",
    "/api/v1/agent-tools",
    "/api/v1/maintenance",
)


def _operations() -> set[tuple[str, str]]:
    schema = app.openapi()
    return {
        (method.upper(), path)
        for path, path_item in schema["paths"].items()
        for method in path_item
        if method.lower()
        in {"get", "put", "post", "delete", "options", "head", "patch", "trace"}
    }


def test_public_runtime_exposes_only_approved_routes() -> None:
    operations = _operations()
    paths = {path for _, path in operations}

    assert len(paths) == 117
    assert len(operations) == 145
    assert (
        "POST",
        "/api/v1/agent-runs/resident-slots/tick",
    ) not in operations
    assert (
        "POST",
        "/api/v1/agent-runs/community-once",
    ) not in operations
    assert (
        "POST",
        "/api/v1/agent-runs/resident-slots/assign",
    ) not in operations
    assert all(
        not path.startswith(prefix)
        for _, path in operations
        for prefix in PRIVATE_ROUTE_PREFIXES
    )


def test_public_runtime_does_not_expose_global_resident_tick(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called = False

    async def _unexpected_tick(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("global resident tick must not be reachable over HTTP")

    monkeypatch.setattr(agent_run_service, "tick_resident_slots", _unexpected_tick)

    async def _post_tick() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            return await client.post(
                "/api/v1/agent-runs/resident-slots/tick",
                json={
                    "post_id": "post-attacker",
                    "message": "attacker context",
                    "max_runs": 10,
                },
            )

    response = asyncio.run(_post_tick())

    assert response.status_code in {404, 405}
    assert called is False


def test_public_runtime_does_not_expose_community_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called = False

    async def _unexpected_run(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("community-once must not be reachable over HTTP")

    monkeypatch.setattr(agent_run_service, "run_community_once", _unexpected_run)

    async def _post_community_once() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            return await client.post(
                "/api/v1/agent-runs/community-once",
                json={"character_id": "char-attacker"},
            )

    response = asyncio.run(_post_community_once())

    assert response.status_code in {404, 405}
    assert called is False


def test_hosted_backend_extension_registers_router_and_hooks_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "SEED_DEMO_DATA", False)
    router = APIRouter()
    calls: list[str] = []

    @router.get("/hosted-extension-probe")
    def hosted_extension_probe() -> dict[str, str]:
        return {"status": "hosted"}

    async def startup() -> None:
        calls.append("startup")

    async def shutdown() -> None:
        calls.append("shutdown")

    extension = HostedBackendExtension(
        name="test-hosted",
        routers=(router,),
        startup_hooks=(startup,),
        shutdown_hooks=(shutdown,),
    )
    hosted_app = create_app(
        extension,
        lifespan_handler=create_lifespan(
            extension,
            security_validator=lambda: None,
        ),
    )

    async def run() -> None:
        async with hosted_app.router.lifespan_context(hosted_app):
            transport = httpx.ASGITransport(app=hosted_app)
            async with httpx.AsyncClient(
                transport=transport,
                base_url="http://testserver",
            ) as client:
                response = await client.get("/api/v1/hosted-extension-probe")
            assert response.status_code == 200
            assert response.json() == {"status": "hosted"}
            assert calls == ["startup"]

    asyncio.run(run())

    assert calls == ["startup", "shutdown"]


def test_hosted_configuration_is_scoped_to_hosted_lifespan(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "SEED_DEMO_DATA", False)

    class FakeSettingsProvider:
        name = "fake-settings"

        def get_setting(self, key: str) -> object | None:
            return {"runtime": "hosted"}.get(key)

    class FakePromptProvider:
        name = "fake-prompts"

        def get_prompt(self, key: str) -> str | None:
            return {"resident": "hosted prompt"}.get(key)

    extension = HostedBackendExtension(
        name="test-hosted-configuration",
        settings_provider=FakeSettingsProvider(),
        prompt_provider=FakePromptProvider(),
    )
    hosted_app = create_app(
        extension,
        lifespan_handler=create_lifespan(
            extension,
            security_validator=lambda: None,
        ),
    )

    assert HOSTED_EXTENSION_CONTRACT_VERSION == 2
    assert get_hosted_setting("runtime") is None
    assert get_hosted_prompt("resident") is None

    async def run() -> None:
        async with hosted_app.router.lifespan_context(hosted_app):
            assert get_hosted_setting("runtime") == "hosted"
            assert get_hosted_prompt("resident") == "hosted prompt"

    asyncio.run(run())

    assert get_hosted_setting("runtime") is None
    assert get_hosted_prompt("resident") is None


def test_hosted_extension_rejects_partial_configuration() -> None:
    class FakeSettingsProvider:
        name = "fake-settings"

        def get_setting(self, key: str) -> object | None:
            return None

    with pytest.raises(HostedConfigurationRegistrationError):
        HostedBackendExtension(
            name="partial-configuration",
            settings_provider=FakeSettingsProvider(),
        )


@pytest.mark.parametrize("field", ["routers", "startup_hooks", "shutdown_hooks"])
def test_hosted_backend_extension_rejects_duplicate_registration(field: str) -> None:
    router = APIRouter()

    async def hook() -> None:
        return None

    values = {
        "routers": (router, router),
        "startup_hooks": (hook, hook),
        "shutdown_hooks": (hook, hook),
    }

    with pytest.raises(HostedExtensionConfigurationError):
        HostedBackendExtension(name="duplicate", **{field: values[field]})


def test_resident_runtime_boundary_fails_closed_without_adapter() -> None:
    previous = get_resident_runtime_adapter()
    if previous is not None:
        unregister_resident_runtime_adapter(previous)
    try:
        with pytest.raises(ResidentRuntimeUnavailableError):
            OpenClawGatewayClient()
        with pytest.raises(ResidentRuntimeUnavailableError):
            _ = openclaw_auth_profiles.OpenClawAuthProfileSyncError
    finally:
        if previous is not None:
            register_resident_runtime_adapter(previous)


def test_resident_runtime_boundary_uses_registered_adapter() -> None:
    previous = get_resident_runtime_adapter()
    if previous is not None:
        unregister_resident_runtime_adapter(previous)

    auth_profiles = type(
        "FakeAuthProfiles",
        (),
        {"OpenClawAuthProfileSyncError": RuntimeError},
    )()

    class FakeAdapter:
        name = "fake"

        def create_gateway_client(self, *args: object, **kwargs: object) -> object:
            return {"args": args, "kwargs": kwargs}

        def get_auth_profiles(self) -> object:
            return auth_profiles

    adapter = FakeAdapter()
    try:
        register_resident_runtime_adapter(adapter)
        client = OpenClawGatewayClient("gateway", timeout_seconds=3)
        assert client == {
            "args": ("gateway",),
            "kwargs": {"timeout_seconds": 3},
        }
        assert openclaw_auth_profiles.OpenClawAuthProfileSyncError is RuntimeError
    finally:
        unregister_resident_runtime_adapter(adapter)
        if previous is not None:
            register_resident_runtime_adapter(previous)


def test_public_runtime_defaults_are_safe() -> None:
    assert settings.agent_activity_engine == "langgraph"
    assert settings.server_llm_engine == "direct"
    assert settings.resident_tick_scheduler_enabled is False
    assert settings.post_image_job_worker_enabled is False
    assert settings.pollinations_service_image_enabled is False
    validate_public_runtime_settings()


@pytest.mark.parametrize(
    ("attribute", "value"),
    [
        ("AGENT_ACTIVITY_ENGINE", "openclaw"),
        ("SERVER_LLM_ENGINE", "openclaw"),
        ("RESIDENT_TICK_SCHEDULER_ENABLED", True),
        ("POST_IMAGE_JOB_WORKER_ENABLED", True),
        ("POLLINATIONS_SERVICE_IMAGE_ENABLED", True),
    ],
)
def test_public_runtime_rejects_unsafe_settings(
    monkeypatch: pytest.MonkeyPatch,
    attribute: str,
    value: object,
) -> None:
    monkeypatch.setattr(settings, attribute, value)

    with pytest.raises(PublicRuntimeConfigurationError):
        validate_public_runtime_settings()
