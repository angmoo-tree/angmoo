"""Fail closed before operating on this disposable local experiment's resources."""
from __future__ import annotations
import json
from pathlib import Path
import subprocess
from urllib.parse import urlsplit

RUN_ID = 'angmoo-pg-20261027-run01'
SOURCE_SHA = 'b1287c9be6b1480858f86a1235aea9730ff59468'
MARKER = '.angmoo-pg-experiment.json'
PORTS = {'postgres':15414,'backend':18114,'frontend':13114}

class GuardError(ValueError):
    pass

def require_owned_root(root: Path) -> Path:
    root = root.absolute()
    if any(p.is_symlink() or (hasattr(p,'is_junction') and p.is_junction()) for p in (root,*root.parents)):
        raise GuardError('experiment_symlink_refused')
    if not root.is_dir():
        raise GuardError('experiment_root_missing')
    if (root/MARKER).is_symlink():
        raise GuardError('experiment_marker_symlink_refused')
    try:
        marker=json.loads((root/MARKER).read_text(encoding='utf-8'))
    except (OSError,ValueError) as e:
        raise GuardError('experiment_owner_missing') from e
    if marker.get('run_id')!=RUN_ID or marker.get('source_sha')!=SOURCE_SHA:
        raise GuardError('experiment_owner_mismatch')
    return root.resolve()

def owned_path(root: Path, relative: str) -> Path:
    root=require_owned_root(root)
    part=Path(relative)
    if part.is_absolute() or '..' in part.parts:
        raise GuardError('experiment_path_escape')
    target=root/part
    if any(p.is_symlink() or (hasattr(p,'is_junction') and p.is_junction()) for p in (target,*target.parents)):
        raise GuardError('experiment_symlink_refused')
    if not target.resolve().is_relative_to(root):
        raise GuardError('experiment_path_escape')
    return target

def require_repository(root: Path) -> None:
    root=require_owned_root(root)
    def git(*args):
        return subprocess.check_output(['git','-C',str(root),*args],text=True).strip()
    if git('remote') or git('branch','--show-current')!='experiment/postgresql-termux':
        raise GuardError('experiment_git_boundary')
    if Path(git('rev-parse','--absolute-git-dir')).resolve()!=(root/'.git').resolve():
        raise GuardError('experiment_git_shared')
    if (root/'.git/objects/info/alternates').exists():
        raise GuardError('experiment_git_alternates')

def require_dsn(dsn: str) -> None:
    try:
        parsed=urlsplit(dsn)
        valid=(parsed.scheme in {'postgresql','postgresql+psycopg'} and parsed.hostname=='127.0.0.1'
               and parsed.port==PORTS['postgres'] and parsed.path in {'/angmoo_pg_run01','/angmoo_pg_run01_g1'}
               and parsed.username in {'angmoo_pg_run01','angmoo_pg_run01_admin'})
    except ValueError:
        valid=False
    if not valid:
        raise GuardError('experiment_dsn_refused')

def require_database_identity(connection) -> None:
    row=connection.execute('SELECT run_id, source_sha FROM angmoo_experiment_identity WHERE singleton = TRUE').fetchone()
    if row is None or tuple(row)!=(RUN_ID,SOURCE_SHA):
        raise GuardError('experiment_database_identity_mismatch')

def require_local_image(name: str) -> None:
    if not name.startswith('angmoo-pg-exp/') or '@' in name or ':' not in name or name.endswith(':latest'):
        raise GuardError('experiment_image_refused')
