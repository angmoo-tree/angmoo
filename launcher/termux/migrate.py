"""Explicit 0.1.3 source selection, copied-data migration and reversible selection."""
from __future__ import annotations
import json
import hashlib
from pathlib import Path
import shutil
import subprocess
import uuid
from payload import require,read_manifest
from processes import atomic_json, identity, stop_child, free_port
import postgres_host


TEXT={
 'en':{'review':'Migrate this 0.1.3 installation? The original and backup will be preserved. [yes/no] ',
       'rollback':'Return to the preserved 0.1.3 installation? New PostgreSQL data stays separate. [yes/no] ',
       'ready':'Migration verified. Start Angmoo to use the selected PostgreSQL installation.',
       'rolled_back':'Returned to the preserved 0.1.3 installation. Start Angmoo to use it. New PostgreSQL data is preserved separately.',
       'cancel':'Cancelled. The existing installation is preserved.'},
 'ko':{'review':'이 0.1.3 설치를 이전할까요? 원본과 백업을 보존합니다. [yes/no] ',
       'rollback':'보존한 0.1.3 설치로 복귀할까요? PostgreSQL의 새 데이터는 별도로 남습니다. [yes/no] ',
       'ready':'이전 검증을 완료했습니다. Angmoo를 시작하면 선택한 PostgreSQL 설치를 사용합니다.',
       'rolled_back':'보존한 0.1.3 설치로 복귀했습니다. Angmoo를 시작하면 해당 설치를 사용합니다. PostgreSQL의 새 데이터는 별도로 보존됩니다.',
       'cancel':'취소했습니다. 기존 설치는 보존됩니다.'}}


def selected(home):
    path=home/'selection.json'
    if not path.exists():return home
    require(not path.is_symlink(),'migration_selection_link')
    value=json.loads(path.read_text())
    target=Path(value['target_home'])
    require(value.get('schema')=='angmoo-termux-selection.v1' and target.parent==home.parent
        and target.name==home.name+'-postgresql' and not target.is_symlink(),'migration_selection_invalid')
    require(not (target/'selection.json').exists(),'migration_selection_nested')
    return target


def target_signature(manifest):
    return (manifest['version'],manifest['source_sha'],tuple(sorted(
        (item['service'],item['manifest_digest'],item['config_digest'])
        for item in manifest['images'] if item['platform']=='linux/arm64')))


def require_resume_target(config,args):
    candidate=getattr(args,'candidate_manifest',None)
    local=candidate or getattr(args,'manifest',None)
    if local:
        requested=read_manifest(Path(local),require_all=not bool(candidate))
        require(target_signature(requested)==target_signature(config['manifest']),'migration_resume_target_changed')
    elif getattr(args,'release',None):
        require(config['manifest']['version']==args.release,'migration_resume_target_changed')


def run(home,args,ask=input):
    import angmoo
    text=TEXT[args.language]
    target=home.with_name(home.name+'-postgresql')
    if args.rollback:
        require(selected(home)==target,'migration_no_selected_target')
        if ask(text['rollback']).strip().lower()!='yes':print(text['cancel']);return
        angmoo.stop(target)
        (home/'selection.json').rename(home/('selection-rollback-'+uuid.uuid4().hex+'.json'))
        print(text['rolled_back']);return
    # A resumed conversion keeps its original immutable target. Validate the
    # newly requested source before stopping the old installation or copying.
    if (target/'installation.json').exists():
        require_resume_target(angmoo.installation(target),args)
    old=angmoo.installation(home)
    require(old['manifest']['version']=='0.1.3' and 'postgres' not in old['containers'],'migration_source_version_unsupported')
    source=Path(old['data_root'])
    required=sum(p.stat().st_size for p in source.rglob('*') if p.is_file())*3+4*1024**3
    available=shutil.disk_usage(home).free
    require(available>=required,'migration_disk_space_low')
    print(json.dumps({'source_home':str(home),'source_version':'0.1.3','target_home':str(target),
        'backup':str(target/'migration/work/D0'),'required_bytes':required,'available_bytes':available},ensure_ascii=False,indent=2))
    if ask(text['review']).strip().lower()!='yes':print(text['cancel']);return
    angmoo.stop(home)
    with angmoo.lock(home):
        target=angmoo.private_home(target)
        if not (target/'installation.json').exists():
            angmoo.install(target,args.release,args.manifest,args.candidate_manifest)
        config=angmoo.installation(target)
        require(config['manifest']['version']=='0.1.4','migration_target_version_unsupported')
        ports={'postgres':args.postgres_port,'backend':args.backend_port,'frontend':args.frontend_port}
        require(len(set(ports.values()))==3 and all(1<=p<=65535 for p in ports.values()),'migration_ports_invalid')
        for port in ports.values():free_port(port)
        config.update(home=str(target),ports=ports,validation_mode=args.validation)
        atomic_json(target/'installation.json',config)
        state=postgres_host.prepare(target,ports)
        stage=target/'migration/source'
        marker=target/'migration/source-copy.json'
        stage.mkdir(mode=0o700,parents=True,exist_ok=True)
        inventory=[{'path':str(p.relative_to(source)),'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
                   for p in sorted(source.rglob('*')) if p.is_file()]
        require(not any(p.is_symlink() for p in source.rglob('*')),'migration_source_link_refused')
        if marker.exists():require(json.loads(marker.read_text())==inventory,'migration_source_changed')
        else:atomic_json(marker,inventory)
        for row in inventory:
            destination=stage/row['path']
            if not destination.exists():
                destination.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
                shutil.copy2(source/row['path'],destination)
            require(hashlib.sha256(destination.read_bytes()).hexdigest()==row['sha256'],'migration_source_copy_mismatch')
        executable=angmoo.tools()
        # The canonical engine hashes D0/D1, validates schema and source rows,
        # and does not touch this source installation's SQLite files.
        postgres_host.common(executable,config,'snapshot','--source-root','/migration/migration/source',
            '--work','/migration/migration/work','--installation-id',state['installation_id'])
        with (target/'migration/postgres.log').open('ab') as stream:
            process=subprocess.Popen(postgres_host.command(executable,config),env=postgres_host.host_environment(config),
                stdin=subprocess.DEVNULL,stdout=stream,stderr=subprocess.STDOUT,start_new_session=True)
            owner=identity(process.pid)
            try:
                postgres_host.wait_ready(executable,config,process)
                postgres_host.common(executable,config,'migrate','--work','/migration/migration/work','--data-root','/var/lib/angmoo',
                    '--owner-dsn-file','/migration/credentials/owner-dsn','--runtime-dsn-file','/migration/credentials/runtime-dsn')
            finally:
                try:postgres_host.stop(executable,config,owner)
                finally:stop_child(process,owner,30)
        # Selection occurs only after canonical, search, checkpoint and file
        # verification succeeds. Starting the application remains explicit.
        atomic_json(home/'selection.json',{'schema':'angmoo-termux-selection.v1','target_home':str(target),
            'installation_id':state['installation_id']})
        print(text['ready'])
