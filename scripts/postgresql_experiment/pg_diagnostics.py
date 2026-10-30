"""Explicit PG offline diagnostic counterpart; never opens legacy SQLite paths."""
import argparse,json
from pathlib import Path
import psycopg
from app.runtime.postgresql_backend import install_validation_guards
from app.runtime.postgresql_experiment import build_config,validate_config
from app.runtime.diagnostics.postgresql_snapshot import scheduler_snapshot,memory_snapshot


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--dsn-file',type=Path,required=True);p.add_argument('--data-root',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    install_validation_guards();dsn=a.dsn_file.read_text().strip();validate_config(build_config(a.data_root,dsn))
    with psycopg.connect(dsn.replace('postgresql+psycopg://','postgresql://',1)) as db:
        db.execute('SET TRANSACTION READ ONLY')
        scopes=db.execute('SELECT world_id,array_agg(id ORDER BY id) FROM world_characters GROUP BY world_id LIMIT 100').fetchall()
    reports=[]
    for world,actors in scopes:
        scope={'world_id':world,'actor_ids':actors}
        reports.append({'scheduler':scheduler_snapshot(a.data_root,scope,dsn=dsn),'memory':memory_snapshot(a.data_root,scope,dsn=dsn)})
    value={'persistence':'postgresql','reports':reports,'sqlite_access':'denied'}
    with a.output.open('x') as f:json.dump(value,f,default=str,indent=2)
    print(json.dumps({'worlds':len(reports),'scheduler_status':[r['scheduler']['scheduler_snapshot'] for r in reports],
        'memory_status':[r['memory']['status'] for r in reports],'sqlite_access':'denied'}))
    raise SystemExit(2 if any(r['scheduler']['scheduler_snapshot']!='ready' or r['memory']['status']!='ok' for r in reports) else 0)
