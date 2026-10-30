"""Canonical PostgreSQL composition with installation-owned data and credentials."""
from app.runtime.postgresql_configuration import read_marker, validate_postgresql_config as validate_config
import json, re
from pathlib import Path
from urllib.parse import urlsplit
from sqlalchemy import text






def build_config(data_root, dsn, *, frontend_origin='http://127.0.0.1:3000', validation_mode=False, desktop_launch_token=''):
    from app.runtime.configuration_contracts import RuntimeConfig, RuntimeProfile, RuntimeGraphProvider, RuntimeComponentMode
    from app.runtime.persistence.runtime_data_path import StaticRuntimeDataPath
    paths = StaticRuntimeDataPath(Path(data_root)).resolve()
    return RuntimeConfig(profile=RuntimeProfile.LOCAL_POSTGRESQL if desktop_launch_token else RuntimeProfile.CONTRIBUTOR_POSTGRESQL,
        data_paths=paths,generation='postgresql-v5',database_url=dsn,app_secret_file=paths.secrets/'app-secret',
        graph_provider=RuntimeGraphProvider.LADYBUG,graph_database_root=paths.graph/'ladybug',graph_projection_enabled=True,
        component_mode=RuntimeComponentMode.IN_PROCESS,desktop_allowed_origin=frontend_origin,desktop_launch_token=desktop_launch_token,
        validation_mode=validation_mode)


def compose(config, runtime_settings):
    from app.runtime.persistence.postgresql_schema import metadata, VERSION
    metadata()  # Bind JSONB variants in this fresh serving process, without DDL.
    from app.database import create_database_engine, create_session_factory
    from app.runtime.composition_resources import RuntimeComposition
    from app.runtime.autonomous_activity.postgresql_checkpoints import PostgresCheckpointStore, register, unregister
    from app.runtime.memory.postgresql_recall import PostgresMemoryRecallIndex
    from app.runtime.memory.sqlite_fts5_recall import MemoryRecallIndexSettings
    from app.runtime.memory.postgresql_hybrid import PostgresMemoryHybridRuntime
    from app.runtime.memory.recall_projection import EmbeddedMemoryRecallProjection
    from app.runtime.search.postgresql_fts import PostgresFtsSearchIndex
    from app.runtime.search import EmbeddedSocialSearchProjection
    from app.domains.memory.service.recall import CanonicalRecallService
    from app.runtime.memory.recall_composition import canonical_recall_repository
    engine = create_database_engine(config.database_url)
    store = PostgresCheckpointStore(config.database_url)
    try:
        with engine.connect() as c:
            if config.profile.value == 'EXPERIMENT_POSTGRESQL':
                from app.runtime.postgresql_configuration import RUN_ID, SOURCE_SHA
                if tuple(c.execute(text('SELECT run_id,source_sha FROM angmoo_experiment_identity WHERE singleton=true')).one()) != (RUN_ID,SOURCE_SHA):
                    raise ValueError('postgresql_experiment_database_identity_mismatch')
            else:
                from app.runtime.persistence.postgresql_identity import verify
                verify(c, read_marker(config.data_paths.root)['installation_id'])
                role=c.execute(text('SELECT rolsuper,rolcreatedb,rolcreaterole,rolreplication,rolbypassrls FROM pg_roles WHERE rolname=current_user')).one()
                if any(role):raise ValueError('postgresql_runtime_role_privilege_mismatch')
            version = c.execute(text('SELECT version FROM angmoo_postgresql_schema_version')).scalar_one()
            if version != VERSION:
                raise ValueError('postgresql_experiment_schema_mismatch')
        factory = create_session_factory(engine)
        episode_only = runtime_settings.MEMORY_RECALL_REPRESENTATION == 'episode_v1'
        recall = PostgresMemoryRecallIndex(engine,
            settings=MemoryRecallIndexSettings.for_representation(runtime_settings.MEMORY_RECALL_REPRESENTATION),
            progress_path=config.data_paths.runtime/'postgresql-recall-progress.json')
        hybrid = PostgresMemoryHybridRuntime(factory, recall, config.data_paths,
            fts_policy=runtime_settings.CHAT_HYBRID_FTS_POLICY, episode_only=episode_only)
        hybrid.validation_mode = config.validation_mode
        register(config.data_paths.root, store)
        return RuntimeComposition(config=config, settings=runtime_settings, engine=engine, session_factory=factory,
            social_search_projection=EmbeddedSocialSearchProjection(index=PostgresFtsSearchIndex(engine), session_factory=factory),
            memory_recall_projection=EmbeddedMemoryRecallProjection(index=recall, session_factory=factory, episode_only=episode_only),
            memory_recall_service=CanonicalRecallService(canonical_recall_repository(factory), recall, hybrid_service=hybrid.service),
            memory_hybrid_runtime=hybrid, checkpoint_store=store,
            checkpoint_dispose=lambda: unregister(config.data_paths.root, store))
    except BaseException:
        unregister(config.data_paths.root, store)
        engine.dispose()
        raise


def validation_components(settings, session_factory):
    from functools import partial
    from app.runtime.single_backend_components import SingleBackendRuntimeComponents
    from app.runtime.component_workers import run_projector_component
    async def suspended_scheduler(stop_event, state_listener):
        state_listener('ready')
        await stop_event.wait()
    return SingleBackendRuntimeComponents(scheduler_runner=suspended_scheduler,
        projector_runner=partial(run_projector_component, config=settings, session_factory=session_factory))
