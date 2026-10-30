"""Run the pinned ARM64 PostgreSQL image in a private Termux PRoot tree."""
from __future__ import annotations
import argparse,hashlib,json,os,pathlib,secrets,socket,subprocess,time
from guard import RUN_ID,SOURCE_SHA,require_owned_root,owned_path

ROOT=pathlib.Path.home()/'angmoo-pg-experiments/20261027-run01'
PORT=15414
ROLE='angmoo_pg_run01_admin'
# Size SSI metadata independently of the deliberately small connection pool.
# Keep the original per-relation promotion threshold (64 / 2 = 32): raising
# the pool must not silently increase each scan's fine-grained lock footprint.
PREDICATE_OPTIONS=('-c','max_pred_locks_per_transaction=256',
                   '-c','max_pred_locks_per_relation=32')
CAPACITY_OPTIONS=('-c','max_connections=28','-c','superuser_reserved_connections=3')

def root():return require_owned_root(ROOT)

def command(*args):
    base=root()
    mounts={'pgdata':'/var/lib/postgresql/data','socket':'/run/angmoo-pg',
            'secrets':'/run/angmoo-secrets','scripts':'/experiment-scripts','tmp':'/tmp','tmp/shm':'/dev/shm','.':'/experiment'}
    proot=owned_path(base,'tools/proot-playstore')
    build=json.loads(owned_path(base,'records/proot-build.json').read_text())
    assert hashlib.sha256(proot.read_bytes()).hexdigest()==build['binary_sha256']
    cmd=['/system/bin/linker64',str(proot),'--kill-on-exit','--link2symlink','--sysvipc','-k','6.17.0-PRoot-Distro','-i','999:999',
         '-r',str(owned_path(base,'rootfs')),'-b','/dev','-b','/proc','-b','/sys']
    for source,target in mounts.items():cmd+=['-b',str(owned_path(base,source))+':'+target]
    return cmd+['-w','/var/lib/postgresql','/usr/bin/env','-i',
       'PATH=/usr/lib/postgresql/17/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin',
       'HOME=/var/lib/postgresql','LANG=C.UTF-8','LC_ALL=C.UTF-8',
       'PGPASSFILE=/run/angmoo-secrets/pgpass','PGAPPNAME='+RUN_ID,*args]

def environment():
    env=dict(os.environ);env['PROOT_TMP_DIR']=str(root()/'tmp')
    # Termux's exec shim is for Android binaries, not the image's glibc loader.
    env.pop('LD_PRELOAD',None)
    env.pop('LD_LIBRARY_PATH',None)
    # Use PRoot's own IPC namespace. The shared libandroid-shmem helper assumes
    # /proc/self/exe names the program; Play Store Termux launches via linker64.
    env['PROOT_DONT_SHARE_LIBANDROID_SHMEM']='1'
    env['ANGMOO_PROOT_SELF_EXE']=str(owned_path(root(),'tools/proot-playstore'))
    return env

def run(*args,timeout=90,input=None):
    r=subprocess.run(command(*args),env=environment(),input=input,capture_output=True,text=True,timeout=timeout)
    return {'returncode':r.returncode,'stdout':r.stdout,'stderr':r.stderr}

def record(name,value):
    p=owned_path(root(),'records/'+name)
    p.write_text(json.dumps(value,indent=2)+'\n')

def identity(pid):
    fields=pathlib.Path(f'/proc/{pid}/stat').read_text().rsplit(')',1)[1].split()
    return {'pid':pid,'start_ticks':fields[19],'boot_id':pathlib.Path('/proc/sys/kernel/random/boot_id').read_text().strip()}

def verify_postmaster(pid):
    expected=owned_path(root(),'rootfs/usr/lib/postgresql/17/bin/postgres').resolve()
    mappings=pathlib.Path(f'/proc/{pid}/maps').read_text().splitlines()
    # Play Store Termux keeps the APK loader as /proc/PID/exe. Verify the
    # actual executable mapping, not that loader path alone.
    if not any('x' in line.split()[1] and line.split()[-1]==str(expected) for line in mappings):
        raise ValueError('postgres_executable_mapping_mismatch')
    return {'loader':os.readlink(f'/proc/{pid}/exe'),'mapped_postgres':str(expected)}

def init():
    base=root();data=owned_path(base,'pgdata')
    if any(data.iterdir()):raise ValueError('pgdata_not_empty')
    for name in ['secrets','socket','tmp','tmp/shm']:
        owned_path(base,name).mkdir(mode=0o700,parents=True,exist_ok=True)
    password_path=owned_path(base,'secrets/password')
    if not password_path.exists():
        password=secrets.token_urlsafe(32)
        for name,value in [('password',password+'\n'),('pgpass',f'127.0.0.1:{PORT}:*:{ROLE}:{password}\n')]:
            p=owned_path(base,'secrets/'+name)
            with p.open('x') as f:f.write(value)
            p.chmod(0o600)
    else:
        assert (base/'secrets/pgpass').is_file() and password_path.stat().st_mode&0o077==0
    version=run('postgres','--version');user=run('id')
    assert version['returncode']==0, version
    result=run('initdb','-D','/var/lib/postgresql/data','--username='+ROLE,
        '--pwfile=/run/angmoo-secrets/password','--auth-local=scram-sha-256','--auth-host=scram-sha-256',
        '--encoding=UTF8','--locale=C.UTF-8','--data-checksums',timeout=180)
    record('initdb.json',{'version':version,'user':user,'result':result})
    if result['returncode']:
        return {'status':'initdb_failed','version':version,'user':user,**result}
    config="""
# angmoo-pg-20261027-run01: experiment only
listen_addresses = '127.0.0.1'
port = 15414
unix_socket_directories = '/run/angmoo-pg'
shared_buffers = '64MB'
work_mem = '2MB'
maintenance_work_mem = '32MB'
autovacuum_work_mem = '16MB'
max_connections = 28
superuser_reserved_connections = 3
max_parallel_workers = 0
max_parallel_workers_per_gather = 0
max_parallel_maintenance_workers = 0
max_worker_processes = 2
autovacuum_max_workers = 1
huge_pages = off
dynamic_shared_memory_type = mmap
fsync = on
full_page_writes = on
synchronous_commit = on
autovacuum = on
max_wal_size = '256MB'
min_wal_size = '80MB'
log_min_duration_statement = 1000
log_line_prefix = '%m [%p] '
"""
    with (data/'postgresql.conf').open('a') as f:f.write(config)
    (data/'.angmoo-pg-experiment.json').write_text(json.dumps({'run_id':RUN_ID,'source_sha':SOURCE_SHA}))
    return {'status':'initialized','version':version,'user':user,**result}

def sql(statement,db='postgres',timeout=30):
    return run('psql','-X','-w','-h','127.0.0.1','-p',str(PORT),'-U',ROLE,'-d',db,
               '-v','ON_ERROR_STOP=1','-At','-c',statement,timeout=timeout)

def start():
    base=root();data=owned_path(base,'pgdata')
    assert json.loads((data/'.angmoo-pg-experiment.json').read_text())['run_id']==RUN_ID
    with socket.socket() as s:
        # PostgreSQL also uses SO_REUSEADDR. A closed connection in TIME_WAIT
        # is not a live foreign listener and must not prevent crash recovery.
        s.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
        s.bind(('127.0.0.1',PORT))
    old=base/'records/process.json'
    if old.exists():
        previous=json.loads(old.read_text())
        try:
            state=pathlib.Path(f"/proc/{previous['proot']['pid']}/stat").read_text().rsplit(')',1)[1].split()[0]
            if state!='Z' and identity(previous['proot']['pid'])==previous['proot']:raise ValueError('experiment_already_running')
        except FileNotFoundError:pass
    log=base/'logs/postgres.log'
    with log.open('ab',buffering=0) as f:
        p=subprocess.Popen(command('postgres','-D','/var/lib/postgresql/data',*PREDICATE_OPTIONS,*CAPACITY_OPTIONS),env=environment(),stdin=subprocess.DEVNULL,
            stdout=f,stderr=f,start_new_session=True)
    process={'run_id':RUN_ID,'proot':identity(p.pid)}
    record('process.json',process)
    deadline=time.monotonic()+50
    while time.monotonic()<deadline:
        if p.poll() is not None:return {'status':'start_failed','returncode':p.returncode,'log':log.read_text()[-10000:]}
        try:
            with socket.create_connection(('127.0.0.1',PORT),timeout=.5):pass
            ready=sql('SELECT version(), current_user, current_setting(\'data_directory\');')
            if ready['returncode']==0:
                pid=int((data/'postmaster.pid').read_text().splitlines()[0]);process['postgres']=identity(pid)
                process['executable_identity']=verify_postmaster(pid)
                record('process.json',process)
                return {'status':'ready','process':process,'probe':ready}
        except (OSError,subprocess.TimeoutExpired):pass
        time.sleep(.5)
    return {'status':'readiness_timeout','process':process,'log':log.read_text()[-10000:]}

def stop(crash=False):
    base=root();p=json.loads((base/'records/process.json').read_text())
    assert p['run_id']==RUN_ID and identity(p['postgres']['pid'])==p['postgres']
    verify_postmaster(p['postgres']['pid'])
    if crash:
        import signal
        os.kill(p['postgres']['pid'],signal.SIGKILL)
        result={'returncode':0,'mode':'SIGKILL_verified_experiment_postmaster'}
    else:result=run('pg_ctl','-D','/var/lib/postgresql/data','-m','fast','-w','-t','40','stop',timeout=50)
    deadline=time.monotonic()+10
    while time.monotonic()<deadline:
        try:
            fields=pathlib.Path(f"/proc/{p['proot']['pid']}/stat").read_text().rsplit(')',1)[1].split()
            if fields[0]=='Z':break
        except FileNotFoundError:break
        time.sleep(.2)
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['init','start','stop','crash','sql']);p.add_argument('statement',nargs='?');a=p.parse_args()
    os.umask(0o077)
    if a.action=='init':value=init()
    elif a.action=='start':value=start()
    elif a.action=='stop':value=stop()
    elif a.action=='crash':value=stop(crash=True)
    else:value=sql(a.statement)
    print(json.dumps(value,ensure_ascii=False,indent=2))
