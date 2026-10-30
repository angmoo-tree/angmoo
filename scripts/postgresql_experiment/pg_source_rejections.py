"""Offline source-format rejection fixtures, exclusively under the trial root."""
import json,sqlite3
from pathlib import Path
from app.runtime.postgresql_migration import inspect_source,files

root=Path('/experiment/migration/rejection-fixtures')
root.mkdir()
result=[]
for name,version in [('older-schema',40),('future-schema',42),('corrupt-file',None)]:
    data=root/name;path=data/'canonical/generations/fixture/angmoo.sqlite3';path.parent.mkdir(parents=True)
    if version is None:path.write_bytes(b'synthetic malformed sqlite')
    else:
        with sqlite3.connect(path) as db:
            db.execute('CREATE TABLE angmoo_schema_version(schema_version,source_revision,source_migration_count)')
            db.execute('INSERT INTO angmoo_schema_version VALUES(?,?,?)',(version,'unvalidated',117))
    before=files(data)
    try:inspect_source(data)
    except ValueError as e:
        expected='migration_source_schema_unknown' if version is None else 'migration_source_schema_unsupported'
        if str(e)!=expected:raise
        result.append({'fixture':name,'reason':str(e),'source_unchanged':files(data)==before})
    else:raise AssertionError('unsupported source accepted')
print(json.dumps({'rejections':result,'postgres_writes':0}))
