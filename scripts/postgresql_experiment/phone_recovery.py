"""Copy old image trees into owned trial storage and run the D0 recovery harness."""
import hashlib,json,os,pathlib,shutil,socket,subprocess,time,uuid,urllib.request
import phone_app,phone_pg,phone_migrate,phone_snapshot
from guard import RUN_ID,SOURCE_SHA,owned_path

OLD_SHA='01ef3847c77a890071728b7f618f18fa88b775bf'


def prepare():
    phone_migrate.stopped();phone_migrate.snapshot_current();root=phone_pg.root()
    result=phone_migrate.rollback_to_snapshot()
    images={}
    for service in ('backend','frontend'):
        source=pathlib.Path('/data/data/com.termux/files/usr/var/lib/proot-distro/containers')/('angmoo-'+service+'-01ef3847c77a-ad198e1d4208')
        metadata=json.loads((source/'manifest.json').read_text())
        if not metadata['image_ref'].startswith('ghcr.io/angmoo-tree/angmoo-'+service+'@sha256:'):raise ValueError('recovery_original_image_invalid')
        dest=owned_path(root,'recovery-images/'+service)
        if dest.exists():raise ValueError('recovery_image_destination_exists')
        shutil.copytree(source/'rootfs',dest,symlinks=True)
        entry='app/app/runtime/contributor_backend.py' if service=='backend' else 'app/app/server.js'
        before=phone_snapshot.digest_file(source/'rootfs'/entry)
        if phone_snapshot.digest_file(dest/entry)!=before:raise ValueError('recovery_code_copy_mismatch')
        images[service]={'rootfs':str(dest.relative_to(root)),'source_sha':OLD_SHA,'original_image':metadata['image_ref'],'entry_sha256':before}
    phone_pg.record('recovery-images.json',{'run_id':RUN_ID,'images':images})
    return {'snapshot':result,'images':images}


def start(service):
    phone_migrate.stopped();root=phone_pg.root()
    image=json.loads(owned_path(root,'records/recovery-images.json').read_text())['images'][service]
    with socket.socket() as s:s.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1);s.bind(('127.0.0.1',18114 if service=='backend' else 13114))
    # Reuse the verified experiment PRoot command but select the copied old image.
    args=('python','/experiment/scripts/sqlite_recovery_backend.py') if service=='backend' else ('node','app/server.js')
    nonce=uuid.uuid4().hex;cmd=phone_app.command(service,*args,launch_id=nonce)
    cmd[cmd.index('-r')+1]=str(owned_path(root,image['rootfs']))
    cmd=[('ANGMOO_SOURCE_SHA='+OLD_SHA) if x.startswith('ANGMOO_SOURCE_SHA=') else x for x in cmd]
    log=owned_path(root,'logs/recovery-'+service+'-'+nonce+'.log')
    with log.open('ab',buffering=0) as f:p=subprocess.Popen(cmd,env=phone_pg.environment(),stdin=subprocess.DEVNULL,stdout=f,stderr=f,start_new_session=True)
    record={'run_id':RUN_ID,'service':service,'proot':phone_pg.identity(p.pid),'rootfs':image['rootfs'],'launch_id':nonce,'log':str(log),'state':'starting'}
    phone_pg.record('recovery-'+service+'-process.json',record)
    until=time.monotonic()+180
    while time.monotonic()<until:
        if p.poll() is not None:raise ValueError('recovery_start_failed:'+str(p.returncode))
        try:
            url='http://127.0.0.1:'+('18114/health' if service=='backend' else '13114/api/runtime-identity')
            with urllib.request.urlopen(url,timeout=2) as r:
                payload=json.load(r);label=r.headers.get('X-Angmoo-Validation')
            if payload.get('source_sha')==OLD_SHA and payload.get('launch_id')==nonce:
                if service=='backend' and (payload.get('persistence')!='sqlite' or label!='old-version-D0-recovery-read-smoke'):raise ValueError('recovery_health_identity_invalid')
                record['state']='ready';phone_pg.record('recovery-'+service+'-process.json',record)
                return {'service':service,'state':'ready','identity':payload,'validation':'old-version-D0-recovery-read-smoke'}
        except (OSError,ValueError):pass
        time.sleep(.5)
    raise ValueError('recovery_readiness_timeout')


def stop(service):
    # phone_app uses the same PID/start/boot/rootfs guard for every owned service.
    return phone_app.stop(service,record_name='recovery-'+service+'-process.json')


if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('action',choices=['prepare','start','stop']);p.add_argument('service',nargs='?',choices=['backend','frontend']);a=p.parse_args()
    os.umask(0o077)
    print(json.dumps(prepare() if a.action=='prepare' else start(a.service) if a.action=='start' else stop(a.service)))
