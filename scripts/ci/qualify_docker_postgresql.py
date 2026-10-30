"""Final-source qualification on the new owned copies, never the old fixtures.

This is private orchestration. The distributed, source-stamped migration tool
owns conversion, selection, resume and rollback. All created resources remain.
"""
import argparse, hashlib, importlib.util, json, re, shutil, subprocess, time
import urllib.request,platform
from pathlib import Path
from types import SimpleNamespace

TASK='postgresql-docker-qualification'
p=argparse.ArgumentParser()
p.add_argument('arch',choices=('amd64','arm64'))
p.add_argument('--inputs',type=Path,required=True)
p.add_argument('--work-root',type=Path,required=True)
p.add_argument('--resume-qualification',action='store_true')
p.add_argument('--source-already-running',action='store_true')
a=p.parse_args(); arch=a.arch;RUN=a.work_root.resolve()
inputs=json.loads(a.inputs.read_text()); source=inputs['source_sha']
assert re.fullmatch('[0-9a-f]{40}',source)
spec=importlib.util.spec_from_file_location('shipped_docker_migrator',inputs['migration_python'])
tool=importlib.util.module_from_spec(spec);spec.loader.exec_module(tool)
assert tool.BUILD_SOURCE==source
d=tool.Docker(); fixture='angmoo-n6-013-'+arch+'-backend'
old=d.json('inspect',fixture)[0]
assert old['Config']['Labels']['io.angmoo.task']==TASK
assert not old['State']['Running'] or (a.source_already_running and not a.resume_qualification)
assert old['Config']['Labels']['org.opencontainers.image.version']=='0.1.3'
helper='angmoo-backend-candidate:'+source+'-'+arch
images={s:'angmoo-'+s+'-candidate:'+source+'-'+arch for s in ('backend','frontend','postgres')}
for name in images.values():
    image=d.json('image','inspect',name)[0]
    assert image['Config']['Labels']['org.opencontainers.image.revision']==source
    assert image['Architecture']==arch

def ready(container):
    deadline=time.monotonic()+240
    while True:
        try:
            value=json.loads(d.run('exec',container,'python','-c',
                "import json,urllib.request;print(json.dumps(json.load(urllib.request.urlopen('http://127.0.0.1:8080/health',timeout=8))))"))
            assert value['status']=='ok';return value
        except Exception:
            if time.monotonic()>deadline:raise
            time.sleep(2)

def browser(port):
    with urllib.request.urlopen(f'http://127.0.0.1:{port}/',timeout=20) as r:assert r.status==200
    with urllib.request.urlopen(f'http://127.0.0.1:{port}/api/runtime-identity',timeout=20) as r:v=json.load(r)
    assert v['source_sha']==source and v['version']=='0.1.4'
    return v

backup=RUN/'backups'/('docker-'+arch+'-'+source[:12])
assert backup.exists()==a.resume_qualification
port=13314 if arch=='amd64' else 13316
args=SimpleNamespace(language='ko',source_volume=None,source_directory=None,source_project=None,
    backup_directory=str(backup),required_free_gib=4,port=port,resume=None,validation=True,
    **{s+'_image':ref for s,ref in images.items()})
if not a.resume_qualification:
    d.run('start',fixture)
    assert ready(fixture)['persistence']=='sqlite'
    items=tool.discover(d)
    index=next(i for i,v in enumerate(items,1) if v['project']=='angmoo-n6-013-'+arch)
    assert items[index-1]['containers']==[old['Id']]
    selected=tool.choose(items,args,ask=lambda _:str(index))
    assert selected['source']=='angmoo-n6-013-'+arch+'-data'
    if arch=='amd64':
        command=[inputs['migration_exe'],'--language','ko','--backup-directory',str(backup),
            '--port',str(port),'--validation']
        for service,ref in images.items():command+=['--'+service+'-image',ref]
        r=subprocess.run(command,input=(str(index)+'\nyes\n' if len(items)>1 else 'yes\n').encode(),
            capture_output=True,timeout=1800)
        for stream in ('stdout','stderr'):(RUN/'records'/('n6-docker-'+arch+'-'+stream+'.raw')).write_bytes(getattr(r,stream))
        assert r.returncode==0,'packaged_migration_failed_see_private_record'
    else:
        class Interrupted(tool.Docker):
            def run(self,*values,**kwargs):
                result=super().run(*values,**kwargs)
                if 'app.runtime.postgresql_installation' in values and 'migrate' in values:
                    raise RuntimeError('qa_interrupted_after_verified_store')
                return result
        try:tool.migrate(Interrupted(),selected,args,ask=lambda _:'yes')
        except RuntimeError as e:assert str(e)=='qa_interrupted_after_verified_store'
        else:raise AssertionError('fault_injection_not_exercised')
        partial_root=next(backup.glob('0.1.3-to-0.1.4-*'))
        partial=json.loads((partial_root/'migration.json').read_text())
        assert partial['phase']=='failed' and 'verified' not in partial['done']
        args.resume=partial_root;tool.migrate(d,None,args,ask=lambda _:'yes')

root=next(backup.glob('0.1.3-to-0.1.4-*'))
state=json.loads((root/'migration.json').read_text())
assert state['phase']=='active' and state['target_source']==source
compose=state['compose_file']; identity=browser(port)
backend_container=d.run('compose','-f',compose,'ps','-q','backend')
d.run('cp',str(Path(__file__).with_name('postgresql_candidate_data_probe.py')),backend_container+':/tmp/n6-data-probe.py')
search_probe=json.loads(d.run('exec','--env','PYTHONPATH=/app',backend_container,'python','/tmp/n6-data-probe.py',
    '--data-root','/var/lib/angmoo','--source',source,timeout=180))
assert search_probe['status']=='PASS' and search_probe['source_sha']==source
(RUN/'records'/('n6-docker-'+arch+'-migrated-search.json')).write_text(json.dumps(search_probe,indent=2)+'\n',encoding='utf-8')
marker='n6-'+arch+'-'+source[:12]
write="""import json
from pathlib import Path
import psycopg
dsn=Path('/var/lib/angmoo/secrets/postgresql-runtime-dsn').read_text().strip().replace('postgresql+psycopg://','postgresql://')
with psycopg.connect(dsn) as db:
 db.execute('INSERT INTO site_operation_settings(key,value) VALUES(%s,%s)',(MARKER,'한글 English 😀'))
 counts={table:db.execute('SELECT count(*) FROM '+table).fetchone()[0] for table in ('users','worlds','world_characters','posts','memory_items','relationship_states')}
print(json.dumps({'new_write':True,'counts':counts}))
""".replace('MARKER',repr(marker))
counts=json.loads(d.run('compose','-f',compose,'exec','-T','backend','python','-c',write))
read=write[:write.index(' db.execute(')]+" assert db.execute('SELECT value FROM site_operation_settings WHERE key=%s',("+repr(marker)+",)).fetchone()==('한글 English 😀',)\n"

def stop_owned(file):
    for identifier in d.run('compose','-f',file,'ps','-aq').split():
        assert tool.owned(d,'container',identifier,state['installation_id'])
    d.run('compose','-f',file,'stop','--timeout','200',timeout=300)

stop_owned(compose)
d.run('compose','-f',compose,'start',timeout=300)
ready(d.run('compose','-f',compose,'ps','-q','backend'))
browser(port);d.run('compose','-f',compose,'exec','-T','backend','python','-c',read)
stop_owned(compose)
cold=root/'cold-backup';cold.mkdir();shutil.copytree(root/'secrets',cold/'secrets')
inventory_program="""import hashlib,json
from pathlib import Path
r=Path('/source')
print(json.dumps({str(p.relative_to(r)):{'sha256':hashlib.file_digest(p.open('rb'),'sha256').hexdigest(),'bytes':p.stat().st_size,'mode':p.stat().st_mode&0o777,'uid':p.stat().st_uid,'gid':p.stat().st_gid} for p in sorted(r.rglob('*')) if p.is_file()}))
"""
def inventory(volume):
    return json.loads(d.run('run','--rm','--network','none','--user','0:0','--entrypoint','python',
        '--mount','type=volume,src='+volume+',dst=/source,readonly',helper,'-c',inventory_program,timeout=300))

copies={};receipts={}
for service,volume in state['volumes'].items():
    assert tool.owned(d,'volume',volume,state['installation_id'])
    before=inventory(volume)
    d.run('run','--rm','--network','none','--user','0:0','--entrypoint','tar',
        '--mount','type=volume,src='+volume+',dst=/source,readonly',
        '--mount','type=bind,src='+str(cold)+',dst=/backup',helper,
        '-C','/source','-czpf','/backup/'+service+'.tar.gz','.',timeout=600)
    restored=volume+'-n6-restore';assert not d.run('volume','ls','-q','--filter','name=^'+restored+'$')
    d.run('volume','create','--label','io.angmoo.installation='+state['installation_id'],
        '--label','io.angmoo.task='+TASK,restored)
    d.run('run','--rm','--network','none','--user','0:0','--entrypoint','tar',
        '--mount','type=volume,src='+restored+',dst=/restore',
        '--mount','type=bind,src='+str(cold)+',dst=/backup,readonly',helper,
        '-C','/restore','-xzpf','/backup/'+service+'.tar.gz',timeout=600)
    assert inventory(restored)==before
    archive=cold/(service+'.tar.gz')
    receipts[service]={'files':len(before),'bytes':archive.stat().st_size,
        'sha256':hashlib.file_digest(archive.open('rb'),'sha256').hexdigest(),'exact_inventory_match':True}
    (cold/(service+'-inventory.json')).write_text(json.dumps(before,indent=2))
    copies[service]=restored
restore_root=root/'restored';restore_root.mkdir();shutil.copytree(cold/'secrets',restore_root/'secrets')
restored_state={**state,'network':state['network']+'-n6-restore','volumes':copies,
    'port':13324 if arch=='amd64' else 13326}
restore_compose=tool.write_compose(restore_root,restored_state,validation=True)
try:
    d.run('compose','-f',restore_compose,'up','-d','--wait','--wait-timeout','240',timeout=300)
    browser(restored_state['port'])
    d.run('compose','-f',restore_compose,'exec','-T','backend','python','-c',read)
finally:stop_owned(restore_compose)
result=tool.rollback(d,root,args,ask=lambda _:'yes');assert result['state']=='rolled_back'
assert ready(fixture)['persistence']=='sqlite'
d.run('stop','--time','200',fixture,timeout=300)
report={'status':'PASS','source_sha':source,'platform':'docker-'+arch,'source_version':'0.1.3',
    'target_schema':5,'migration':True,'new_write_restart':True,'backup_restore':True,'rollback':True,
    'counts':counts['counts'],'browser_identity':identity,'backup_archives':receipts,
    'adapter':'packaged Windows exe' if arch=='amd64' else 'source-stamped Python launcher',
    'host':platform.platform(),'arm64_emulation':arch=='arm64' and platform.machine().lower() not in {'aarch64','arm64'},'macos_qualification':False,
    'old_original_fixture_untouched':True,'owned_source_copy_stopped':True,'provider_transmissions':0,
    'migration_record':str(root/'migration.json')}
(RUN/'records'/('n6-docker-'+arch+'.json')).write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({k:report[k] for k in ('status','source_sha','platform','migration','new_write_restart','backup_restore','rollback')}))
