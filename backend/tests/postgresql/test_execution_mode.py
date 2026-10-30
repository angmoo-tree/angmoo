"""Explicit mode switching must retain SQLite denial and readiness identity."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import pytest


@pytest.mark.parametrize('mode', ['default', 'validation', 'real-use'])
def test_serving_audit_guard_in_a_fresh_process(mode):
    # Exercise installed audit hooks without sending a request to a provider.
    program = """
import sqlite3,sys
from app.runtime.postgresql_backend import install_validation_guards
mode=sys.argv[1]
install_validation_guards(**({} if mode=='default' else {'validation_mode':mode=='validation'}))
try:sqlite3.connect(':memory:')
except RuntimeError as e:assert str(e)=='postgresql_serving_sqlite_forbidden'
else:raise AssertionError('SQLite guard missing')
sys.audit('socket.connect',None,('127.0.0.1',15414))
for event,args in [('socket.connect',(None,('203.0.113.1',443))),
                   ('socket.getaddrinfo',('provider.example',443,0,0,0))]:
    try:sys.audit(event,*args)
    except RuntimeError as e:
        assert mode!='real-use' and str(e)=='experiment_external_provider_disabled'
    else:assert mode=='real-use'
"""
    result=subprocess.run([sys.executable,'-c',program,mode],cwd=Path(__file__).resolve().parents[2],
        capture_output=True,text=True,timeout=15)
    assert result.returncode==0,result.stderr


@pytest.fixture
def launcher(tmp_path,monkeypatch):
    scripts=Path(__file__).resolve().parents[3]/'scripts/postgresql_experiment'
    monkeypatch.syspath_prepend(str(scripts))
    spec=importlib.util.spec_from_file_location('mode_test_phone_app',scripts/'phone_app.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    (tmp_path/'.angmoo-pg-experiment.json').write_text(json.dumps({'run_id':module.RUN_ID,'source_sha':module.SOURCE_SHA}))
    (tmp_path/'records').mkdir()
    (tmp_path/'records/selection.json').write_text(json.dumps({'run_id':module.RUN_ID,'state':'VERIFIED',
        'data_root':'appdata-restore','dsn_file':'secrets/restore-runtime-dsn'}))
    monkeypatch.setattr(module.phone_pg,'ROOT',tmp_path)
    return module


def test_mode_switch_requires_stopped_app_and_matching_selection(launcher,monkeypatch):
    assert launcher.execution_mode()=='validation'
    monkeypatch.setattr(launcher,'status',lambda s:{'alive':s=='backend'})
    with pytest.raises(ValueError,match='requires_stopped_app'):launcher.set_execution_mode('real-use')
    assert launcher.execution_mode()=='validation'
    monkeypatch.setattr(launcher,'status',lambda s:{'alive':False})
    launcher.set_execution_mode('real-use')
    assert launcher.execution_mode()=='real-use'
    path=launcher.phone_pg.root()/'records/selection.json'
    value=json.loads(path.read_text());value['data_root']='other-data';path.write_text(json.dumps(value))
    with pytest.raises(ValueError,match='execution_mode_invalid'):launcher.execution_mode()


def test_resolver_copy_is_private_and_does_not_change_source(launcher,tmp_path,monkeypatch):
    source=tmp_path/'termux-resolv.conf';source.write_text('nameserver 8.8.8.8\n')
    monkeypatch.setattr(launcher,'TERMUX_RESOLVER',source)
    target=launcher.resolver_file()
    assert target==tmp_path/'records/resolv.conf'
    assert target.read_bytes()==source.read_bytes()
    source.write_text('nameserver 8.8.4.4\n')
    assert launcher.resolver_file().read_text()=='nameserver 8.8.8.8\n'
    assert source.read_text()=='nameserver 8.8.4.4\n'


def test_empty_resolver_is_rejected(launcher,tmp_path,monkeypatch):
    source=tmp_path/'termux-resolv.conf';source.write_text('')
    monkeypatch.setattr(launcher,'TERMUX_RESOLVER',source)
    with pytest.raises(ValueError,match='resolver_invalid'):launcher.resolver_file()
    assert not (tmp_path/'records/resolv.conf').exists()


@pytest.mark.parametrize('mode',['validation','real-use'])
def test_readiness_rejects_wrong_mode_or_identity(launcher,monkeypatch,mode):
    monkeypatch.setattr(launcher,'status',lambda s:{'alive':False})
    launcher.set_execution_mode(mode)
    monkeypatch.setattr(launcher,'manifest',lambda:{'services':{'backend':{'source_sha':'expected'}}})
    value={'source_sha':'expected','launch_id':'launch','persistence':'postgresql',
        'validation_mode':mode=='validation','automatic_activity':'suspended' if mode=='validation' else 'enabled'}
    class Response:
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def read(self,*args):return json.dumps(value).encode()
    monkeypatch.setattr(launcher.urllib.request,'urlopen',lambda *a,**k:Response())
    assert launcher.ready('backend','launch')
    value['validation_mode']=not value['validation_mode']
    assert not launcher.ready('backend','launch')
    value['validation_mode']=mode=='validation';value['source_sha']='wrong'
    assert not launcher.ready('backend','launch')
