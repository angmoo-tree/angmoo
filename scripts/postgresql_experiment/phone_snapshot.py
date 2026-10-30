"""Termux G4: whole quiescent D0 and writable D1, never mutate the installation."""
import argparse,hashlib,json,os,pathlib,shutil,subprocess,time
from guard import RUN_ID,SOURCE_SHA,owned_path,require_owned_root

ROOT=pathlib.Path.home()/'angmoo-pg-experiments/20261027-run01'
SOURCE=pathlib.Path.home()/'.local/share/angmoo/data'


def digest_file(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
    return h.hexdigest()


def manifest(root):
    rows=[]
    for p in sorted(root.rglob('*')):
        if p.is_symlink():raise ValueError('snapshot_link_refused')
        if p.is_file():rows.append({'path':p.relative_to(root).as_posix(),'size':p.stat().st_size,'sha256':digest_file(p)})
    return rows


def quiescent():
    result=subprocess.run(['angmoo','status'],capture_output=True,text=True,timeout=30,check=True)
    if json.loads(result.stdout)['state']!='stopped':raise ValueError('source_must_be_normally_stopped')
    for p in pathlib.Path('/proc').glob('[0-9]*'):
        try:
            if p.stat().st_uid!=os.getuid():continue
            for fd in (p/'fd').iterdir():
                try:target=os.readlink(fd)
                except OSError:continue
                if target.startswith(str(SOURCE)+'/'):raise ValueError('source_open_data_fd')
        except (FileNotFoundError,PermissionError):continue


def backup():
    base=require_owned_root(ROOT);quiescent()
    before=manifest(SOURCE)
    target=owned_path(base,'migration');target.mkdir(mode=0o700,exist_ok=True)
    if (target/'D0').exists() or (target/'D1').exists():raise ValueError('snapshot_destination_exists')
    required=sum(r['size'] for r in before)*4+1024**3
    if shutil.disk_usage(base).free<required:raise ValueError('snapshot_space_insufficient')
    shutil.copytree(SOURCE,target/'D0',copy_function=shutil.copy2)
    quiescent()
    if manifest(SOURCE)!=before or manifest(target/'D0')!=before:raise ValueError('snapshot_source_changed')
    digest=hashlib.sha256(json.dumps(before,separators=(',',':'),sort_keys=True).encode()).hexdigest()
    value={'run_id':RUN_ID,'source_sha':SOURCE_SHA,'migration_id':'termux-schema41-run01','source':str(SOURCE),
        'snapshot_digest':digest,'files':before,'created_at':time.time(),'state':'SNAPSHOT_READY'}
    (target/'snapshot.json').write_text(json.dumps(value,indent=2)+'\n')
    shutil.copytree(target/'D0',target/'D1',copy_function=shutil.copy2)
    if manifest(target/'D1')!=before:raise ValueError('working_copy_mismatch')
    for p in (target/'D0').rglob('*'):
        p.chmod(0o500 if p.is_dir() else 0o400)
    (target/'D0').chmod(0o500)
    value['state']='SOURCE_PREPARED';(target/'snapshot.json').write_text(json.dumps(value,indent=2)+'\n')
    return {'state':value['state'],'files':len(before),'bytes':sum(r['size'] for r in before),'snapshot_digest':digest}


if __name__=='__main__':
    os.umask(0o077)
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['backup','inspect']);a=parser.parse_args()
    if a.action=='backup':print(json.dumps(backup()))
    else:
        quiescent();rows=manifest(SOURCE);print(json.dumps({'state':'stopped','files':len(rows),'bytes':sum(r['size'] for r in rows)}))
