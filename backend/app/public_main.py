from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from dataclasses import dataclass
import logging
from typing import Any

import uvicorn
from fastapi import APIRouter, FastAPI, HTTPException, Request, status
from sqlalchemy import text

from app.api.v1.public import create_public_api_router
from app.config import Settings, settings
from app.core.db import SessionLocal, get_db
from app.core.request_limits import RequestBodyLimitMiddleware
from app.core.public_media import mount_public_media
from app.core.startup_security import validate_startup_security
from app.cruds.community import seed_demo_data
from app.domains.world_characters.public import (
    reconcile_local_autonomous_runtime_modes,
)
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


logger = logging.getLogger(__name__)


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
            raise HostedExtensionConfigurationError("hosted extension name is required")
        _reject_duplicates("router", self.routers)
        _reject_duplicates("startup hook", self.startup_hooks)
        _reject_duplicates("shutdown hook", self.shutdown_hooks)
        if (self.settings_provider is None) != (self.prompt_provider is None):
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
    ] = lambda: None,
    startup_recovery: Callable[[], None] = lambda: None,
    runtime_settings=settings,
    runtime_disposer: Callable[[], None] | None = None,
    memory_runtime=None,
) -> LifespanHandler:
    @asynccontextmanager
    async def runtime_lifespan(runtime_app: FastAPI) -> AsyncIterator[None]:
        configuration_registered = False
        component_manager = component_manager_factory()
        coordinator = getattr(runtime_app.state, "memory_shutdown", None)
        if coordinator is not None and component_manager is not None:
            coordinator.quiesce = getattr(component_manager, "quiesce_scheduler", None)
        if extension is None:
            validate_public_runtime_settings(runtime_settings)
        security_validator()
        if runtime_settings.seed_demo_data:
            with session_factory() as db:
                demo_seed(db)
        startup_recovery()

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
            if memory_runtime is not None:
                await memory_runtime.start()
        except BaseException:
            try:
                if memory_runtime is not None:
                    await memory_runtime.stop()
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
                if memory_runtime is not None:
                    await memory_runtime.stop()
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
    prepare_media_directories: bool = True,
) -> FastAPI:
    composition: RuntimeComposition | None = None
    world_package_import_committer = None
    runtime_settings = settings
    runtime_lifespan = lifespan_handler
    process_settings_snapshot: dict[str, object] | None = None
    memory_runtime = None
    if runtime_config is not None:
        composition = compose_runtime(runtime_config, base_settings=settings)
        from app.runtime.memory.batch_runtime import MemoryBatchRuntime
        from app.runtime.memory_selection_provider import memory_provider

        memory_runtime = MemoryBatchRuntime(
            composition.session_factory,
            lambda owner, model: memory_provider(
                composition.session_factory, owner, model
            ),
        )
        runtime_settings = composition.settings
        from app.domains.world_packages.infrastructure.filesystem_import_media import (
            FilesystemWorldPackageImportMedia,
        )
        from app.domains.world_packages.infrastructure.sqlalchemy_import_commit import (
            SqlAlchemyWorldPackageImportCommitter,
        )

        world_package_import_committer = SqlAlchemyWorldPackageImportCommitter(
            composition.session_factory,
            media=FilesystemWorldPackageImportMedia(
                media_root=runtime_config.data_paths.media,
                runtime_root=runtime_config.data_paths.runtime,
                media_url_path=runtime_settings.media_url_path,
            ),
        )
        # Existing service modules retain a reference to the process Settings
        # singleton. Materialize the typed profile into that object without
        # consulting or rewriting parent-shell environment variables.
        process_settings_snapshot = settings.model_dump()
        for field_name in Settings.model_fields:
            setattr(settings, field_name, getattr(runtime_settings, field_name))

        def dispose_runtime() -> None:
            composition.dispose()
            assert process_settings_snapshot is not None
            for field_name in Settings.model_fields:
                setattr(
                    settings,
                    field_name,
                    process_settings_snapshot[field_name],
                )

        def recover_embedded_runtime() -> None:
            world_package_import_committer.recover_media()
            repair_result = reconcile_local_autonomous_runtime_modes(
                composition.session_factory,
                excluded_world_ids=(
                    world_package_import_committer.list_imported_world_ids()
                ),
            )
            logger.info(
                "autonomous_runtime_mode_reconciliation_completed "
                "scanned_count=%s repaired_count=%s skipped_count=%s",
                repair_result.scanned_count,
                repair_result.repaired_count,
                sum(count for _reason, count in repair_result.skipped_reasons),
            )
            composition.social_search_projection.start()
            composition.memory_recall_projection.start()

        if runtime_lifespan is None:
            runtime_lifespan = create_lifespan(
                extension,
                security_validator=lambda: validate_startup_security(runtime_settings),
                session_factory=composition.session_factory,
                component_manager_factory=lambda: (
                    create_single_backend_runtime_components(
                        runtime_settings,
                        session_factory=composition.session_factory,
                    )
                ),
                startup_recovery=recover_embedded_runtime,
                runtime_settings=runtime_settings,
                runtime_disposer=dispose_runtime,
                memory_runtime=memory_runtime,
            )
    runtime_app = FastAPI(
        title=runtime_settings.project_name,
        lifespan=runtime_lifespan or create_lifespan(extension),
        docs_url="/docs" if runtime_settings.api_docs_enabled else None,
        redoc_url="/redoc" if runtime_settings.api_docs_enabled else None,
        openapi_url=("/openapi.json" if runtime_settings.api_docs_enabled else None),
    )
    runtime_app.add_middleware(RequestBodyLimitMiddleware)
    runtime_app.include_router(
        create_public_api_router(extension.routers if extension else ()),
        prefix=runtime_settings.api_v1_prefix,
    )
    mount_public_media(
        runtime_app,
        runtime_settings,
        prepare_directories=prepare_media_directories,
    )
    runtime_app.state.runtime_settings = runtime_settings
    runtime_app.state.runtime_config = runtime_config
    runtime_app.state.runtime_composition = composition
    runtime_app.state.memory_batch_runtime = memory_runtime
    if memory_runtime is not None:
        from app.runtime.memory.shutdown import (
            MemoryShutdownCoordinator,
            MemoryShutdownAdmissionMiddleware,
        )

        runtime_app.state.memory_shutdown = MemoryShutdownCoordinator(memory_runtime)
        runtime_app.add_middleware(
            MemoryShutdownAdmissionMiddleware,
            coordinator=runtime_app.state.memory_shutdown,
        )
    runtime_app.state.world_package_import_committer = world_package_import_committer
    runtime_app.state.restore_process_settings = (
        dispose_runtime if composition is not None else None
    )
    if composition is not None:

        def runtime_database_dependency():
            db = composition.session_factory()
            try:
                yield db
            finally:
                db.close()

        runtime_app.dependency_overrides[get_db] = runtime_database_dependency
    runtime_app.add_api_route("/health", runtime_health, methods=["GET"])
    return runtime_app


def health() -> dict[str, str]:
    return {"status": "ok"}


def runtime_health(request: Request) -> dict[str, object]:
    """Bounded, privacy-safe readiness for the composed embedded runtime."""

    composition = getattr(request.app.state, "runtime_composition", None)
    runtime_config = getattr(request.app.state, "runtime_config", None)
    if composition is None or runtime_config is None:
        return health()

    try:
        with composition.session_factory() as db:
            db.execute(text("SELECT 1")).scalar_one()

        from app.domains.runtime.public import (
            RuntimeComponentState,
            component_observations,
        )
        from app.runtime.component_workers import (
            borrow_runtime_graph_client,
        )

        observations = {item.name: item for item in component_observations.snapshot()}
        allowed = {
            RuntimeComponentState.READY,
            RuntimeComponentState.RUNNING,
            RuntimeComponentState.DEGRADED,
        }
        for component in ("scheduler", "projector"):
            observed = observations.get(component)
            if observed is None or observed.state not in allowed:
                raise RuntimeError(f"{component}_not_ready")

        graph = borrow_runtime_graph_client(composition.settings)
        if graph is None:
            raise RuntimeError("ladybug_not_ready")
        graph.verify_connectivity()
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="embedded_runtime_not_ready",
        ) from exc

    return {
        "status": "ok",
        "profile": runtime_config.profile.value,
        "persistence": "sqlite",
        "graph": "ladybug",
        "components": {
            name: observations[name].state.value for name in ("scheduler", "projector")
        },
    }


app = create_app(
    lifespan_handler=lifespan,
    prepare_media_directories=False,
)


def main() -> None:
    uvicorn.run("app.public_main:app", host="0.0.0.0", port=8080, reload=True)


if __name__ == "__main__":
    main()
