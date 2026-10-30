"""Bind native Docker qualification to already-built release originals.

Creates only a synthetic 0.1.3 source in a fresh, labelled runner volume. Never
uploads the source database, generated credentials or migration backups.
"""
import argparse
import hashlib
import json
from pathlib import Path
import platform
import re
import subprocess
import sys
import time

from scripts.release.github import GitHub, successful_images
from scripts.release.candidate import load
from launcher.termux.payload import read_manifest, verify_archive, digest_file
from launcher.migrate.docker_migrate import private_directory


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for field in ('source','candidate-run','candidate-artifact','windows-run','windows-attempt','windows-artifact'):
        parser.add_argument('--'+field,required=True)
    parser.add_argument('--work-root',type=Path,required=True)
    args=parser.parse_args()
    assert re.fullmatch('[0-9a-f]{40}',args.source)
    assert all(re.fullmatch('[1-9][0-9]*',getattr(args,key)) for key in
        ('candidate_run','candidate_artifact','windows_run','windows_attempt','windows_artifact'))
    assert platform.machine().lower() in {'aarch64','arm64'},'native_arm64_runner_required'
    root=args.work_root.resolve();private_directory(root)
    (root/'records').mkdir()
    github=GitHub();github.main_source(args.source)
    run=github.run(args.candidate_run,'1',workflow='container-candidate.yml',source=args.source)
    artifact=github.artifact(args.candidate_artifact,run,name=f'release-candidate-{args.source}-1')
    candidate=github.download(artifact,root/'artifacts/candidate')
    manifest=read_manifest(candidate/'candidate.json');successful_images(manifest)
    assert manifest['source_sha']==args.source and manifest['version']=='0.1.4'
    arm={**manifest,'images':[v for v in manifest['images'] if v['platform']=='linux/arm64']}
    for image in arm['images']:verify_archive(candidate/image['archive'],image)
    selected=candidate/'native-arm64.json';selected.write_text(json.dumps(arm))
    load(selected)
    windows=github.run(args.windows_run,args.windows_attempt,workflow='windows-installer.yml',source=args.source)
    original=github.artifact(args.windows_artifact,windows,
        name=f'angmoo-windows-installer-{args.source}-{args.windows_attempt}')
    directory=github.download(original,root/'artifacts/windows')
    matches=list(directory.rglob('angmoo-migration-tools.json'));assert len(matches)==1
    tools=json.loads(matches[0].read_text());assert tools['source_sha']==args.source
    files={}
    for name,digest in tools['files'].items():
        paths=list(directory.rglob(name));assert len(paths)==1
        assert digest_file(paths[0])=='sha256:'+digest;files[name]=paths[0]
    inputs={'source_sha':args.source,'migration_python':str(files['angmoo-migrate.py']),
        'migration_exe':str(files['angmoo-migrate.exe'])}
    (root/'inputs.json').write_text(json.dumps(inputs,indent=2))

    def docker(*values):
        return subprocess.check_output(['docker',*map(str,values)],text=True,timeout=300).strip()
    previous=json.loads((Path(__file__).resolve().parents[2]/'docs/releases/0.1.3/p5.json').read_text())
    image='ghcr.io/angmoo-tree/angmoo-backend@'+previous['images']['backend/linux/arm64']
    docker('pull','--platform','linux/arm64',image)
    document=json.loads(docker('image','inspect',image))[0]
    assert document['Architecture']=='arm64'
    assert document['Config']['Labels']['org.opencontainers.image.revision']==previous['source_sha']
    assert document['Config']['Labels']['org.opencontainers.image.version']=='0.1.3'
    project='angmoo-n6-013-arm64';volume=project+'-data';container=project+'-backend'
    assert not docker('volume','ls','-q','--filter','name=^'+volume+'$')
    assert not docker('ps','-aq','--filter','name=^/'+container+'$')
    docker('volume','create','--label','io.angmoo.task=postgresql-docker-qualification',
        '--label','com.docker.compose.project='+project,
        '--label','com.docker.compose.volume=angmoo_contributor_embedded_data',volume)
    docker('run','--rm','--network','none','--user','0:0','--entrypoint','sh',
        '--mount','type=volume,src='+volume+',dst=/seed',image,'-ec','chown 10001:10001 /seed; chmod 700 /seed')
    docker('run','-d','--name',container,'--network','none','--platform','linux/arm64',
        '--label','io.angmoo.task=postgresql-docker-qualification',
        '--label','com.docker.compose.project='+project,'--label','com.docker.compose.service=backend',
        '--env','ANGMOO_CONTRIBUTOR_DATA_ROOT=/var/lib/angmoo',
        '--mount','type=volume,src='+volume+',dst=/var/lib/angmoo',image,'contributor-api')
    probe="import json,urllib.request;print(json.dumps(json.load(urllib.request.urlopen('http://127.0.0.1:8080/health',timeout=8))))"
    deadline=time.monotonic()+180
    while True:
        try:
            health=json.loads(docker('exec',container,'python','-c',probe))
            assert health['status']=='ok' and health['persistence']=='sqlite';break
        except Exception:
            assert time.monotonic()<deadline,'legacy_native_source_not_ready';time.sleep(2)
    seed='''from pathlib import Path
import http.cookiejar,json,sqlite3,urllib.request
root=Path('/var/lib/angmoo')
# The normal bootstrap is the only owner-creation path used by this fixture.
headers={'Origin':'http://127.0.0.1:3000','Host':'127.0.0.1:3000',
 'X-Angmoo-Frontend-Origin':'http://127.0.0.1:3000','Sec-Fetch-Site':'same-origin','Content-Type':'application/json'}
client=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
def request(method,suffix,body=None):
 data=json.dumps(body).encode() if body is not None else b'' if method=='POST' else None
 with client.open(urllib.request.Request('http://127.0.0.1:8080/api/v1/auth/local/bootstrap'+suffix,
      method=method,headers=headers,data=data),timeout=10) as response:return json.load(response)
status=request('GET','');assert status['state']=='unclaimed'
request('POST','/challenge')
claimed=request('POST','/prepare',{'protocol':2,'installation_id':status['installation_id'],
 'client_instance_id':'synthetic-native-qualification','expected_generation':0,'preferred_language':'en-US'})
assert claimed['user']['id']
databases=[]
for path in [*root.rglob('*.sqlite'),*root.rglob('*.sqlite3')]:
 with sqlite3.connect(path.as_uri()+'?mode=ro',uri=True) as db:
  tables={row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
  if {'users','angmoo_schema_version','site_operation_settings'}<=tables and db.execute('SELECT schema_version FROM angmoo_schema_version').fetchone()==(41,):databases.append(path)
assert len(databases)==1
with sqlite3.connect(databases[0]) as db:
 assert db.execute('SELECT count(*) FROM users').fetchone()==(1,)
 db.execute('INSERT INTO site_operation_settings(key,value) VALUES(?,?)',('native-migration-source-marker','한글 English 😀'))
uploads=root/'uploads';uploads.mkdir(exist_ok=True)
(uploads/'native-qualification.txt').write_text('Synthetic native ARM64 migration fixture. 한글 English 😀')
print(json.dumps({'schema':41,'normal_owner_bootstrap':True,'users':1,'marker_written':True,'synthetic_only':True}))
'''
    result=json.loads(docker('exec','--user','0:0',container,'python','-c',seed))
    docker('stop','--time','200',container)
    record={'source_sha':args.source,'legacy_source_sha':previous['source_sha'],
        'candidate_run':args.candidate_run,'candidate_artifact':args.candidate_artifact,
        'windows_run':args.windows_run,'windows_attempt':args.windows_attempt,'windows_artifact':args.windows_artifact,
        'migration_python_sha256':digest_file(files['angmoo-migrate.py']),
        'native_architecture':platform.machine(),'synthetic_source':result,'source_stopped':True,
        'provider_transmissions':0}
    (root/'records/source.json').write_text(json.dumps(record,indent=2)+'\n')
    print(json.dumps({'status':'READY','source_sha':args.source,'native_architecture':platform.machine()}))


if __name__=='__main__':main()
