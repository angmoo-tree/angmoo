"""Current native installer and bounded qualification safety contracts."""
from copy import deepcopy
import hashlib,json
import os,shutil,subprocess
from pathlib import Path
import pytest
from app.runtime import windows_postgresql as native
from app.runtime.installer_update import InstallerPayloadContract,InstallerUpdateContractError
from scripts.ci.windows_postgresql_coverage import CHECKS,KINDS,SCHEMA,verify_reports
from scripts.ci.run_windows_postgresql_qualification import hosted_root,wait_for_host
from scripts.release.windows_receipt import aggregate
from scripts.build_windows_postgresql import utf8_manifest


def test_native_utf8_manifest_keeps_existing_process_contracts():
    import xml.etree.ElementTree as ET
    original=b'''<assembly xmlns="urn:schemas-microsoft-com:asm.v1" manifestVersion="1.0">
      <trustInfo xmlns="urn:schemas-microsoft-com:asm.v3"><security><requestedPrivileges>
      <requestedExecutionLevel level="asInvoker" uiAccess="false" />
      </requestedPrivileges></security></trustInfo></assembly>'''
    for value in (None,original):
        manifest=utf8_manifest(value)
        root=ET.fromstring(manifest)
        assert root.find('.//{http://schemas.microsoft.com/SMI/2019/WindowsSettings}activeCodePage').text=='UTF-8'
        assert utf8_manifest(manifest)==manifest
        if value:
            assert root.find('.//{urn:schemas-microsoft-com:asm.v3}requestedExecutionLevel').attrib=={'level':'asInvoker','uiAccess':'false'}

def resources(tmp_path):
    root=tmp_path/'resources';(root/'bin').mkdir(parents=True)
    (root/'bin/postgres.exe').write_bytes(b'synthetic-resource')
    manifest={'postgresql':'17.11','pgvector':'0.8.7','platform':'windows-x64',
              'files':{'bin/postgres.exe':hashlib.sha256(b'synthetic-resource').hexdigest()}}
    (root/'angmoo-resources.json').write_text(json.dumps(manifest))
    return root

def reports():
    values=[]
    for kind in sorted(KINDS):
        checks={k:True for k in CHECKS}
        if kind!='clean-install':checks['migration_consent']=True
        if kind=='failure-recovery':checks.update(interrupted_after_canonical=True,same_migration_resumed=True)
        values.append({'schema':SCHEMA,'status':'PASS','source_sha':'a'*40,'run_id':'10','run_attempt':'2',
            'kind':kind,'checks':checks,'source_version':None if kind=='clean-install' else '0.1.3',
            'target_schema':5,'resources_sha256':'b'*64})
    return values

def test_current_windows_union_requires_all_actual_cases_and_one_resource_set():
    assert verify_reports(reports(),source_sha='a'*40,run_id='10',run_attempt='2')['source_versions']==['0.1.3']
    receipts=[{'schema':'angmoo-installer-test.v1','status':'PASS','source_sha':'a'*40,'run_id':'10','attempt':'2',
        'kind':kind,'artifact_id':'99','exe':{'name':'Angmoo_0.1.4_x64-setup.exe','sha256':'sha256:'+'c'*64,'size':123}}
        for kind in sorted(KINDS)]
    assert aggregate(receipts,reports(),source='a'*40,run='10',attempt='2')['coverage']['target_schema']==5

@pytest.mark.parametrize('fault',['missing','duplicates','failed','not_run','source','attempt','resources','unchecked','private','wrong_version'])
def test_current_union_cannot_hide_missing_checks_or_wrong_bytes(fault):
    values=deepcopy(reports())
    if fault=='missing':values.pop()
    elif fault=='duplicates':values[1]=deepcopy(values[0])
    elif fault=='failed':values[0]['status']='FAIL'
    elif fault=='not_run':values[0]['status']='NOT_RUN'
    elif fault=='source':values[0]['source_sha']='d'*40
    elif fault=='attempt':values[0]['run_attempt']='3'
    elif fault=='resources':values[0]['resources_sha256']='d'*64
    elif fault=='unchecked':values[0]['checks']['restart']=False
    elif fault=='private':values[0]['data_root']='private'
    elif fault=='wrong_version':values[0]['target_schema']=4
    with pytest.raises(ValueError):verify_reports(values,source_sha='a'*40,run_id='10',run_attempt='2')

def test_installer_harness_cannot_run_against_developer_installation(monkeypatch):
    monkeypatch.delenv('GITHUB_ACTIONS',raising=False)
    with pytest.raises(ValueError,match='hosted_only'):hosted_root()


def test_consent_automation_cannot_run_against_developer_windows(monkeypatch):
    from scripts.ci.windows_migration_consent import accept_owned_migration_dialog
    monkeypatch.delenv('GITHUB_ACTIONS',raising=False)
    with pytest.raises(ValueError,match='hosted_only'):accept_owned_migration_dialog(os.getpid())


@pytest.mark.parametrize('scenario',['slow_initial','fatal','missing_consent','missing_token_gate'])
def test_real_host_wait_preserves_cold_start_and_authentication(monkeypatch,tmp_path,scenario):
    from types import SimpleNamespace
    import urllib.error
    from scripts.ci import run_windows_postgresql_qualification as harness
    endpoint=tmp_path/'endpoint.json';clock=[0.0];prompts=[]
    child=SimpleNamespace(pid=123,poll=lambda:7 if scenario=='fatal' else None)
    def sleep(seconds):
        clock[0]+=seconds
        if clock[0]>=200:endpoint.write_text('{"dynamic_port":12345}')
    def health(*args,**kwargs):
        if scenario!='missing_token_gate':raise urllib.error.HTTPError('',401,'unauthorized',None,None)
        return None
    def consent(pid):
        prompts.append(pid)
        return scenario!='missing_consent'
    monkeypatch.setattr(harness.time,'monotonic',lambda:clock[0])
    monkeypatch.setattr(harness.time,'sleep',sleep)
    monkeypatch.setattr(harness.urllib.request,'urlopen',health)
    if scenario=='slow_initial':
        wait_for_host(child,endpoint,timeout=330,confirm=consent)
        assert clock[0]==200 and prompts==[123]
    else:
        error={'fatal':'actual_host_not_ready','missing_consent':'consent_not_observed',
               'missing_token_gate':'token_gate_missing'}[scenario]
        with pytest.raises(ValueError,match=error):wait_for_host(child,endpoint,timeout=330,confirm=consent)
        if scenario=='fatal':assert clock[0]==0

def test_native_restarts_keep_credentials_but_missing_credentials_fail_closed(tmp_path):
    bundle=resources(tmp_path);root=tmp_path/'Angmoo PostgreSQL 한글'
    manager=native.NativePostgres(root,bundle)
    first=manager.runtime_file.read_bytes()
    assert native.NativePostgres(root,bundle).runtime_file.read_bytes()==first
    (root/'cluster').mkdir();(root/'cluster/PG_VERSION').write_text('17')
    manager.runtime_file.unlink()
    with pytest.raises(ValueError,match='credentials_missing'):native.NativePostgres(root,bundle)
    assert not manager.runtime_file.exists()

def test_native_resources_are_checked_before_start_or_data_creation(tmp_path):
    bundle=resources(tmp_path);(bundle/'bin/postgres.exe').write_bytes(b'corrupt')
    with pytest.raises(ValueError,match='resource_hash_mismatch'):native.NativePostgres(tmp_path/'data',bundle)
    assert not (tmp_path/'data').exists()


@pytest.mark.skipif(os.name!='nt',reason='real Windows byte-lock read semantics')
def test_native_snapshot_keeps_serving_ownership_and_excludes_only_live_control_files(tmp_path):
    from app.runtime.migrations.canonical_retention import ServingRetentionOwner
    from app.runtime.migrations.generation import EmbeddedUpgradeLock,EmbeddedGenerationError
    runtime=tmp_path/'runtime';runtime.mkdir()
    (runtime/'activity').mkdir();(runtime/'activity/checkpoints.sqlite').write_bytes(b'synthetic-checkpoint')
    (runtime/'sidecar.owner.json').write_text('{"pid":123}')
    owner=ServingRetentionOwner(tmp_path,enabled=False).acquire()
    try:
        result=native.source_inventory(tmp_path)['runtime']
        assert [row['path'] for row in result]==['activity/checkpoints.sqlite']
        assert result[0]['sha256']==hashlib.sha256(b'synthetic-checkpoint').hexdigest()
        # Copying must never release the lifetime lock to make the read work.
        with pytest.raises(EmbeddedGenerationError,match='embedded_upgrade_locked'):
            with EmbeddedUpgradeLock(runtime/'canonical-serving.lock'):pass
    finally:owner.close()

def test_native_conversion_requires_explicit_consent_before_cluster_creation(tmp_path):
    root=tmp_path/'old';(root/'canonical').mkdir(parents=True)
    (root/'canonical/current-generation.json').write_text('{}')
    with pytest.raises(ValueError,match='migration_required'):native.prepare(root,tmp_path/'unused')
    assert not (root/'postgresql').exists()

def test_schema3_binds_resources_and_only_official_source(tmp_path):
    from test_installer_update import _manifest
    path=_manifest(tmp_path/'installer.json',sqlite=(41,41,41))
    value=json.loads(path.read_text());value['schema_version']=3
    value['postgresql']={'schema_version':5,'server_major':17,'source_version':'0.1.3','resources_manifest_sha256':'d'*64}
    parts=[value['product_version'],value['build_commit'],value['files']['angmoo-desktop.exe'],value['files']['angmoo-sidecar.exe'],
        'sqlite:41-41->41','ladybug:0-2->2','postgresql:5:17:'+'d'*64]
    value['payload_generation']=hashlib.sha256('\n'.join(parts).encode()).hexdigest();path.write_text(json.dumps(value))
    assert InstallerPayloadContract.load(path).sqlite.minimum_readable_version==41
    value['postgresql']['resources_manifest_sha256']='e'*64;path.write_text(json.dumps(value))
    with pytest.raises(InstallerUpdateContractError):InstallerPayloadContract.load(path)

def payload(root,version,schema,generation):
    root.mkdir(parents=True,exist_ok=True)
    for name in ('angmoo-desktop.exe','angmoo-sidecar.exe'):(root/name).write_bytes(b'MZ'+generation.encode()+name.encode())
    pg=root/'postgresql';(pg/'bin').mkdir(parents=True)
    (pg/'bin/postgres.exe').write_bytes(b'synthetic-native-'+generation.encode())
    (pg/'angmoo-resources.json').write_text(json.dumps({'schema':'angmoo-postgresql-resources.v1',
        'postgresql':'17.11','pgvector':'0.8.7','files':{'bin/postgres.exe':hashlib.sha256((pg/'bin/postgres.exe').read_bytes()).hexdigest()}}))
    files={name:hashlib.sha256((root/name).read_bytes()).hexdigest() for name in ('angmoo-desktop.exe','angmoo-sidecar.exe')}
    value={'schema_version':schema,'product_version':version,'build_commit':generation*40,'files':files,
        'embedded_data':{'sqlite':{'minimum_readable_version':41,'maximum_readable_version':41,'target_version':41},
            'ladybug':{'minimum_readable_version':0,'maximum_readable_version':2,'target_version':2}}}
    parts=[version,generation*40,files['angmoo-desktop.exe'],files['angmoo-sidecar.exe'],'sqlite:41-41->41','ladybug:0-2->2']
    if schema==3:
        digest=hashlib.sha256((pg/'angmoo-resources.json').read_bytes()).hexdigest()
        value['postgresql']={'schema_version':5,'server_major':17,'source_version':'0.1.3','resources_manifest_sha256':digest}
        parts.append('postgresql:5:17:'+digest)
    value['payload_generation']=hashlib.sha256('\n'.join(parts).encode()).hexdigest()
    (root/'installer-payload.json').write_text(json.dumps(value));return value

@pytest.mark.skipif(os.name!='nt',reason='real PowerShell and Windows per-user payload paths')
def test_schema3_installed_verifier_rejects_changed_native_file(tmp_path):
    root=Path(__file__).resolve().parents[2];local=tmp_path/'local';app=local/'Angmoo/app'
    payload(app,'0.1.4',3,'a');env=dict(os.environ,LOCALAPPDATA=str(local))
    command=[shutil.which('pwsh') or 'powershell','-NoProfile','-NonInteractive','-File',
             str(root/'desktop/scripts/verify-installed-payload.ps1'),'-AppRoot',str(app)]
    first=subprocess.run(command,env=env,capture_output=True,text=True)
    assert first.returncode==0,first.stderr
    (app/'postgresql/bin/postgres.exe').write_bytes(b'tampered')
    second=subprocess.run(command,env=env,capture_output=True,text=True)
    assert second.returncode==35 and 'postgresql_resource_digest_mismatch' in second.stderr

@pytest.mark.skipif(os.name!='nt',reason='real Windows installer payload transaction')
def test_finalize_keeps_verified_013_payload_for_data_rollback(tmp_path):
    root=Path(__file__).resolve().parents[2];local=tmp_path/'local';product=local/'Angmoo';app=product/'app'
    old=payload(app,'0.1.3',2,'a');env=dict(os.environ,LOCALAPPDATA=str(local))
    tool=root/'desktop/scripts/installer-payload-transaction.ps1'
    def transaction(action):
        result=subprocess.run([shutil.which('pwsh') or 'powershell','-NoProfile','-NonInteractive','-File',
            str(tool),'-Action',action,'-ProductRoot',str(product),'-VerifierPath',str(root/'desktop/scripts/verify-installed-payload.ps1')],
            env=env,capture_output=True,text=True)
        assert result.returncode==0,result.stdout+result.stderr
    transaction('Prepare');payload(product/'app.__install_staging__','0.1.4',3,'b')
    transaction('Promote');transaction('Finalize')
    archive=product/'postgresql-migration/previous-payload'/old['payload_generation']
    assert (archive/'angmoo-sidecar.exe').read_bytes().startswith(b'MZa')
    assert json.loads((app/'installer-payload.json').read_text())['schema_version']==3
