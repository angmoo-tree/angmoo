"""User-facing Docker migration launcher. Bundle with PyInstaller for host use.

Only Docker is required by the distributed executable. Canonical conversion is
performed by the target backend image, never by host-specific SQL.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import re
from pathlib import Path
import secrets
import subprocess
import tempfile
import time
from urllib.parse import quote
from uuid import uuid4

BUILD_SOURCE = None  # Release packaging binds this launcher to product source S.

TEXT = {
 'en': {'one':'Review the detected environment before migration.', 'many':'Select one environment to migrate.',
        'none':'No environment found. Specify the existing volume or directory.', 'confirm':'Start migration? [yes/no] ',
        'backup':'Backup directory', 'choice':'Environment number: ', 'cancelled':'Cancelled. Existing environments are unchanged.',
        'failed':'Migration stopped. Backup and source are preserved.', 'ready':'Migration completed. Open the displayed browser address.'},
 'ko': {'one':'발견한 환경을 확인한 뒤 이전을 시작하세요.', 'many':'이전할 환경 하나를 선택하세요.',
        'none':'환경을 찾지 못했습니다. 기존 볼륨 또는 폴더를 지정하세요.', 'confirm':'이전을 시작하시겠습니까? [yes/no] ',
        'backup':'백업 위치', 'choice':'환경 번호: ', 'cancelled':'취소했습니다. 기존 환경은 변경하지 않았습니다.',
        'failed':'이전을 중단했습니다. 백업과 원본은 보존됩니다.', 'ready':'이전을 완료했습니다. 표시된 주소를 브라우저에서 여세요.'},
}


class Docker:
    def run(self, *args, timeout=180):
        result=subprocess.run(['docker',*map(str,args)],capture_output=True,text=True,encoding='utf-8',timeout=timeout)
        if result.returncode:
            # Docker/driver output may contain environment secrets. Only a code
            # and command name belong in a normal support record.
            raise RuntimeError('docker_'+str(args[0])+'_failed')
        return result.stdout.strip()

    def json(self,*args):return json.loads(self.run(*args))


def discover(docker):
    engine=docker.run('info','--format','{{.ID}}',timeout=20)
    context=docker.run('context','show',timeout=20)
    identifiers=docker.run('ps','-aq',timeout=20).split()
    containers=docker.json('inspect',*identifiers) if identifiers else []
    volume_names=docker.run('volume','ls','-q',timeout=20).split()
    volumes=docker.json('volume','inspect',*volume_names) if volume_names else []
    candidates={};healthy_postgresql_projects=set()
    for container in containers:
        labels=container.get('Config',{}).get('Labels') or {}
        project=labels.get('com.docker.compose.project')
        if not project or labels.get('com.docker.compose.service')!='backend' or labels.get('io.angmoo.installation'):continue
        version=str(labels.get('org.opencontainers.image.version') or 'unverified')
        if re.fullmatch(r'\d+\.\d+\.\d+(?:-dev.*)?',version) and tuple(map(int,version.split('-')[0].split('.'))) >= (0,1,4):
            if container.get('State',{}).get('Health',{}).get('Status')=='healthy':healthy_postgresql_projects.add(project)
            continue
        for mount in container.get('Mounts',[]):
            if mount.get('Destination')!='/var/lib/angmoo' or mount.get('Type') not in {'volume','bind'}:continue
            source=mount.get('Name') if mount['Type']=='volume' else mount['Source']
            key=(project,mount['Type'],source)
            candidates[key]={'project':project,'kind':mount['Type'],'source':source,
                'version':labels.get('org.opencontainers.image.version','unverified'),
                'running':bool(container.get('State',{}).get('Running')),'containers':[]}
    for volume in volumes:
        labels=volume.get('Labels') or {}
        if labels.get('com.docker.compose.volume')!='angmoo_contributor_embedded_data':continue
        project=labels.get('com.docker.compose.project')
        if project in healthy_postgresql_projects:continue
        if project:
            candidates.setdefault((project,'volume',volume['Name']),{'project':project,'kind':'volume','source':volume['Name'],
                'version':'unverified','running':False,'containers':[]})
    for item in candidates.values():
        item['containers']=[c['Id'] for c in containers if (c.get('Config',{}).get('Labels') or {}).get('com.docker.compose.project')==item['project']]
        item['engine']=engine;item['context']=context
        item['id']=hashlib.sha256(json.dumps([engine,context,item['project'],item['kind'],item['source']]).encode()).hexdigest()[:20]
    return sorted(candidates.values(),key=lambda x:(x['project'],x['source']))


def choose(candidates,args,ask=input):
    text=TEXT[args.language]
    manual=args.source_volume or args.source_directory or args.source_project
    if candidates:
        if manual:raise ValueError('manual_source_only_when_discovery_finds_none')
        print(text['one'] if len(candidates)==1 else text['many'])
        for index,item in enumerate(candidates,1):
            print(f"{index}. {item['project']} | {item['kind']}:{item['source']} | {item['version']}")
        if len(candidates)==1:return candidates[0]
        value=ask(text['choice']).strip()
        if not value.isdecimal() or not 1<=int(value)<=len(candidates):raise ValueError('migration_selection_invalid')
        return candidates[int(value)-1]
    print(text['none'])
    if not (args.source_volume or args.source_directory):raise ValueError('migration_source_required')
    if args.source_volume and args.source_directory:raise ValueError('migration_source_ambiguous')
    return {'project':args.source_project or 'manual','kind':'volume' if args.source_volume else 'bind',
        'source':args.source_volume or str(Path(args.source_directory).resolve()),'version':'unverified','containers':[], 'id':'manual'}


def private_directory(path):
    path.mkdir(parents=True,exist_ok=False,mode=0o700)
    if os.name=='nt':
        import getpass
        subprocess.run(['icacls',str(path),'/inheritance:r','/grant:r',getpass.getuser()+':(OI)(CI)F'],check=True,capture_output=True)


def write_private_once(path,body):
    """Publish a complete 0600 file inside an already private directory.

    Windows inherits the migration directory's owner-only DACL. Hard-link
    publication refuses an existing destination instead of replacing a key.
    """
    path=Path(path)
    descriptor,temporary=tempfile.mkstemp(prefix='.'+path.name+'-',dir=path.parent)
    try:
        with os.fdopen(descriptor,'wb') as stream:
            stream.write(body.encode('utf-8'));stream.flush();os.fsync(stream.fileno())
        os.link(temporary,path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def wait_ready(docker,container,command,seconds=120):
    deadline=time.monotonic()+seconds
    while time.monotonic()<deadline:
        try:
            docker.run('exec',container,*command,timeout=10)
            return
        except RuntimeError:
            if not docker.json('inspect',container)[0]['State']['Running']:raise RuntimeError('migration_service_stopped')
            time.sleep(1)
    raise RuntimeError('migration_service_not_ready')


def owned(docker,kind,name,installation_id):
    selector='id='+name if re.fullmatch(r'[0-9a-f]{12,64}',name) else 'name=^/'+name+'$'
    identifiers=docker.run(*(('ps','-aq','--filter',selector) if kind=='container' else (kind,'ls','-q','--filter','name=^'+name+'$'))).split()
    if not identifiers:return False
    value=docker.json(*(('inspect',name) if kind=='container' else (kind,'inspect',name)))[0]
    labels=(value.get('Config',{}).get('Labels') or {}) if kind=='container' else (value.get('Labels') or {})
    if labels.get('io.angmoo.installation')!=installation_id:raise ValueError('migration_resource_owner_mismatch')
    return True


def read_record(path,docker):
    root=Path(path).absolute()
    if root.is_file():root=root.parent
    if any(p.is_symlink() for p in (root,*root.parents)):raise ValueError('migration_record_link_refused')
    state=json.loads((root/'migration.json').read_text(encoding='utf-8'))
    if state.get('schema')!='angmoo-docker-migration.v1' or not state.get('installation_id','').startswith('angmoo-'):
        raise ValueError('migration_record_invalid')
    if state['engine']!=docker.run('info','--format','{{.ID}}') or state['context']!=docker.run('context','show'):
        raise ValueError('migration_docker_context_changed')
    return root,state


def rollback(docker,path,args,ask=input):
    root,state=read_record(path,docker)
    message={'en':'Return to the preserved 0.1.3 environment? New PostgreSQL changes will stay separate. [yes/no] ',
             'ko':'보존한 0.1.3 환경으로 복귀할까요? PostgreSQL에서 추가한 데이터는 별도로 남습니다. [yes/no] '}[args.language]
    if ask(message).strip().lower()!='yes':return {'state':'cancelled'}
    for name in reversed(list(state['containers'].values())):
        if owned(docker,'container',name,state['installation_id']):docker.run('stop','--time','200',name,timeout=300)
    for identifier in state.get('previously_running',[]):
        value=docker.json('inspect',identifier)[0]
        if (value.get('Config',{}).get('Labels') or {}).get('com.docker.compose.project')!=state['source']['project']:
            raise ValueError('migration_source_identity_changed')
        docker.run('start',identifier)
    state['phase']='rolled_back';(root/'migration.json').write_text(json.dumps(state,indent=2)+'\n',encoding='utf-8')
    return {'state':'rolled_back','postgresql_data_preserved':True}


def write_compose(root,state,*,validation):
    """Normal operation uses Compose too; the temporary DB is stopped first."""
    images=state['images'];volumes=state['volumes']
    shared={'restart':'unless-stopped','labels':{'io.angmoo.installation':state['installation_id']}}
    health={'interval':'5s','timeout':'5s','retries':24,'start_period':'30s'}
    services={
        'postgres':{**shared,'image':images['postgres'],'environment':{
            'POSTGRES_USER':'angmoo_owner','POSTGRES_DB':'angmoo','POSTGRES_PASSWORD_FILE':'/run/secret'},
            'volumes':['postgres-data:/var/lib/postgresql/data',str(root/'secrets/postgres-password')+':/run/secret:ro'],
            'command':['postgres','-c','max_connections=28','-c','shared_buffers=64MB','-c','work_mem=4MB','-c','max_pred_locks_per_transaction=256'],
            'healthcheck':{**health,'test':['CMD','pg_isready','-U','angmoo_owner','-d','angmoo']},'stop_grace_period':'120s'},
        'backend':{**shared,'image':images['backend'],'user':'0:0','command':['postgresql-api']+(['--validation'] if validation else []),
            'environment':{'ANGMOO_FRONTEND_ORIGIN':'http://127.0.0.1:'+str(state['port'])},
            'volumes':['app-data:/var/lib/angmoo'],'depends_on':{'postgres':{'condition':'service_healthy'}},
            'healthcheck':{**health,'test':['CMD','python','-c',"import urllib.request;urllib.request.urlopen('http://127.0.0.1:8080/health',timeout=3)"]},'stop_grace_period':'200s'},
        'frontend':{**shared,'image':images['frontend'],'environment':{'ANGMOO_API_BASE_URL':'http://backend:8080','HOSTNAME':'0.0.0.0','PORT':'3000'},
            'ports':['127.0.0.1:'+str(state['port'])+':3000'],'depends_on':{'backend':{'condition':'service_healthy'}},
            'healthcheck':{**health,'test':['CMD','node','-e',"fetch('http://127.0.0.1:3000/').then(r=>{if(!r.ok)process.exit(1)}).catch(()=>process.exit(1))"]},'stop_grace_period':'20s'}}
    document={'name':state['network'],'services':services,'volumes':{
        'postgres-data':{'external':True,'name':volumes['postgres']},'app-data':{'external':True,'name':volumes['app']}}}
    directory=root/'installation';directory.mkdir(mode=0o700,exist_ok=True)
    path=directory/'compose.json';path.write_text(json.dumps(document,indent=2)+'\n',encoding='utf-8')
    state['compose_file']=str(path)
    return path


def migrate(docker,source,args,ask=input):
    text=TEXT[args.language]
    resume=getattr(args,'resume',None)
    if resume:
        root,state=read_record(resume,docker);source=state['source']
        if state['phase'] in {'active','rolled_back'}:raise ValueError('migration_already_finished')
    else:
        root=Path(args.backup_directory or Path.home()/'AngmooBackups')/('0.1.3-to-0.1.4-'+uuid4().hex[:12])
        if source['version'] not in {'0.1.3','unverified'}:raise ValueError('migration_source_version_unsupported')
        if source['version']=='unverified':
            question={'en':'Confirm this source is official 0.1.3 by typing 0.1.3 (anything else cancels): ',
                'ko':'원본이 정식 0.1.3인지 확인하고 0.1.3을 입력하세요(다른 입력은 취소): '}[args.language]
            if ask(question).strip()!='0.1.3':return {'state':'cancelled'}
    if source['kind']=='volume':docker.json('volume','inspect',source['source'])
    if source['kind']=='bind' and not Path(source['source']).is_dir():raise ValueError('migration_source_directory_missing')
    if any(p.is_symlink() or (hasattr(p,'is_junction') and p.is_junction()) for p in (root,*root.parents)):
        raise ValueError('migration_backup_link_refused')
    if source['kind']=='bind':
        directory=Path(source['source']).resolve()
        destination=root.resolve()
        if destination.is_relative_to(directory) or directory.is_relative_to(destination):raise ValueError('migration_source_backup_overlap')
        if os.name=='nt' and os.environ.get('LOCALAPPDATA'):
            installed=(Path(os.environ['LOCALAPPDATA'])/'Angmoo').resolve()
            if directory==installed or directory.is_relative_to(installed):raise ValueError('migration_windows_installation_is_not_docker_source')
    required=args.required_free_gib*1024**3
    import shutil
    ancestor=root.parent
    while not ancestor.exists():ancestor=ancestor.parent
    available=shutil.disk_usage(ancestor).free
    if available<required:raise ValueError('migration_backup_space_low')
    print(json.dumps({'source':source,'backup':str(root),'free_bytes':available,'target':'0.1.4'},ensure_ascii=False,indent=2))
    if ask(text['confirm']).strip().lower()!='yes':
        print(text['cancelled']);return {'state':'cancelled'}
    if not resume and source['id']!='manual' and source not in discover(docker):raise ValueError('migration_source_selection_changed')
    if not resume:private_directory(root)
    installation_id=state['installation_id'] if resume else 'angmoo-'+uuid4().hex
    suffix=installation_id[-12:]
    name='angmoo-pg-'+suffix
    if not resume:state={'schema':'angmoo-docker-migration.v1','installation_id':installation_id,'source':source,'phase':'prepared',
        'containers':{'postgres':name+'-postgres','backend':name+'-backend','frontend':name+'-frontend'},'network':name,
        'volumes':{'postgres':name+'-postgres-data','app':name+'-app-data'},'port':args.port,
        'engine':docker.run('info','--format','{{.ID}}'),'context':docker.run('context','show'),'done':[]}
    args.port=state['port']
    def save(): (root/'migration.json').write_text(json.dumps(state,indent=2)+'\n',encoding='utf-8')
    save()
    credentials=root/'secrets';credentials.mkdir(mode=0o700,exist_ok=True)
    owner_password=secrets.token_urlsafe(48);runtime_password=secrets.token_urlsafe(48)
    for key,body in {'postgres-password':owner_password,'owner-dsn':'postgresql+psycopg://angmoo_owner:'+quote(owner_password,safe='')+'@postgres:5432/angmoo',
                     'runtime-dsn':'postgresql+psycopg://angmoo_runtime:'+quote(runtime_password,safe='')+'@postgres:5432/angmoo'}.items():
        path=credentials/key
        if not resume:write_private_once(path,body+'\n')
    labels=['--label','io.angmoo.installation='+installation_id]
    images={key:docker.json('image','inspect',state['images'][key] if resume else getattr(args,key+'_image'))[0]
        for key in ('backend','postgres','frontend')}
    revisions={(value['Config'].get('Labels') or {}).get('org.opencontainers.image.revision') for value in images.values()}
    if BUILD_SOURCE is not None and revisions!={BUILD_SOURCE}:raise ValueError('migration_tool_source_mismatch')
    if len(revisions)!=1 or None in revisions or 'unknown' in revisions:raise ValueError('migration_target_source_mismatch')
    if resume and state.get('target_source') not in (None,next(iter(revisions))):raise ValueError('migration_resume_source_mismatch')
    if any((value['Config'].get('Labels') or {}).get('org.opencontainers.image.version')!='0.1.4' for value in images.values()):raise ValueError('migration_target_version_mismatch')
    if len({(value['Os'],value['Architecture']) for value in images.values()})!=1:raise ValueError('migration_target_architecture_mismatch')
    state['images']={key:value['Id'] for key,value in images.items()};state['target_source']=next(iter(revisions));save()
    backend,postgres,frontend=(state['images'][key] for key in ('backend','postgres','frontend'))
    # Resolve all target images before stopping any source service.
    for image in (backend,postgres,frontend):docker.json('image','inspect',image)
    was_running=[c for c in source['containers'] if docker.json('inspect',c)[0]['State']['Running']]
    if not resume:state['previously_running']=was_running;save()
    if was_running:docker.run('stop','--time','200',*was_running,timeout=300)
    state['phase']='source_stopped';save()
    if resume and state.get('compose_file'):
        identifiers=docker.run('compose','-f',state['compose_file'],'ps','-aq').split()
        for identifier in identifiers:owned(docker,'container',identifier,installation_id)
        if identifiers:docker.run('stop','--time','200',*identifiers,timeout=300)
    mount_source='type='+source['kind']+',src='+source['source']+',dst=/source,readonly'
    common=['run','--rm','--user','0:0',*labels,'--entrypoint','python','--mount','type=bind,src='+str(root)+',dst=/migration']
    try:
        if 'backed_up' not in state['done']:
            docker.run(*common,'--mount',mount_source,backend,'-m','app.runtime.postgresql_installation','snapshot',
                '--source-root','/source','--work','/migration/work','--installation-id',installation_id,timeout=1800)
            state['done'].append('backed_up')
        state['phase']='backed_up';save()
        if not owned(docker,'network',name,installation_id):docker.run('network','create',*labels,name)
        for volume in state['volumes'].values():
            if not owned(docker,'volume',volume,installation_id):docker.run('volume','create',*labels,volume)
        temporary=state.setdefault('migration_postgres',name+'-postgres');save()
        if not owned(docker,'container',temporary,installation_id):docker.run('run','-d','--name',temporary,*labels,'--network',name,'--network-alias','postgres',
            '--mount','type=volume,src='+state['volumes']['postgres']+',dst=/var/lib/postgresql/data',
            '--mount','type=bind,src='+str(credentials/'postgres-password')+',dst=/run/secrets/postgres-password,readonly',
            '-e','POSTGRES_PASSWORD_FILE=/run/secrets/postgres-password','-e','POSTGRES_USER=angmoo_owner','-e','POSTGRES_DB=angmoo',
            postgres,'postgres','-c','max_connections=28','-c','shared_buffers=64MB','-c','max_pred_locks_per_transaction=256')
        else:docker.run('start',temporary)
        wait_ready(docker,temporary,['pg_isready','-U','angmoo_owner','-d','angmoo'])
        if 'verified' not in state['done']:
            docker.run(*common,'--network',name,'--mount','type=volume,src='+state['volumes']['app']+',dst=/appdata',
                backend,'-m','app.runtime.postgresql_installation','migrate','--work','/migration/work','--data-root','/appdata',
                '--owner-dsn-file','/migration/secrets/owner-dsn','--runtime-dsn-file','/migration/secrets/runtime-dsn',timeout=1800)
            state['done'].append('verified')
        state['phase']='verified';save()
        # Do not run two postmasters over the same PGDATA. The one-off DB is
        # retained stopped; Compose owns subsequent normal start/stop/restart.
        docker.run('stop','--time','120',temporary,timeout=150)
        path=write_compose(root,state,validation=args.validation);save()
        docker.run('compose','-f',path,'up','-d','--wait','--wait-timeout','240',timeout=300)
        state['containers']={service:docker.run('compose','-f',path,'ps','-q',service) for service in ('postgres','backend','frontend')}
        state['phase']='active';save()
        print(text['ready']);print('http://127.0.0.1:'+str(args.port)+'/')
        print('docker compose -f "'+str(path)+'" ps')
        return {'state':'active','record':str(root/'migration.json'),'installation_id':installation_id}
    except BaseException:
        state['failed_phase']=state['phase'];state['phase']='failed';save()
        print(text['failed'])
        raise


def main():
    parser=argparse.ArgumentParser(description='Angmoo Docker 0.1.3 → 0.1.4 / Docker 데이터 이전')
    parser.add_argument('--language',choices=TEXT,default='en')
    parser.add_argument('--list',action='store_true')
    control=parser.add_mutually_exclusive_group()
    control.add_argument('--resume',type=Path,help='Resume a saved migration / 저장한 이전 재개')
    control.add_argument('--rollback',type=Path,help='Return to the preserved source / 보존한 원본으로 복귀')
    parser.add_argument('--source-project')
    parser.add_argument('--source-volume')
    parser.add_argument('--source-directory')
    parser.add_argument('--backup-directory')
    parser.add_argument('--port',type=int,default=3000)
    parser.add_argument('--required-free-gib',type=int,default=4)
    parser.add_argument('--backend-image',default='ghcr.io/angmoo-tree/angmoo-backend:release-v0.1.4')
    parser.add_argument('--frontend-image',default='ghcr.io/angmoo-tree/angmoo-frontend:release-v0.1.4')
    parser.add_argument('--postgres-image',default='ghcr.io/angmoo-tree/angmoo-postgres:release-v0.1.4')
    parser.add_argument('--validation',action='store_true',help=argparse.SUPPRESS)
    args=parser.parse_args()
    if not 1<=args.port<=65535 or args.required_free_gib<1:parser.error('invalid port or disk allowance')
    docker=Docker()
    try:
        if args.rollback:print(json.dumps(rollback(docker,args.rollback,args)));return
        if args.resume:migrate(docker,None,args);return
        candidates=discover(docker)
        if args.list:print(json.dumps(candidates,ensure_ascii=False,indent=2));return
        migrate(docker,choose(candidates,args),args)
    except (RuntimeError,ValueError,subprocess.TimeoutExpired) as exc:
        code=str(exc) if isinstance(exc,(RuntimeError,ValueError)) else 'docker_operation_timeout'
        print(json.dumps({'state':'failed','code':code},ensure_ascii=False))
        raise SystemExit(2) from None


if __name__=='__main__':main()
