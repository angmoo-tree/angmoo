from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from dataclasses import dataclass
from typing import Any

import uvicorn
from fastapi import APIRouter, FastAPI

from app.api.v1.public import create_public_api_router
from app.core.config import settings
from app.core.db import SessionLocal, get_db
from app.core.request_limits import RequestBodyLimitMiddleware
from app.core.public_media import mount_public_media
from app.core.startup_security import validate_startup_security
from app.cruds.community import seed_demo_data
from app.services.hosted_configuration import (
    HostedConfigurationRegistrationError,
    HostedPromptProvider,
    HostedSettingsProvider,
    register_hosted_configuration,
    unregister_hosted_configuration,
)
from app.runtime.single_backend_components import (
    SingleBackendRuntimeComponents,
    create_single_backend_runtime_components,
)
from app.runtime.configuration import (
    RuntimeComposition,
    RuntimeConfig,
    compose_runtime,
)


class PublicRuntimeConfigurationError(RuntimeError):
    pass


class HostedExtensionConfigurationError(RuntimeError):
    pass


HostedLifecycleHook = Callable[[], Awaitable[None]]
LifespanHandler = Callable[
    [FastAPI],
    AbstractAsyncContextManager[None],
]


@dataclass(frozen=True)
class HostedBackendExtension:
    name: str
    routers: tuple[APIRouter, ...] = ()
    startup_hooks: tuple[HostedLifecycleHook, ...] = ()
    shutdown_hooks: tuple[HostedLifecycleHook, ...] = ()
    settings_provider: HostedSettingsProvider | None = None
    prompt_provider: HostedPromptProvider | None = None

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise HostedExtensionConfigurationError(
                "hosted extension name is required"
            )
        _reject_duplicates("router", self.routers)
        _reject_duplicates("startup hook", self.startup_hooks)
        _reject_duplicates("shutdown hook", self.shutdown_hooks)
        if (self.settings_provider is None) != (
            self.prompt_provider is None
        ):
            raise HostedConfigurationRegistrationError(
                "hosted settings and prompt providers must be configured together"
            )


def _reject_duplicates(label: str, values: tuple[object, ...]) -> None:
    if len({id(value) for value in values}) != len(values):
        raise HostedExtensionConfigurationError(f"duplicate hosted {label}")


def validate_public_runtime_settings(config=settings) -> None:
    invalid: list[str] = []
    if config.agent_activity_engine != "langgraph":
        invalid.append("AGENT_ACTIVITY_ENGINE must be langgraph")
    if config.server_llm_engine != "direct":
        invalid.append("SERVER_LLM_ENGINE must be direct")
    if config.resident_tick_scheduler_enabled:
        invalid.append("RESIDENT_TICK_SCHEDULER_ENABLED must be false")
    if config.post_image_job_worker_enabled:
        invalid.append("POST_IMAGE_JOB_WORKER_ENABLED must be false")
    if config.POLLINATIONS_SERVICE_IMAGE_ENABLED:
        invalid.append("POLLINATIONS_SERVICE_IMAGE_ENABLED must be false")
    if config.signup_enabled:
        invalid.append("SIGNUP_ENABLED must be false")
    if invalid:
        raise PublicRuntimeConfigurationError("; ".join(invalid))


def create_lifespan(
    extension: HostedBackendExtension | None = None,
    *,
    security_validator: Callable[[], None] = validate_startup_security,
    session_factory: Callable[[], Any] = SessionLocal,
    demo_seed: Callable[[Any], None] = seed_demo_data,
    component_manager_factory: Callable[
        [], SingleBackendRuntimeComponents | None
    ] = create_single_backend_runtime_components,
    runtime_settings=settings,
    runtime_disposer: Callable[[], None] | None = None,
) -> LifespanHandler:
    @asynccontextmanager
    async def runtime_lifespan(_: FastAPI) -> AsyncIterator[None]:
        configuration_registered = False
        component_manager = component_manager_factory()
        if extension is None:
            validate_public_runtime_settings(runtime_settings)
        security_validator()
        if runtime_settings.seed_demo_data:
            with session_factory() as db:
                demo_seed(db)

        if extension is not None:
            if (
                extension.settings_provider is not None
                and extension.prompt_provider is not None
            ):
                register_hosted_configuration(
                    extension.settings_provider,
                    extension.prompt_provider,
                )
                configuration_registered = True
            try:
                for hook in extension.startup_hooks:
                    await hook()
            except BaseException:
                try:
                    for hook in reversed(extension.shutdown_hooks):
                        await hook()
                finally:
                    if configuration_registered:
                        unregister_hosted_configuration(
                            extension.settings_provider,
                            extension.prompt_provider,
                        )
                raise
        try:
            if component_manager is not None:
                await component_manager.start()
        except BaseException:
            try:
                if component_manager is not None:
                    await component_manager.stop()
            finally:
                if extension is not None:
                    for hook in reversed(extension.shutdown_hooks):
                        await hook()
                if configuration_registered:
                    unregister_hosted_configuration(
                        extension.settings_provider,
                        extension.prompt_provider,
                    )
                if runtime_disposer is not None:
                    runtime_disposer()
            raise
        try:
            yield
        finally:
            try:
                if component_manager is not None:
                    await component_manager.stop()
            finally:
                if extension is not None:
                    try:
                        for hook in reversed(extension.shutdown_hooks):
                            await hook()
                    finally:
                        if configuration_registered:
                            unregister_hosted_configuration(
                                extension.settings_provider,
                                extension.prompt_provider,
                            )
                if runtime_disposer is not None:
                    runtime_disposer()

    return runtime_lifespan


lifespan = create_lifespan()


def create_app(
    extension: HostedBackendExtension | None = None,
    *,
    lifespan_handler: LifespanHandler | None = None,
    runtime_config: RuntimeConfig | None = None,
) -> FastAPI:
    composition: RuntimeComposition | None = None
    runtime_settings = settings
    runtime_lifespan = lifespan_handler
    if runtime_config is not None:
        runtime_config.require_public_runtime()
        composition = compose_runtime(runtime_config, base_settings=settings)
        runtime_settings = composition.settings
        if runtime_lifespan is None:
            runtime_lifespan = create_lifespan(
                extension,
                security_validator=lambda: validate_startup_security(
                    runtime_settings
                ),
                session_factory=composition.session_factory,
                component_manager_factory=lambda: (
                    create_single_backend_runtime_components(
                        runtime_settings,
                        session_factory=composition.session_factory,
                    )
                ),
                runtime_settings=runtime_settings,
                runtime_disposer=composition.dispose,
            )
    runtime_app = FastAPI(
        title=runtime_settings.project_name,
        lifespan=runtime_lifespan or create_lifespan(extension),
        docs_url="/docs" if runtime_settings.api_docs_enabled else None,
        redoc_url="/redoc" if runtime_settings.api_docs_enabled else None,
        openapi_url=(
            "/openapi.json" if runtime_settings.api_docs_enabled else None
        ),
    )
    runtime_app.add_middleware(RequestBodyLimitMiddleware)
    runtime_app.include_router(
        create_public_api_router(extension.routers if extension else ()),
        prefix=runtime_settings.api_v1_prefix,
    )
    mount_public_media(runtime_app, runtime_settings)
    runtime_app.state.runtime_settings = runtime_settings
    runtime_app.state.runtime_config = runtime_config
    runtime_app.state.runtime_composition = composition
    if composition is not None:

        def runtime_database_dependency():
            db = composition.session_factory()
            try:
                yield db
            finally:
                db.close()

        runtime_app.dependency_overrides[get_db] = runtime_database_dependency
    runtime_app.add_api_route("/health", health, methods=["GET"])
    return runtime_app


def health() -> dict[str, str]:
    return {"status": "ok"}


app = create_app(lifespan_handler=lifespan)


def main() -> None:
    uvicorn.run("app.public_main:app", host="0.0.0.0", port=8080, reload=True)


if __name__ == "__main__":
    main()
