"""Serving-process checkpoint binding; no dependency on a storage adapter."""
import os
from pathlib import Path
from threading import RLock

_stores = {}
_lock = RLock()

def _key(root):return os.path.normcase(str(Path(root).resolve()))



def register(root,store):
    with _lock:
        existing=_stores.get(_key(root))
        if existing is not None and existing is not store:raise ValueError('postgresql_checkpoint_root_already_bound')
        _stores[_key(root)]=store



def bound_store(root):
    with _lock:value=_stores.get(_key(root))
    if value is None and (Path(root)/'runtime/postgresql-runtime.json').exists():
        raise RuntimeError('postgresql_checkpoint_runtime_not_bound')
    return value



def unregister(root,store):
    with _lock:
        if _stores.get(_key(root)) is store:_stores.pop(_key(root))
