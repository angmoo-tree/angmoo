"""Termux-only isolated migration operations. Never changes the installed wrapper."""
import argparse,hashlib,json,os,pathlib,shutil,time,uuid
import phone_app,phone_pg,phone_snapshot
from guard import RUN_ID,SOURCE_SHA,owned_path


def checked(result):
    if result['returncode']:
        # Driver output may include user SQL. Keep details private on the phone.
        name='operation-failure-'+uuid.uuid4().hex+'.json'
        phone_pg.record(name,result)
        raise ValueError('migration_operation_failed:'+name)
    return result


def convert(action,*,stop_after=None):
    args=['-m','app.runtime.postgresql_migration',action,'--work','/experiment/migration',
          '--dsn-file','/experiment/secrets/app-dsn']
    if stop_after:args+=['--stop-after',stop_after]
    result=checked(phone_app.run_backend(*args,timeout=1800))
    return json.loads(result['stdout'])


def stopped():
    for name in ('backend','frontend'):
        path=owned_path(phone_pg.root(),'records/'+name+'-process.json')
        if path.exists() and phone_app.alive(json.loads(path.read_text())['proot']):
            raise ValueError('migration_experiment_services_must_be_stopped')


def snapshot_current():
    phone_snapshot.quiescent()
    manifest=json.loads(owned_path(phone_pg.root(),'migration/snapshot.json').read_text())
    if phone_snapshot.manifest(phone_snapshot.SOURCE)!=manifest['files']:
        raise ValueError('migration_source_changed_since_snapshot')
    if phone_snapshot.manifest(owned_path(phone_pg.root(),'migration/D0'))!=manifest['files']:
        raise ValueError('migration_snapshot_changed')
    return manifest


def activate(*,restored=False):
    stopped();manifest=snapshot_current()
    if restored:
        result=json.loads(owned_path(phone_pg.root(),'records/restore-verification.json').read_text())
        if result.get('state')!='VERIFIED':raise ValueError('migration_restore_unverified')
        data,dsn='appdata-restore','secrets/restore-runtime-dsn'
    else:
        result=convert('verify')
        if not owned_path(phone_pg.root(),'appdata/runtime/graph-rebuild.json').is_file():
            checked(phone_app.run_backend('-m','app.runtime.postgresql_migration','prepare-app',
                '--work','/experiment/migration','--dsn-file','/experiment/secrets/app-dsn',timeout=1200))
        for row in manifest['files']:
            if row['path'].split('/')[0] in {'media','secrets'}:
                if phone_snapshot.digest_file(owned_path(phone_pg.root(),'appdata/'+row['path']))!=row['sha256']:
                    raise ValueError('migration_activation_file_mismatch')
        data,dsn='appdata','secrets/runtime-dsn'
    checked(phone_app.run_backend('/experiment/scripts/pg_runtime_role.py',timeout=60))
    marker=json.loads(owned_path(phone_pg.root(),data+'/runtime/postgresql-runtime.json').read_text())
    if marker.get('snapshot_digest')!=manifest['snapshot_digest']:raise ValueError('migration_appdata_snapshot_mismatch')
    value={'run_id':RUN_ID,'state':'VERIFIED','snapshot_digest':manifest['snapshot_digest'],
        'data_root':data,'dsn_file':dsn,'activated_at':time.time(),'automatic_activity':'suspended'}
    phone_pg.record('activation-'+uuid.uuid4().hex+'.json',value)
    phone_pg.record('selection.json',value)
    return {'state':'ACTIVATED','data_root':data,'installed_wrapper_changed':False,'automatic_activity':'suspended'}


def inspect():
    phone_snapshot.quiescent();root=phone_pg.root();rows=phone_snapshot.manifest(phone_snapshot.SOURCE)
    size=sum(x['size'] for x in rows);free=shutil.disk_usage(root).free
    result={'state':'SOURCE_STOPPED','source_files':len(rows),'source_bytes':size,
        'free_bytes':free,'minimum_free_bytes':size*4+1024**3,'space_sufficient':free>=size*4+1024**3,
        'supported_schema':[41],'source_schema':'requires_consistent_working_copy',
        'postgres_major':17,'pgvector':'0.8.7','windows_installer':'follow_up','docker_product':'follow_up'}
    if (root/'migration/snapshot.json').exists():result['source']=convert('inspect')
    return result


def pg_backup():
    stopped();root=phone_pg.root();selection=phone_app.selection()
    name='backups/'+time.strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:8]
    dest=owned_path(root,name);dest.mkdir(parents=True,mode=0o700)
    restored=selection['data_root']=='appdata-restore'
    db='angmoo_pg_run01_restore' if restored else 'angmoo_pg_run01'
    admin_dsn='secrets/restore-dsn' if restored else 'secrets/app-dsn'
    checked(phone_pg.run('pg_dump','-w','-h','127.0.0.1','-p','15414','-U',phone_pg.ROLE,
        '-d',db,'-Fc','--file=/experiment/'+name+'/database.dump',timeout=1200))
    for folder in ('media','secrets','runtime'):
        shutil.copytree(owned_path(root,selection['data_root']+'/'+folder),dest/folder)
    checked(phone_app.run_backend('/experiment/scripts/pg_fingerprint.py','--dsn-file','/experiment/'+admin_dsn,
        '--output','/experiment/'+name+'/database-fingerprint.json',timeout=600))
    rows=phone_snapshot.manifest(dest)
    value={'run_id':RUN_ID,'source_sha':SOURCE_SHA,'postgres_major':17,'required_role':phone_pg.ROLE,
        'required_roles':[phone_pg.ROLE,'angmoo_pg_run01_runtime'],
        'database':db,'selection':selection,'files':rows,'images':phone_app.manifest(),'state':'BACKUP_COMPLETE'}
    (dest/'manifest.json').write_text(json.dumps(value,indent=2)+'\n')
    return {'state':'BACKUP_COMPLETE','backup':name,'files':len(rows),'bytes':sum(r['size'] for r in rows)}


def pg_restore(relative):
    stopped();root=phone_pg.root();dest=owned_path(root,relative)
    if not relative.startswith('backups/'):raise ValueError('migration_backup_path_invalid')
    value=json.loads((dest/'manifest.json').read_text())
    if value['run_id']!=RUN_ID or value['postgres_major']!=17:raise ValueError('migration_backup_identity_invalid')
    actual=[x for x in phone_snapshot.manifest(dest) if x['path']!='manifest.json']
    if actual!=value['files']:raise ValueError('migration_backup_digest_mismatch')
    exists=checked(phone_pg.sql("SELECT EXISTS(SELECT 1 FROM pg_database WHERE datname='angmoo_pg_run01_restore')"))
    if exists['stdout'].strip()!='f':raise ValueError('migration_restore_target_exists')
    checked(phone_pg.sql('CREATE DATABASE angmoo_pg_run01_restore'))
    checked(phone_pg.run('pg_restore','-w','-h','127.0.0.1','-p','15414','-U',phone_pg.ROLE,
        '-d','angmoo_pg_run01_restore','--single-transaction','--exit-on-error',
        '/experiment/'+relative+'/database.dump',timeout=1200))
    dsn=owned_path(root,'secrets/app-dsn').read_text().strip()
    from urllib.parse import urlsplit,urlunsplit
    uri=urlsplit(dsn);dsn=urlunsplit((uri.scheme,uri.netloc,'/angmoo_pg_run01_restore',uri.query,uri.fragment))
    secret=owned_path(root,'secrets/restore-dsn')
    with secret.open('x') as f:f.write(dsn+'\n')
    secret.chmod(0o600)
    checked(phone_app.run_backend('/experiment/scripts/pg_fingerprint.py','--dsn-file','/experiment/secrets/restore-dsn',
        '--output','/experiment/records/restore-database-fingerprint.json',timeout=600))
    return finish_restore(relative)


def finish_restore(relative):
    stopped();root=phone_pg.root();dest=owned_path(root,relative)
    if not relative.startswith('backups/'):raise ValueError('migration_backup_path_invalid')
    value=json.loads((dest/'manifest.json').read_text())
    if value['run_id']!=RUN_ID or value['postgres_major']!=17:raise ValueError('migration_backup_identity_invalid')
    if [x for x in phone_snapshot.manifest(dest) if x['path']!='manifest.json']!=value['files']:
        raise ValueError('migration_backup_digest_mismatch')
    identity=checked(phone_pg.sql('SELECT run_id,source_sha FROM angmoo_experiment_identity',db='angmoo_pg_run01_restore'))
    if identity['stdout'].strip()!=RUN_ID+'|'+SOURCE_SHA:raise ValueError('migration_restore_owner_mismatch')
    # Compare counts, row hashes, sequences, extensions, ACLs, constraints,
    # indexes and triggers. Never accept only a successful pg_restore exit.
    result=checked(phone_app.run_backend('/experiment/scripts/pg_verify_backup.py',
        '/experiment/'+relative+'/database-fingerprint.json','/experiment/records/restore-database-fingerprint.json',timeout=30))
    verification=json.loads(result['stdout'])
    app=owned_path(root,'appdata-restore');app.mkdir(mode=0o700)
    for folder in ('media','secrets','runtime'):shutil.copytree(dest/folder,app/folder)
    marker=json.loads(owned_path(root,value['selection']['data_root']+'/runtime/postgresql-runtime.json').read_text())
    (app/'runtime/postgresql-runtime.json').write_text(json.dumps(marker)+'\n')
    checked(phone_app.run_backend('/experiment/scripts/pg_prepare_restored.py',timeout=1200))
    result={'state':'VERIFIED','run_id':RUN_ID,'backup':relative,'tables':verification['tables'],
        'snapshot_digest':marker['snapshot_digest'],'empty_target':True,'database_fingerprints_equal':True}
    phone_pg.record('restore-verification.json',result)
    return result


def rollback_to_snapshot():
    stopped();manifest=snapshot_current();root=phone_pg.root()
    target=owned_path(root,'migration/D2-recovery')
    if target.exists():raise ValueError('migration_recovery_destination_exists')
    shutil.copytree(owned_path(root,'migration/D0'),target,copy_function=shutil.copyfile)
    for p in (target,*target.rglob('*')):p.chmod(0o700 if p.is_dir() else 0o600)
    if phone_snapshot.manifest(target)!=manifest['files']:raise ValueError('migration_recovery_copy_mismatch')
    result={'state':'SNAPSHOT_RECOVERY_PREPARED','run_id':RUN_ID,'data_root':'migration/D2-recovery',
        'snapshot_digest':manifest['snapshot_digest'],'postgres_changes_backported':False,
        'installed_data_untouched':True,'recovery_time':'D0 snapshot time only'}
    phone_pg.record('rollback-selection.json',result)
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['inspect','dry-run','backup','convert','verify','resume','abort','activate','pg-backup','pg-restore','pg-resume-restore','activate-restored','rollback-to-snapshot'])
    parser.add_argument('--backup');parser.add_argument('--stop-after',choices=['canonical','vectors','checkpoints']);a=parser.parse_args()
    os.umask(0o077)
    try:
        if a.action in {'inspect','dry-run'}:result=inspect()
        elif a.action=='backup':result=phone_snapshot.backup()
        elif a.action in {'convert','verify','resume','abort'}:stopped();result=convert(a.action,stop_after=a.stop_after)
        elif a.action=='activate':result=activate()
        elif a.action=='activate-restored':result=activate(restored=True)
        elif a.action=='pg-backup':result=pg_backup()
        elif a.action=='pg-restore':result=pg_restore(a.backup or '')
        elif a.action=='pg-resume-restore':result=finish_restore(a.backup or '')
        else:result=rollback_to_snapshot()
        print(json.dumps(result,ensure_ascii=False))
    except Exception as exc:
        print(json.dumps({'state':'FAILED','reason':str(exc) if isinstance(exc,ValueError) else type(exc).__name__}))
        raise SystemExit(2) from None
