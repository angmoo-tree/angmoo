from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from dataclasses import dataclass
from typing import Any

import uvicorn

from app.runtime.logging_config import configure_application_logging, uvicorn_logging_config
from fastapi import APIRouter, FastAPI

from app.api.v1.public import create_public_api_router
from app.config import settings
from app.core.db import SessionLocal
from app.core.request_limits import RequestBodyLimitMiddleware
from app.core.public_media import mount_public_media
from app.runtime.startup_security import validate_startup_security
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


def validate_public_runtime_settings() -> None:
    invalid: list[str] = []
    if settings.agent_activity_engine != "langgraph":
        invalid.append("AGENT_ACTIVITY_ENGINE must be langgraph")
    if settings.server_llm_engine != "direct":
        invalid.append("SERVER_LLM_ENGINE must be direct")
    if settings.resident_tick_scheduler_enabled:
        invalid.append("RESIDENT_TICK_SCHEDULER_ENABLED must be false")
    if settings.post_image_job_worker_enabled:
        invalid.append("POST_IMAGE_JOB_WORKER_ENABLED must be false")
    if settings.POLLINATIONS_SERVICE_IMAGE_ENABLED:
        invalid.append("POLLINATIONS_SERVICE_IMAGE_ENABLED must be false")
    if settings.signup_enabled:
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
) -> LifespanHandler:
    @asynccontextmanager
    async def runtime_lifespan(_: FastAPI) -> AsyncIterator[None]:
        configuration_registered = False
        component_manager = component_manager_factory()
        if extension is None:
            validate_public_runtime_settings()
        security_validator()
        if settings.seed_demo_data:
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

    return runtime_lifespan


lifespan = create_lifespan()


def create_app(
    extension: HostedBackendExtension | None = None,
    *,
    lifespan_handler: LifespanHandler | None = None,
) -> FastAPI:
    configure_application_logging()
    runtime_app = FastAPI(
        title=settings.project_name,
        lifespan=lifespan_handler or create_lifespan(extension),
        docs_url="/docs" if settings.api_docs_enabled else None,
        redoc_url="/redoc" if settings.api_docs_enabled else None,
        openapi_url="/openapi.json" if settings.api_docs_enabled else None,
    )
    from app.runtime.account_deletion import delete_current_user_account

    runtime_app.state.account_deletion_workflow = delete_current_user_account
    from app.runtime.characters.management import build_character_management_workflows
    runtime_app.state.character_management_workflows = build_character_management_workflows
    runtime_app.add_middleware(RequestBodyLimitMiddleware)
    runtime_app.include_router(
        create_public_api_router(extension.routers if extension else ()),
        prefix=settings.api_v1_prefix,
    )
    mount_public_media(runtime_app)
    runtime_app.add_api_route("/health", health, methods=["GET"])
    return runtime_app


def health() -> dict[str, str]:
    return {"status": "ok"}


app = create_app(lifespan_handler=lifespan)


def main() -> None:
    uvicorn.run("app.public_main:app", host="0.0.0.0", port=8080, reload=True, log_config=uvicorn_logging_config())


if __name__ == "__main__":
    main()
