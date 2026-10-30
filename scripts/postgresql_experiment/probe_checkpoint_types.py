"""Inspect serialization tags without importing or constructing payload types."""
import collections,json,sqlite3
from pathlib import Path
import ormsgpack
counts=collections.Counter();errors=0
def hook(code,data):
    global errors
    try:
        value=ormsgpack.unpackb(data,ext_hook=hook)
        if isinstance(value,(list,tuple)) and len(value)>=2 and all(isinstance(x,str) for x in value[:2]):
            counts[(code,value[0],value[1])]+=1
    except (ValueError,TypeError):errors+=1
    return None
root=Path('/experiment/migration/D1/runtime/activity/activity-checkpoints.sqlite')
db=sqlite3.connect(root.as_uri()+'?mode=ro',uri=True)
for table,column in [('checkpoints','checkpoint'),('writes','value')]:
    for kind,value in db.execute('SELECT type,'+column+' FROM '+table):
        if kind=='msgpack':ormsgpack.unpackb(value,ext_hook=hook)
        elif kind not in {'json','null','bytes'}:raise ValueError('unsupported_serialization')
print(json.dumps({'types':[{'code':k[0],'module':k[1],'name':k[2],'occurrences':v} for k,v in sorted(counts.items())],'opaque_extensions':errors}))
