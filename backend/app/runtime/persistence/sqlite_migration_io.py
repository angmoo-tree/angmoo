"""Read-only legacy input and deterministic digests shared by migration stages."""
import base64, json, sqlite3
from contextlib import contextmanager
from datetime import datetime, date

@contextmanager
def source_db(path):
    if not path.is_file():raise ValueError('migration_source_missing')
    if any(p.is_symlink() or (hasattr(p,'is_junction') and p.is_junction()) for p in (path,*path.parents)):
        raise ValueError('migration_source_link_refused')
    db=sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True,timeout=.5)
    try:
        db.execute('PRAGMA query_only=ON')
        db.execute('BEGIN')
        yield db
    finally:db.close()



def canonical_path(root):
    pointer=root/'canonical/current-generation.json'
    if pointer.exists():
        value=json.loads(pointer.read_text(encoding='utf-8'))
        generation=value.get('generation','')
        if (value.get('schema_version')!=1 or value.get('data_version')!=41
                or not __import__('re').fullmatch(r'[A-Za-z0-9_-]+',generation)
                or value.get('relative_path')!='generations/'+generation):
            raise ValueError('migration_canonical_pointer_invalid')
        candidate=root/'canonical/generations'/generation/'angmoo.sqlite3'
        if not candidate.is_file():raise ValueError('migration_canonical_generation_missing')
        return candidate
    candidates=list((root/'canonical/generations').glob('*/angmoo.sqlite3'))
    if len(candidates)!=1:raise ValueError('migration_canonical_generation_ambiguous')
    return candidates[0]



def normalized(value):
    if isinstance(value,(datetime,date)):return value.isoformat()
    if isinstance(value,(bytes,memoryview)):return {'binary':base64.b64encode(value).decode()}
    if isinstance(value,dict):return {k:normalized(v) for k,v in value.items()}
    if isinstance(value,(list,tuple)):return [normalized(v) for v in value]
    return value



def add_digest(hasher,row):
    hasher.update(json.dumps(normalized(row),sort_keys=True,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode())
    hasher.update(b'\n')
