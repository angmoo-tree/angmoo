"""Filesystem/DSN checks used before composition; no runtime factory imports."""
import json, re
from pathlib import Path
from urllib.parse import urlsplit

RUN_ID = 'angmoo-pg-20261027-run01'
SOURCE_SHA = 'b1287c9be6b1480858f86a1235aea9730ff59468'

def read_marker(root):
    marker = json.loads((Path(root)/'runtime/postgresql-runtime.json').read_text(encoding='utf-8'))
    if marker.get('schema') != 'angmoo-postgresql-runtime.v1':
        raise ValueError('postgresql_runtime_marker_invalid')
    from app.core.postgresql_identifiers import require_identifier
    require_identifier(marker['installation_id'])
    return marker



def validate_postgresql_config(config):
    root = config.data_paths.root
    if any(p.is_symlink() or (hasattr(p,'is_junction') and p.is_junction()) for p in (root,*root.parents)):
        raise ValueError('postgresql_data_link_refused')
    read_marker(root)
    uri = urlsplit(config.database_url)
    if uri.scheme != 'postgresql+psycopg' or not uri.hostname or not uri.username or not uri.password or not re.fullmatch(r'/[a-zA-Z0-9_]+',uri.path):
        raise ValueError('postgresql_runtime_dsn_invalid')
    if config.profile.value=='LOCAL_POSTGRESQL' and uri.hostname not in {'127.0.0.1','::1'}:
        raise ValueError('postgresql_desktop_loopback_required')
    if not config.app_secret_file.is_file():
        raise ValueError('postgresql_runtime_secret_missing')


def validate_experiment_config(config):
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
