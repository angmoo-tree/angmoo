"""Owned three-service Termux launcher for the PostgreSQL experiment only."""
import argparse,hashlib,ipaddress,json,os,pathlib,signal,socket,subprocess,time,uuid,urllib.request
import phone_pg
from guard import RUN_ID,SOURCE_SHA,owned_path

TERMUX_RESOLVER=pathlib.Path('/data/data/com.termux/files/usr/etc/resolv.conf')


def resolver_file():
    # Docker exports leave /etc/resolv.conf empty. Supply a trial-owned copy of
    # the installed Termux resolver; never alter the image or global resolver.
    target=owned_path(phone_pg.root(),'records/resolv.conf')
    source=target if target.exists() else TERMUX_RESOLVER
    if source.is_symlink():raise ValueError('experiment_resolver_link_refused')
    body=source.read_text()
    lines=[line.split() for line in body.splitlines() if line.strip() and not line.lstrip().startswith(('#',';'))]
    servers=[line[1] for line in lines if line[0]=='nameserver' and len(line)>=2]
    if len(body)>8192 or not servers:raise ValueError('experiment_resolver_invalid')
    for server in servers:ipaddress.ip_address(server)
    if not target.exists():
        with target.open('x') as stream:stream.write(body)
        target.chmod(0o600)
    return target


def manifest():
    data=json.loads(owned_path(phone_pg.root(),'records/app-images.json').read_text())
    if set(data['services'])!={'backend','frontend','postgres'} or data['run_id']!=RUN_ID:raise ValueError('three_service_manifest_invalid')
    for name in ('backend','frontend'):
        service=data['services'][name]
        if service['architecture']!='arm64' or not service['image'].startswith('angmoo-pg-exp/'+name+':'):
            raise ValueError('experiment_image_identity_invalid')
        marker=json.loads(owned_path(phone_pg.root(),service['rootfs']+'/.angmoo-image.json').read_text())
        if marker['image_id']!=service['image_id'] or marker['archive_sha256']!=service['archive_sha256']:
            raise ValueError('experiment_rootfs_identity_mismatch')
    return data


def command(service,*args,launch_id=None):
    base=phone_pg.root();data=manifest()['services'][service]
    proot=owned_path(base,'tools/proot-playstore')
    if hashlib.sha256(proot.read_bytes()).hexdigest()!=json.loads((base/'records/proot-build.json').read_text())['binary_sha256']:
        raise ValueError('experiment_proot_identity_mismatch')
    image=owned_path(base,data['rootfs'])
    cmd=['/system/bin/linker64',str(proot),'--kill-on-exit','--link2symlink','--sysvipc','-k','6.17.0-PRoot-Distro','-i','10001:10001',
        '-r',str(image),'-b','/dev','-b','/proc','-b','/sys','-b',str(base)+':/experiment','-b',str(base/'tmp')+':/tmp',
        '-b',str(base/'tmp/shm')+':/dev/shm','-b',str(resolver_file())+':/etc/resolv.conf',
        '-w','/app','/usr/bin/env','-i',
        'PATH=/app/.venv/bin:/usr/local/bin:/usr/bin:/bin','HOME=/tmp','LANG=C.UTF-8','LC_ALL=C.UTF-8',
        'PYTHONDONTWRITEBYTECODE=1','PYTHONUNBUFFERED=1','PYTHONPATH=/app','MALLOC_ARENA_MAX=2','NODE_ENV=production',
        'NEXT_TELEMETRY_DISABLED=1','PORT=13114','HOSTNAME=127.0.0.1','ANGMOO_API_BASE_URL=http://127.0.0.1:18114',
        'ANGMOO_VERSION=0.1.3','ANGMOO_SOURCE_SHA='+data['source_sha'],'ANGMOO_LAUNCH_ID='+(launch_id or uuid.uuid4().hex)]
    return cmd+list(args)


def run_backend(*args,timeout=600):
    result=subprocess.run(command('backend','python',*args),env=phone_pg.environment(),capture_output=True,text=True,timeout=timeout)
    return {'returncode':result.returncode,'stdout':result.stdout,'stderr':result.stderr}


def alive(record):
    try:
        return phone_pg.identity(record['pid'])==record and pathlib.Path(f"/proc/{record['pid']}/stat").read_text().rsplit(')',1)[1].split()[0]!='Z'
    except FileNotFoundError:return False


def selection():
    value=json.loads(owned_path(phone_pg.root(),'records/selection.json').read_text())
    if value['run_id']!=RUN_ID or value['state']!='VERIFIED':raise ValueError('experiment_activation_required')
    for key in ('data_root','dsn_file'):owned_path(phone_pg.root(),value[key])
    return value


def execution_mode():
    path=owned_path(phone_pg.root(),'records/execution-mode.json')
    if not path.exists():return 'validation'
    value=json.loads(path.read_text())
    chosen=selection()
    if (value.get('run_id')!=RUN_ID or value.get('mode') not in {'validation','real-use'}
            or any(value.get(k)!=chosen[k] for k in ('data_root','dsn_file'))):
        raise ValueError('experiment_execution_mode_invalid')
    return value['mode']


def set_execution_mode(mode):
    if mode not in {'validation','real-use'}:raise ValueError('experiment_execution_mode_invalid')
    # A restart is required: Python audit hooks cannot be removed in-process.
    if any(status(s)['alive'] for s in ('frontend','backend')):
        raise ValueError('experiment_mode_requires_stopped_app')
    previous=execution_mode();chosen=selection()
    value={'run_id':RUN_ID,'mode':mode,'previous_mode':previous,'changed_at_unix':time.time(),
        **{k:chosen[k] for k in ('data_root','dsn_file')}}
    name='execution-mode-'+uuid.uuid4().hex+'.json'
    phone_pg.record(name,value)
    temporary=owned_path(phone_pg.root(),'records/execution-mode.pending.json')
    with temporary.open('x') as stream:json.dump(value,stream,indent=2)
    temporary.chmod(0o600)
    os.replace(temporary,owned_path(phone_pg.root(),'records/execution-mode.json'))
    return value


def ready(service,nonce):
    url='http://127.0.0.1:'+('18114/health' if service=='backend' else '13114/api/runtime-identity')
    try:
        with urllib.request.urlopen(url,timeout=3) as response:value=json.loads(response.read(65536))
        item=manifest()['services'][service]
        if value.get('source_sha')!=item['source_sha'] or value.get('launch_id')!=nonce:return False
        if service=='backend':
            validation=execution_mode()=='validation'
            if (value.get('persistence')!='postgresql' or value.get('validation_mode') is not validation
                    or value.get('automatic_activity')!=('suspended' if validation else 'enabled')):return False
        return True
    except (OSError,ValueError):return False


def start(service):
    state=status(service)
    if state['ready']:return {'service':service,'state':'already_ready'}
    if state['alive']:raise ValueError(service+'_owned_process_not_ready')
    if service=='postgres':
        result=phone_pg.start()
        if result.get('status')!='ready':raise ValueError('postgres_start_not_ready')
        return result
    dependency='postgres' if service=='backend' else 'backend'
    if not status(dependency)['ready']:raise ValueError(service+'_dependency_not_ready')
    port={'backend':18114,'frontend':13114}[service]
    with socket.socket() as s:s.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1);s.bind(('127.0.0.1',port))
    nonce=uuid.uuid4().hex;chosen=selection()
    args=['python','-m','app.runtime.postgresql_backend','--data-root','/experiment/'+chosen['data_root'],
        '--dsn-file','/experiment/'+chosen['dsn_file'],'--mode',execution_mode()] if service=='backend' else ['node','app/server.js']
    logfile=owned_path(phone_pg.root(),'logs/'+service+'-'+nonce+'.log')
    with logfile.open('ab',buffering=0) as f:
        process=subprocess.Popen(command(service,*args,launch_id=nonce),env=phone_pg.environment(),stdin=subprocess.DEVNULL,stdout=f,stderr=f,start_new_session=True)
    record={'run_id':RUN_ID,'service':service,'proot':phone_pg.identity(process.pid),'launch_id':nonce,
        'rootfs':manifest()['services'][service]['rootfs'],'log':str(logfile),'state':'starting'}
    if service=='backend':record['execution_mode']=execution_mode()
    phone_pg.record(service+'-process.json',record)
    deadline=time.monotonic()+100
    while time.monotonic()<deadline:
        if process.poll() is not None:raise ValueError(service+'_start_failed:'+str(process.returncode))
        if ready(service,nonce):
            record['state']='ready';phone_pg.record(service+'-process.json',record);return record
        time.sleep(.5)
    raise ValueError(service+'_readiness_timeout')


def stop(service,*,record_name=None):
    if service=='postgres':
        if not status(service)['alive']:return {'service':service,'state':'already_stopped'}
        result=phone_pg.stop()
        if result.get('returncode')!=0:raise ValueError('postgres_normal_stop_incomplete')
        return result
    record_name=record_name or service+'-process.json'
    path=owned_path(phone_pg.root(),'records/'+record_name)
    if not path.exists():return {'service':service,'state':'never_started'}
    record=json.loads(path.read_text())
    if record['run_id']!=RUN_ID:raise ValueError('experiment_process_owner_mismatch')
    if not alive(record['proot']):return {'service':service,'state':'already_stopped'}
    pid=record['proot']['pid'];cmd=pathlib.Path(f'/proc/{pid}/cmdline').read_bytes()
    rootfs=str(owned_path(phone_pg.root(),record['rootfs'])).encode()
    if rootfs not in cmd:raise ValueError('experiment_process_command_mismatch')
    # Signal the owned traced application, not an unrelated process by name.
    children=[]
    for p in pathlib.Path('/proc').glob('[0-9]*'):
        try:
            fields=(p/'stat').read_text().rsplit(')',1)[1].split()
            if int(fields[1])==pid:children.append(phone_pg.identity(int(p.name)))
        except (OSError,ValueError):continue
    if not children:raise ValueError('experiment_child_identity_missing')
    for child in children:
        if alive(child):os.kill(child['pid'],signal.SIGTERM)
    deadline=time.monotonic()+45
    while alive(record['proot']) and time.monotonic()<deadline:time.sleep(.2)
    if alive(record['proot']):raise ValueError('experiment_normal_stop_incomplete')
    record['state']='stopped';phone_pg.record(record_name,record)
    return {'service':service,'state':'stopped'}


def status(service):
    path=owned_path(phone_pg.root(),'records/'+('process.json' if service=='postgres' else service+'-process.json'))
    if not path.exists():return {'alive':False,'ready':False}
    record=json.loads(path.read_text())
    if record['run_id']!=RUN_ID:raise ValueError('experiment_process_owner_mismatch')
    running=alive(record['proot'])
    if service!='postgres':return {'alive':running,'ready':running and ready(service,record['launch_id'])}
    if not running:return {'alive':False,'ready':False}
    if 'postgres' not in record or not alive(record['postgres']):return {'alive':True,'ready':False}
    phone_pg.verify_postmaster(record['postgres']['pid'])
    probe=phone_pg.sql('SELECT 1',timeout=5)
    return {'alive':True,'ready':probe['returncode']==0 and probe['stdout'].strip()=='1'}


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['start','stop','status','mode']);p.add_argument('service',choices=['postgres','backend','frontend','all','validation','real-use']);a=p.parse_args()
    os.umask(0o077)
    if (a.action=='mode')!=(a.service in {'validation','real-use'}):p.error('mode requires validation/real-use; other actions require a service')
    if a.action=='mode':
        result=set_execution_mode(a.service)
    elif a.action=='status':
        result={service:status(service) for service in (('postgres','backend','frontend') if a.service=='all' else (a.service,))}
    else:
        order=('postgres','backend','frontend') if a.action=='start' else ('frontend','backend','postgres')
        result={s:(start(s) if a.action=='start' else stop(s)) for s in (order if a.service=='all' else (a.service,))}
    print(json.dumps(result))
