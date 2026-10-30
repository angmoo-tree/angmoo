"""Private PostgreSQL host state and offline conversion through the image CLI."""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import secrets
import shlex
import subprocess
import time
from urllib.parse import quote
from uuid import uuid4
from processes import atomic_json, identity, stop_child
from payload import require


def temporary_directory(install):
    home=Path(install['home']).resolve()
    # PRoot's IPC helper uses Unix socket paths (108 bytes on Linux). A custom
    # installation home may be arbitrarily long; keep only disposable IPC
    # state in a short private directory, with an explicit ownership marker.
    path=(Path.home()/'.cache/angmoo-pg'/hashlib.sha256(str(home).encode()).hexdigest()[:12]
        if install.get('proot_wrapper') else home/'postgresql-tmp')
    require(not any(p.is_symlink() for p in (path,*path.parents)),'postgresql_ipc_link_refused')
    path.mkdir(mode=0o700,parents=True,exist_ok=True)
    path.chmod(0o700)
    marker=path/'owner.json';value={'schema':'angmoo-termux-ipc.v1','home':str(home)}
    if marker.exists():require(json.loads(marker.read_text())==value,'postgresql_ipc_owner_mismatch')
    else:atomic_json(marker,value)
    return path


def prepare_tool(home):
    # Other Termux distributions can use their packaged PRoot. Play Store
    # Android forbids /proc/self/exe; use the pinned, private helper recipe.
    if not Path('/data/data/com.termux/files/applib/libproot-loader.so').exists():return None
    binary=home/'tools/proot-playstore'
    record=home/'records/proot-build.json'
    if not binary.exists():
        from prepare_proot import build
        build(home)
    receipt=json.loads(record.read_text())
    require(hashlib.file_digest(binary.open('rb'),'sha256').hexdigest()==receipt['binary_sha256'],'proot_binary_hash_mismatch')
    require(receipt['source_sha256']=='a66743f50c7b0bac1913b83bf55e139d679c80a0ca2808eec76432a65640017f','proot_source_digest_mismatch')
    wrapper=home/'tools/proot-wrapper'
    body='#!/data/data/com.termux/files/usr/bin/sh\nexec /system/bin/linker64 '+shlex.quote(str(binary))+' "$@"\n'
    if wrapper.exists():require(wrapper.read_text()==body,'proot_wrapper_mismatch')
    else:wrapper.write_text(body);wrapper.chmod(0o700)
    return wrapper


def host_environment(install):
    env=dict(os.environ)
    wrapper=install.get('proot_wrapper')
    if wrapper:
        env['PD_PROOT_BIN']=wrapper
        env['ANGMOO_PROOT_SELF_EXE']=str(Path(wrapper).parent/'proot-playstore')
        # PRoot-Distro separates the host LD_* environment from the guest.
        # Keep Termux's host exec shim: Android needs it to execute the private
        # wrapper. Its variables are not passed to the glibc application.
        env['PROOT_DONT_SHARE_LIBANDROID_SHMEM']='1'
        env['PROOT_TMP_DIR']=str(temporary_directory(install))
    return env


def prepare(home,ports=None):
    marker=home/'postgresql.json'
    initialized=(home/'postgresql-data/PG_VERSION').exists()
    require(not initialized or marker.is_file(),'postgresql_identity_missing')
    value=json.loads(marker.read_text()) if marker.exists() else {
        'schema':'angmoo-termux-postgresql.v1','installation_id':'angmoo-'+uuid4().hex,
        'ports':ports or {'postgres':5432,'backend':8080,'frontend':3000}}
    require(value.get('schema')=='angmoo-termux-postgresql.v1','postgresql_identity_invalid')
    if ports:require(value['ports']==ports,'postgresql_ports_changed')
    credentials=home/'credentials';credentials.mkdir(mode=0o700,exist_ok=True)
    require(not initialized or all((credentials/name).is_file() for name in
        ('postgres-password','runtime-password','owner-dsn','runtime-dsn')),'postgresql_credentials_missing')
    for name in ('postgres-password','runtime-password'):
        path=credentials/name
        if not path.exists():
            with path.open('x') as stream:stream.write(secrets.token_urlsafe(48)+'\n')
        path.chmod(0o600)
    for name,user,pwfile in (('owner-dsn','angmoo_owner','postgres-password'),('runtime-dsn','angmoo_runtime','runtime-password')):
        path=credentials/name
        body='postgresql+psycopg://'+user+':'+quote((credentials/pwfile).read_text().strip(),safe='')+'@127.0.0.1:'+str(value['ports']['postgres'])+'/angmoo\n'
        if path.exists():require(path.read_text()==body,'postgresql_credentials_changed')
        else:path.write_text(body);path.chmod(0o600)
    for name in ('postgresql-data','postgresql-tmp'):(home/name).mkdir(mode=0o700,exist_ok=True)
    atomic_json(marker,value)
    return value


def options(executable,install,service,*,user=None):
    user=user or ('postgres' if service=='postgres' else '10001:10001')
    result=[executable,'run',install['containers'][service],'--user',user,'--isolated']
    wrapper=install.get('proot_wrapper')
    if wrapper:result+=['--env','ANGMOO_PROOT_SELF_EXE='+str(Path(wrapper).parent/'proot-playstore'),
        '--env','PROOT_DONT_SHARE_LIBANDROID_SHMEM=1','--env','PROOT_TMP_DIR='+str(temporary_directory(install))]
    return result


def command(executable,install):
    home=Path(install['home']);state=prepare(home,install.get('ports'));port=state['ports']['postgres']
    return options(executable,install,'postgres')+[
        '--bind',str(home/'postgresql-data')+':/var/lib/postgresql/data',
        '--bind',str(temporary_directory(install))+':/tmp',
        '--bind',str(temporary_directory(install))+':/dev/shm',
        '--bind',str(temporary_directory(install))+':/var/run/postgresql',
        '--bind',str(home/'credentials')+':/run/angmoo-secrets',
        '--env','PGDATA=/var/lib/postgresql/data','--env','POSTGRES_USER=angmoo_owner','--env','POSTGRES_DB=angmoo',
        '--env','PGHOST=/tmp','--env','POSTGRES_INITDB_ARGS=--auth-local=scram-sha-256 --auth-host=scram-sha-256 --locale=C.UTF-8',
        '--env','POSTGRES_PASSWORD_FILE=/run/angmoo-secrets/postgres-password','--',
        'postgres','-p',str(port),'-c','listen_addresses=127.0.0.1','-c','unix_socket_directories=/var/run/postgresql',
        '-c','max_connections=28','-c','shared_buffers=64MB','-c','work_mem=4MB',
        '-c','dynamic_shared_memory_type=mmap','-c','huge_pages=off',
        '-c','max_parallel_workers=0','-c','max_parallel_workers_per_gather=0','-c','max_worker_processes=2',
        '-c','autovacuum_max_workers=1','-c','maintenance_work_mem=32MB','-c','autovacuum_work_mem=16MB',
        '-c','max_wal_size=256MB','-c','min_wal_size=80MB','-c','max_pred_locks_per_relation=32',
        '-c','max_pred_locks_per_transaction=256','-c','log_min_error_statement=panic','-c','log_error_verbosity=terse']


def wait_ready(executable,install,process,cancelled=lambda:False):
    port=prepare(Path(install['home']))['ports']['postgres']
    args=options(executable,install,'postgres')+['--','pg_isready','-h','127.0.0.1','-p',str(port),'-U','angmoo_owner','-d','angmoo']
    deadline=time.monotonic()+120
    while time.monotonic()<deadline:
        require(not cancelled(),'start_cancelled')
        require(process.poll() is None,'service_exited_before_ready')
        if subprocess.run(args,env=host_environment(install),stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=15).returncode==0:return
        time.sleep(1)
    raise ValueError('postgresql_readiness_timeout')


def common(executable,install,action,*args):
    home=Path(install['home'])
    command=options(executable,install,'backend')+['--bind',str(home)+':/migration',
        '--bind',install['data_root']+':/var/lib/angmoo','--','postgresql-installation',action,*args]
    result=subprocess.run(command,env=host_environment(install),capture_output=True,text=True,timeout=1800)
    if result.returncode:
        directory=home/'migration';directory.mkdir(mode=0o700,exist_ok=True)
        path=directory/(action+'-error.log')
        path.write_text(result.stdout+'\n'+result.stderr);path.chmod(0o600)
    require(result.returncode==0,'postgresql_'+action+'_failed')
    return result.stdout


def initialize(executable,install):
    home=Path(install['home'])
    if (Path(install['data_root'])/'runtime/postgresql-runtime.json').exists():return
    state=prepare(home)
    common(executable,install,'initialize','--data-root','/var/lib/angmoo','--installation-id',state['installation_id'],
        '--owner-dsn-file','/migration/credentials/owner-dsn','--runtime-dsn-file','/migration/credentials/runtime-dsn')


def stop(executable,install,owner=None):
    home=Path(install['home'])
    if not (home/'postgresql-data/postmaster.pid').exists():return
    pid=int((home/'postgresql-data/postmaster.pid').read_text().splitlines()[0])
    if not (Path('/proc')/str(pid)).exists():return
    from processes import session_members
    require(owner is not None and any(row['pid']==pid for row in session_members(owner)), 'postgresql_process_owner_mismatch')
    # pg_ctl sees only this installation's explicitly bound PGDATA. It is
    # called after the application's owned process has released its sessions.
    args=options(executable,install,'postgres')+['--bind',str(home/'postgresql-data')+':/var/lib/postgresql/data',
        '--bind',str(temporary_directory(install))+':/tmp','--',
        'pg_ctl','-D','/var/lib/postgresql/data','-m','fast','-w','-t','60','stop']
    result=subprocess.run(args,env=host_environment(install),capture_output=True,timeout=90)
    if result.returncode:
        path=home/'postgresql-stop-error.log';path.write_bytes(result.stdout+result.stderr);path.chmod(0o600)
    require(result.returncode==0,'postgresql_stop_failed')
