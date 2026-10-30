import json,sys
from pathlib import Path
from pg_fingerprint import comparable
a=comparable(json.loads(Path(sys.argv[1]).read_text()));b=comparable(json.loads(Path(sys.argv[2]).read_text()))
changed=[k for k in a if a[k]!=b.get(k)]
if changed:
    print(json.dumps({'definition_differences':{k:{'before':[x for x in a[k] if x not in b[k]][:2],'after':[x for x in b[k] if x not in a[k]][:2]} for k in changed if k in {'constraints','indexes','triggers'}}}))
print(json.dumps({'state':'VERIFIED' if not changed else 'FAILED','changed_categories':changed,
    'tables':len(a['tables']),'normalized_only':'varchar_constant_array_text_cast'}))
raise SystemExit(2 if changed else 0)
