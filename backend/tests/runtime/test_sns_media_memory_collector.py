"""Synthetic nonempty SQL and real PowerShell smoke/policy; no server or AI."""
from datetime import datetime, UTC
import importlib.util
import json
from pathlib import Path
import sqlite3
import subprocess
import os
import shutil
import sys
import pytest

ROOT=Path(__file__).resolve().parents[3]
spec=importlib.util.spec_from_file_location('sns_probe',ROOT/'scripts/diagnostics/sns_media_memory_probe.py')
probe=importlib.util.module_from_spec(spec);spec.loader.exec_module(probe)
PWSH=Path(os.environ.get('ANGMOO_TEST_PWSH') or shutil.which('pwsh') or '__pwsh_unavailable__')


def fixture(tmp_path,nonempty):
    root=tmp_path/'data';path=root/'canonical/generations/test/angmoo.sqlite3';path.parent.mkdir(parents=True)
    (root/'canonical/current-generation.json').write_text(json.dumps({'schema_version':1,'relative_path':'generations/test'}))
    manifest={'schema_version':3,'session_id':'sns-'+'a'*32,'world_id':'w','actor_ids':['a'],'carry_in_ids':[],
        'started_at':'2026-10-10T09:28:13.863635+09:00','ends_at':'2026-10-10T13:28:13.863635+09:00','tail_ends_at':'2026-10-10T13:58:13.863635+09:00'}
    directory=root/'diagnostics/sns'/manifest['session_id'];directory.mkdir(parents=True)
    (directory/'manifest.json').write_text(json.dumps(manifest))
    with sqlite3.connect(path) as db:
        db.executescript('CREATE TABLE posts(id TEXT,world_id TEXT,reply_to_post_id TEXT,title TEXT,body TEXT);'
            'CREATE TABLE activity_graph_runs(activity_id TEXT,started_at TEXT,status TEXT,world_id TEXT,world_character_id TEXT);'
            'CREATE TABLE agent_public_action_executions(id TEXT,run_id TEXT,result TEXT,status TEXT);'
            'CREATE TABLE post_image_generation_jobs(id TEXT,post_id TEXT,status TEXT);')
        if nonempty:
            db.execute('INSERT INTO activity_graph_runs VALUES(?,?,?,?,?)',('activity-1','2026-10-10 01:00:00.000000','completed','w','a'))
            db.execute('INSERT INTO agent_public_action_executions VALUES(?,?,?,?)',('execution-1','activity-1',json.dumps({'post_id':'reply'}),'succeeded'))
            db.executemany('INSERT INTO posts VALUES(?,?,?,?,?)',[('root','w',None,'private-title','private-body'),('reply','w','root','private-reply-title','private-reply-body')])
            db.execute('INSERT INTO post_image_generation_jobs VALUES(?,?,?)',('image-1','reply','completed'))
    return root,path,manifest


@pytest.mark.parametrize('nonempty',[False,True])
def test_parameterized_probe_has_real_reply_parent_media_and_no_bodies(tmp_path,nonempty):
    root,path,manifest=fixture(tmp_path,nonempty)
    result=probe.collect(path,manifest)
    assert len(result['posts'])==int(nonempty)
    assert 'private-body' not in json.dumps(result)
    if nonempty:
        assert result['posts'][0]['parent_exists']
        assert result['posts'][0]['image_jobs'][0]['status']=='completed'
    assert (probe.instant(result['tail_ends_utc'])-probe.instant(result['started_utc'])).total_seconds()==270*60
    if PWSH.is_file():
        run=subprocess.run([str(PWSH),'-NoProfile','-File',str(ROOT/'scripts/diagnostics/Invoke-SnsMediaMemoryObservation.ps1'),
            '-DataRoot',str(root),'-SessionId',manifest['session_id'],'-OutputRoot',str(tmp_path/'smoke'),
            '-PythonExe',sys.executable,'-ReadOnlySmoke'],capture_output=True,text=True,timeout=60)
        assert run.returncode==0,run.stderr
        assert json.loads((tmp_path/'smoke/collector-health.json').read_text(encoding='utf-8-sig'))['state']=='SMOKE_COMPLETE'


def test_wrong_parent_column_fails_even_with_empty_posts(tmp_path):
    _,path,manifest=fixture(tmp_path,False)
    with sqlite3.connect(path) as db: db.execute('ALTER TABLE posts RENAME COLUMN reply_to_post_id TO parent_post_id')
    with pytest.raises(ValueError,match='schema_incompatible'): probe.collect(path,manifest)


@pytest.mark.parametrize('stamp',['2026-10-10T09:28:13.863635+09:00','2026-10-10T00:28:13.863635Z','2026-10-09T19:28:13.863635-05:00'])
def test_offset_strings_represent_one_instant(stamp):
    assert probe.instant(stamp)==datetime(2026,10,10,0,28,13,863635,tzinfo=UTC)


def test_ambiguous_datetime_is_rejected():
    for value in ('2026-10-10T09:28:13',datetime.now(UTC)):
        with pytest.raises(ValueError):probe.instant(value)


@pytest.mark.skipif(not PWSH.is_file(),reason='PowerShell host-only policy check')
def test_real_powershell_policy_preserves_strings_degrades_after_three_and_finalizes(tmp_path):
    module=str(ROOT/'scripts/diagnostics/SnsCollectorPolicy.psm1').replace("'","''")
    source=f'''Import-Module '{module}' -Force
$v=Read-CollectorJson '{{"time":"2026-10-10T09:28:13.863635+09:00"}}'
if ($v.time -isnot [string]) {{ throw 'date-converted' }}
if ((Get-CollectorUtcInstant $v.time).ToString('o') -ne '2026-10-10T00:28:13.8636350+00:00') {{ throw 'wrong-offset' }}
$rejected=0
foreach ($v in @('2026-10-10T09:28:13',[DateTime]::Now)) {{ try {{ Get-CollectorUtcInstant $v | Out-Null }} catch {{ $rejected++ }} }}
if ($rejected -ne 2) {{ throw 'ambiguous-date-accepted' }}
$h=@{{failed_snapshots=0;successful_snapshots=0;degraded=$false;copy_success=$true;export_success=$true;flush_complete=$true}}
$fail=0; for ($i=0;$i -lt 3;$i++) {{ $fail=Update-CollectorProbeHealth $h $false $fail }}
if (-not $h.degraded -or $h.failed_snapshots -ne 3) {{ throw 'retry-unbounded' }}
if ((Get-CollectorFinalState $h) -ne 'PARTIAL') {{ throw 'false-complete' }}
$h.failed_snapshots=0
if ((Get-CollectorFinalState $h) -ne 'EXPORTED_PENDING_REVIEW') {{ throw 'wrong-final' }}
$h.export_success=$false
if ((Get-CollectorFinalState $h) -ne 'ERROR') {{ throw 'export-loss-hidden' }}
'''
    path=tmp_path/'policy.ps1';path.write_text(source,encoding='utf-8')
    run=subprocess.run([str(PWSH),'-NoProfile','-File',str(path)],capture_output=True,text=True,timeout=30)
    assert run.returncode==0,run.stderr


@pytest.mark.skipif(not PWSH.is_file(),reason='PowerShell host-only collector lifecycle')
@pytest.mark.parametrize('export_success',[True,False])
def test_actual_collector_exports_after_final_probe_error_and_terminates(tmp_path,export_success):
    root,_,manifest=fixture(tmp_path,False)
    manifest.update(ends_at='2020-01-01T00:00:00Z',tail_ends_at='2020-01-01T00:30:00Z',source_revision='synthetic')
    (root/'diagnostics/sns'/manifest['session_id']/'manifest.json').write_text(json.dumps(manifest))
    # Exercise the real external runner with synthetic CLI output. It never
    # starts an app, uses a credential, runs generation or waits for a real due.
    adapter=tmp_path/'synthetic-python.ps1'
    adapter.write_text('''param([Parameter(ValueFromRemainingArguments)][string[]]$Calls)
if ($Calls[0] -like '*sns_media_memory_probe.py') { exit 1 }
if ($Calls -contains 'status') {
    '{"recorder_health":[{"flush_complete":true}]}'
    exit 0
}
if ($Calls -contains 'export') {
    $destination=$Calls[[Array]::IndexOf($Calls,'--output')+1]
    New-Item -ItemType Directory -Path $destination -Force | Out-Null
    'attempted' | Set-Content -LiteralPath (Join-Path $destination 'attempt.txt')
''' + ('''    '{"support":"supported","situation_evidence_complete":true}' | Set-Content -LiteralPath (Join-Path $destination 'situation-evidence-coverage.json')
    '{}'
    exit 0
''' if export_success else '''    exit 1
''') + '''}
exit 2
''',encoding='utf-8')
    run=subprocess.run([str(PWSH),'-NoProfile','-File',str(ROOT/'scripts/diagnostics/Invoke-SnsMediaMemoryObservation.ps1'),
        '-DataRoot',str(root),'-SessionId',manifest['session_id'],'-OutputRoot',str(tmp_path/'result'),
        '-PythonExe',str(adapter),'-MaxFlushSeconds','0'],capture_output=True,text=True,timeout=30)
    health=json.loads((tmp_path/'result/collector-health.json').read_text(encoding='utf-8-sig'))
    assert run.returncode==(0 if export_success else 2),run.stderr
    assert health['state']==('PARTIAL' if export_success else 'ERROR')
    assert health['final_probe_error']=='collector_probe_failed'
    assert health['export_success'] is export_success
    assert health['last_status_success'] and health['last_flush_success']
    assert bool(health['last_export_success']) is export_success
    assert bool(health['last_copy_success']) is export_success
    assert (tmp_path/'result/export/attempt.txt').is_file()
