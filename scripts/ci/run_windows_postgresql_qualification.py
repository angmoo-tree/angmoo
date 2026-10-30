"""Real NSIS and packaged-sidecar qualification on an empty hosted Windows user.

Never run this installer harness on a developer or self-hosted machine. Reports
contain booleans and source hashes only; databases and tokens remain private.
"""
from __future__ import annotations
import argparse,hashlib,json,os,secrets,shutil,sqlite3,subprocess,sys,time,urllib.error,urllib.request,uuid
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'backend'))
from scripts.ci.windows_postgresql_coverage import CHECKS,SCHEMA
OLD_SOURCE='01ef3847c77a890071728b7f618f18fa88b775bf'
OLD_EXE_SHA='e9679b724ad7f8257ae8b0bbf27a67f92793d2aca077c8dce3db4ef97bae319b'
ORIGIN='http://tauri.localhost'

def require(value,code):
    if not value:raise ValueError(code)

def digest(path):
    with Path(path).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

def inventory(root,names):
    return {str(p.relative_to(root)).replace('\\','/'):digest(p) for name in names
            for p in (root/name).rglob('*') if p.is_file()}

def hosted_root():
    require(os.name=='nt' and os.environ.get('GITHUB_ACTIONS')=='true'
        and os.environ.get('RUNNER_ENVIRONMENT')=='github-hosted','windows_pg_hosted_only')
    root=Path(os.environ['LOCALAPPDATA'])/'Angmoo'
    require(not root.exists() or not any(root.iterdir()),'windows_pg_existing_installation_refused')
    require(not (root.parent/'com.angmoo.desktop').exists(),'windows_pg_legacy_user_data_refused')
    return root

def nsis(path):
    completed=subprocess.run([str(path),'/S'],timeout=300,creationflags=subprocess.CREATE_NO_WINDOW)
    require(completed.returncode==0,'windows_pg_nsis_failed')
    if 'uninstall' in path.name.lower():
        deadline=time.monotonic()+90
        while (path.parent/'angmoo-desktop.exe').exists() and time.monotonic()<deadline:time.sleep(.5)
        require(not (path.parent/'angmoo-desktop.exe').exists(),'windows_pg_uninstall_not_finished')

class Sidecar:
    def __init__(self,app,data,private,*,legacy=False,migrate=False):
        self.token=secrets.token_urlsafe(48);self.generation=uuid.uuid4().hex
        self.endpoint=data/'runtime/sidecar.endpoint.json';self.private=private
        env=dict(os.environ,DESKTOP_LAUNCH_TOKEN=self.token,DESKTOP_ALLOWED_ORIGIN=ORIGIN,
                 PATH=os.environ['SystemRoot']+'\\System32;'+os.environ['SystemRoot'])
        env['ANGMOO_SOURCE_SHA']=json.loads((app/'installer-payload.json').read_text())['build_commit']
        command=[str(app/'angmoo-sidecar.exe'),'--parent-pid',str(os.getpid()),'--data-root',str(data),
            '--legacy-data-root',str(data.parent/'unused-legacy-source'),'--runtime-root',str(data/'runtime'),
            '--launch-id',self.generation,'--runtime-profile','LOCAL_EMBEDDED' if legacy else 'LOCAL_POSTGRESQL']
        if not legacy:command+=['--postgresql-root',str(app/'postgresql'),'--validation']
        if migrate:command+=['--migrate-sqlite']
        self.log=(private/('sidecar-'+self.generation+'.log')).open('wb')
        self.process=subprocess.Popen(command,env=env,stdout=self.log,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW)
        deadline=time.monotonic()+240
        while time.monotonic()<deadline:
            require(self.process.poll() is None,'windows_pg_packaged_start_failed')
            if self.endpoint.exists():
                value=json.loads(self.endpoint.read_text())
                if value.get('generation')==self.generation:
                    self.url='http://127.0.0.1:'+str(value['dynamic_port'])
                    try:
                        if self.request('/health')[0]==200:return
                    except OSError:pass
            time.sleep(.5)
        raise ValueError('windows_pg_packaged_readiness_timeout')

    def request(self,path,*,token=True,origin=ORIGIN,method='GET',cookie=None):
        headers={'Origin':origin}
        if token:headers['x-angmoo-launcher-token']=self.token
        if cookie:headers['Cookie']='angmoo_session='+cookie
        req=urllib.request.Request(self.url+path,headers=headers,method=method)
        try:
            with urllib.request.urlopen(req,timeout=20) as r:return r.status,json.load(r)
        except urllib.error.HTTPError as e:return e.code,{}

    def stop(self):
        self.request('/__angmoo/desktop/shutdown',method='POST')
        code=self.process.wait(timeout=120);self.log.close()
        require(code==0 and not self.endpoint.exists(),'windows_pg_shutdown_failed')

def seed(data):
    from scripts.quickstart_smoke import _bootstrap_local_session
    return _bootstrap_local_session('postgresql-upgrade-fixture','http://127.0.0.1:1',data_root=data)

def check_pg(data,post_id):
    import psycopg
    from app.runtime.postgresql_installation import read_dsn
    dsn=read_dsn(data/'postgresql-appdata/secrets/postgresql-runtime-dsn').replace('postgresql+psycopg://','postgresql://')
    with psycopg.connect(dsn) as db:
        require(db.execute('SELECT version FROM angmoo_postgresql_schema_version').fetchone()==(5,),'windows_pg_schema_mismatch')
        require(db.execute('SELECT count(*) FROM posts WHERE id=%s',(post_id,)).fetchone()==(1,),'windows_pg_fixture_missing')
    from app.database import create_database_engine,create_session_factory
    from app.domains.social.models.posts import Post
    from app.runtime.persistence.postgresql_schema import metadata
    metadata();engine=create_database_engine(dsn.replace('postgresql://','postgresql+psycopg://'))
    marker='ci-pg-write-'+uuid.uuid4().hex
    try:
        with create_session_factory(engine)() as session:
            session.add(Post(id=marker,author_name='Synthetic fixture',
                title='PostgreSQL persistence check',body='PostgreSQL 저장 검증'));session.commit()
    finally:engine.dispose()
    return marker

def interrupt(data,resources,private):
    # Fault injection is confined to the test process. The real converter commits
    # canonical data, then this owned test process is terminated before activation.
    flag=private/'canonical-committed.json'
    script=private/'interrupt-conversion.py'
    script.write_text('''import json,time
from pathlib import Path
from app.runtime.postgresql_migration import Migration
from app.runtime.windows_postgresql import prepare
original=Migration.convert
def paused(self,*args,**kwargs):
 result=original(self,stop_after='canonical')
 assert result['state']=='interrupted_after_canonical'
 Path(FLAG).write_text(json.dumps({'phase':'canonical_committed'}))
 time.sleep(600)
Migration.convert=paused
prepare(Path(DATA),Path(RESOURCES),allow_migration=True)
'''.replace('FLAG',repr(str(flag))).replace('DATA',repr(str(data))).replace('RESOURCES',repr(str(resources))),encoding='utf-8')
    env=dict(os.environ,PYTHONPATH=str(ROOT/'backend'))
    with (private/'interruption.log').open('wb') as log:
        child=subprocess.Popen([sys.executable,str(script)],env=env,stdout=log,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW)
        try:
            deadline=time.monotonic()+180
            while not flag.exists():
                require(child.poll() is None and time.monotonic()<deadline,'windows_pg_fault_phase_not_reached');time.sleep(.3)
            child.kill();child.wait(timeout=20)
        finally:
            if child.poll() is None:child.kill();child.wait(timeout=20)
    require(not (data/'postgresql-appdata/runtime/postgresql-runtime.json').exists(),'windows_pg_activated_partial_conversion')
    return digest(data/'postgresql-migration/work/snapshot.json')

def wait_for_host(child,endpoint,*,timeout,confirm=None):
    """Wait for the real host, preserving cold-start and consent evidence."""
    deadline=time.monotonic()+timeout
    accepted=confirm is None
    while time.monotonic()<deadline:
        require(child.poll() is None,'windows_pg_actual_host_not_ready')
        if not accepted:accepted=confirm(child.pid)
        if endpoint.exists():
            port=json.loads(endpoint.read_text())['dynamic_port']
            try:urllib.request.urlopen(f'http://127.0.0.1:{port}/health',timeout=10)
            except urllib.error.HTTPError as e:
                require(e.code==401,'windows_pg_actual_host_unauthenticated')
                require(accepted,'windows_pg_migration_consent_not_observed')
                return
            except (OSError,TimeoutError):pass
            else:raise ValueError('windows_pg_actual_host_token_gate_missing')
        time.sleep(.5)
    raise ValueError('windows_pg_actual_host_not_ready')


def host_launch(app,data,private,*,initial=False,migration=False):
    endpoint=data/'runtime/sidecar.endpoint.json'
    require(not endpoint.exists(),'windows_pg_previous_endpoint_remains')
    env=dict(os.environ,PATH=os.environ['SystemRoot']+'\\System32;'+os.environ['SystemRoot'])
    with (private/('actual-tauri-host-initial.log' if initial else 'actual-tauri-host.log')).open('wb') as log:
        child=subprocess.Popen([str(app/'angmoo-desktop.exe')],env=env,stdout=log,stderr=subprocess.STDOUT,
                               creationflags=subprocess.CREATE_NO_WINDOW)
        try:
            from scripts.ci.windows_migration_consent import accept_owned_migration_dialog
            wait_for_host(child,endpoint,timeout=330 if initial else 150,
                          confirm=accept_owned_migration_dialog if migration else None)
        finally:
            if child.poll() is None:child.terminate();child.wait(timeout=15)
    deadline=time.monotonic()+120
    while endpoint.exists() and time.monotonic()<deadline:time.sleep(.5)
    require(not endpoint.exists() and not (data/'postgresql/cluster/postmaster.pid').exists(),'windows_pg_actual_host_cleanup_failed')


def native_paths_and_restore(resources,private):
    """Exercise actual binaries under Unicode paths and an independent cluster."""
    from app.runtime.windows_postgresql import NativePostgres
    import psycopg
    root=private/'한글 PostgreSQL 경로'
    copied=root/'동봉 자원';shutil.copytree(resources,copied)
    manager=NativePostgres(root/'앱 데이터',copied)
    independent=NativePostgres(private/'independent-cluster',resources)
    try:
        independent.start();manager.start()
        with psycopg.connect(manager.owner()) as db:
            require(db.execute('SHOW server_encoding').fetchone()==('UTF8',),'windows_pg_encoding_mismatch')
            db.execute('CREATE EXTENSION IF NOT EXISTS vector')
            db.execute('CREATE TABLE unicode_fixture (value text)')
            db.execute('INSERT INTO unicode_fixture VALUES (%s)',('한글 English 😀',))
        backup=root/'백업 데이터.dump';manager.backup(backup);manager.restore(backup)
        with psycopg.connect(manager.owner()) as db:
            require(db.execute('SELECT value FROM unicode_fixture').fetchone()==('한글 English 😀',),'windows_pg_restored_value_mismatch')
        manager.stop();manager.start()
        with psycopg.connect(independent.owner()) as db:
            manager.stop()
            require(db.execute('SELECT 1').fetchone()==(1,),'windows_pg_independent_cluster_affected')
    finally:
        manager.stop();independent.stop()

def run(args):
    data=hosted_root();private=args.work.resolve();private.mkdir(parents=True,exist_ok=False)
    require(private.is_relative_to(Path(os.environ['RUNNER_TEMP']).resolve()),'windows_pg_private_path_invalid')
    require(digest(args.installer)==args.installer_sha256,'windows_pg_installer_hash_mismatch')
    app=data/'app';source_files={};post_id=None
    if args.kind!='clean-install':
        old=private/'Angmoo_0.1.3_x64-setup.exe'
        urllib.request.urlretrieve('https://github.com/angmoo-tree/angmoo/releases/download/release-v0.1.3/'+old.name,old)
        require(digest(old)==OLD_EXE_SHA,'windows_pg_official_source_hash_mismatch');nsis(old)
        payload=json.loads((app/'installer-payload.json').read_text())
        require(payload['build_commit']==OLD_SOURCE and payload['product_version']=='0.1.3','windows_pg_old_payload_mismatch')
        old_runtime=Sidecar(app,data,private,legacy=True);_,post_id=seed(data);old_runtime.stop()
        source_files=inventory(data,('canonical','media','secrets'))
        require(bool(source_files),'windows_pg_empty_source_fixture')
    nsis(args.installer)
    payload=json.loads((app/'installer-payload.json').read_text())
    require(payload['schema_version']==3 and payload['build_commit']==args.source_sha,'windows_pg_payload_mismatch')
    require(payload['postgresql']['schema_version']==5,'windows_pg_target_schema_mismatch')
    resources=app/'postgresql';resources_sha=digest(resources/'angmoo-resources.json')
    require(resources_sha==payload['postgresql']['resources_manifest_sha256'],'windows_pg_native_binding_mismatch')
    if source_files:
        require(inventory(data,('canonical','media','secrets'))==source_files,'windows_pg_installer_changed_source')
        require(not (data/'postgresql-appdata').exists(),'windows_pg_installer_converted_without_consent')
    interrupted_snapshot=interrupt(data,resources,private) if args.kind=='failure-recovery' else None
    # Exercise the installed Tauri host before a direct sidecar can prepare PG.
    # In failure-recovery this resumes the deliberately interrupted conversion.
    require(not (data/'postgresql-appdata/runtime/postgresql-runtime.json').exists(),
            'windows_pg_actual_host_already_initialized')
    host_launch(app,data,private,initial=True,migration=bool(source_files))
    require((data/'postgresql-appdata/runtime/postgresql-runtime.json').is_file(),
            'windows_pg_actual_host_initialization_missing')
    runtime=Sidecar(app,data,private)
    health=runtime.request('/health')[1]
    require(health.get('profile')=='LOCAL_POSTGRESQL' and health.get('persistence')=='postgresql','windows_pg_runtime_profile_mismatch')
    require(runtime.request('/health',token=False)[0]==401,'windows_pg_token_gate_missing')
    require(runtime.request('/health',origin='http://evil.example')[0]==403,'windows_pg_origin_gate_missing')
    if post_id is None:_,post_id=seed(data/'postgresql-appdata')
    written=check_pg(data,post_id);runtime.stop()
    require(not (data/'postgresql/cluster/postmaster.pid').exists(),'windows_pg_server_survived_shutdown')
    if interrupted_snapshot:
        require(digest(data/'postgresql-migration/work/snapshot.json')==interrupted_snapshot,'windows_pg_resume_replaced_snapshot')
    runtime=Sidecar(app,data,private);check_pg(data,written);runtime.stop()
    if source_files:require(inventory(data,('canonical','media','secrets'))==source_files,'windows_pg_source_changed_after_conversion')
    before=inventory(data,('postgresql','postgresql-appdata'))
    uninstall=list(app.glob('*uninstall*.exe'))
    require(len(uninstall)==1,'windows_pg_uninstaller_missing');nsis(uninstall[0])
    require(inventory(data,('postgresql','postgresql-appdata'))==before,'windows_pg_silent_uninstall_deleted_data')
    nsis(args.installer)
    runtime=Sidecar(app,data,private);check_pg(data,written);runtime.stop()
    host_launch(app,data,private)
    native_paths_and_restore(resources,private)
    checks={k:True for k in CHECKS}
    if source_files:checks['migration_consent']=True
    if interrupted_snapshot:checks.update(interrupted_after_canonical=True,same_migration_resumed=True)
    report={'schema':SCHEMA,'status':'PASS','source_sha':args.source_sha,'run_id':os.environ['GITHUB_RUN_ID'],
        'run_attempt':os.environ['GITHUB_RUN_ATTEMPT'],'kind':args.kind,'checks':checks,
        'source_version':'0.1.3' if source_files else None,'target_schema':5,'resources_sha256':resources_sha}
    args.output.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    return report

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--installer',type=Path,required=True);p.add_argument('--installer-sha256',required=True)
    p.add_argument('--source-sha',required=True);p.add_argument('--kind',choices=['clean-install','upgrade-013','failure-recovery'],required=True)
    p.add_argument('--work',type=Path,required=True);p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    print(json.dumps(run(args)))

if __name__=='__main__':main()
