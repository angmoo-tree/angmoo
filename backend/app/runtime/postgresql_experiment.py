"""Explicit local-only experiment composition. Official profiles remain embedded."""
import json
from pathlib import Path
from urllib.parse import urlsplit
from sqlalchemy import text

RUN_ID = 'angmoo-pg-20261027-run01'
SOURCE_SHA = 'b1287c9be6b1480858f86a1235aea9730ff59468'


def validate_config(config):
    root = config.data_paths.root
    if any(p.is_symlink() or (hasattr(p, 'is_junction') and p.is_junction()) for p in (root, *root.parents)):
        raise ValueError('postgresql_experiment_data_link_refused')
    marker = json.loads((root / 'runtime/postgresql-runtime.json').read_text())
    if (marker.get('run_id'), marker.get('source_sha')) != (RUN_ID, SOURCE_SHA):
        raise ValueError('postgresql_experiment_owner_mismatch')
    uri = urlsplit(config.database_url)
    if (uri.scheme != 'postgresql+psycopg' or uri.hostname != '127.0.0.1'
            or uri.port != 15414 or uri.path not in {'/angmoo_pg_run01', '/angmoo_pg_run01_restore'}
            or uri.username not in {'angmoo_pg_run01_admin','angmoo_pg_run01_runtime'}):
        raise ValueError('postgresql_experiment_dsn_refused')
    if not config.app_secret_file.is_file():
        raise ValueError('postgresql_experiment_secret_missing')


def build_config(data_root, dsn, *, frontend_origin='http://127.0.0.1:13114', validation_mode=False):
    from app.runtime.configuration import RuntimeConfig, RuntimeProfile, RuntimeGraphProvider, RuntimeComponentMode
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
