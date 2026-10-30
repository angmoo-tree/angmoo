"""Explicit local-only experiment composition. Official profiles remain embedded."""
import json
from pathlib import Path
from urllib.parse import urlsplit
from sqlalchemy import text

from app.runtime.postgresql_configuration import RUN_ID, SOURCE_SHA, validate_experiment_config as validate_config




def build_config(data_root, dsn, *, frontend_origin='http://127.0.0.1:13114', validation_mode=False):
    from app.runtime.configuration_contracts import RuntimeConfig, RuntimeProfile, RuntimeGraphProvider, RuntimeComponentMode
    from app.runtime.persistence.runtime_data_path import StaticRuntimeDataPath
    paths = StaticRuntimeDataPath(Path(data_root)).resolve()
    return RuntimeConfig(profile=RuntimeProfile.EXPERIMENT_POSTGRESQL, data_paths=paths,
        generation='postgresql-v1', database_url=dsn, app_secret_file=paths.secrets/'app-secret',
        graph_provider=RuntimeGraphProvider.LADYBUG, graph_database_root=paths.graph/'ladybug',
        graph_projection_enabled=True, component_mode=RuntimeComponentMode.IN_PROCESS,
        desktop_allowed_origin=frontend_origin, desktop_launch_token='', validation_mode=validation_mode)


def compose(config, runtime_settings):
    from app.runtime.postgresql_runtime import compose as compose_postgresql
    return compose_postgresql(config, runtime_settings)



def validation_components(settings, session_factory):
    from app.runtime.postgresql_runtime import validation_components as create_components
    return create_components(settings, session_factory)
