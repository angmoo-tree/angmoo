import argparse
import importlib.util
import os
from pathlib import Path
import pytest

path=Path(__file__).resolve().parents[3]/'launcher/migrate/docker_migrate.py'
spec=importlib.util.spec_from_file_location('docker_migrate',path)
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)


def test_private_credentials_are_complete_private_and_never_replaced(tmp_path):
    root=tmp_path/'owned';module.private_directory(root)
    path=root/'database-connection'
    mask=os.umask(0)
    try:module.write_private_once(path,'synthetic first value')
    finally:os.umask(mask)
    assert path.read_text()=='synthetic first value'
    if os.name!='nt':assert path.stat().st_mode&0o777==0o600
    with pytest.raises(FileExistsError):module.write_private_once(path,'different value')
    assert path.read_text()=='synthetic first value'
    assert list(root.iterdir())==[path]


def test_private_credential_failure_does_not_publish_partial_file(tmp_path,monkeypatch):
    path=tmp_path/'not-published'
    def failed(_):raise OSError('synthetic sync failure')
    monkeypatch.setattr(module.os,'fsync',failed)
    with pytest.raises(OSError,match='synthetic sync failure'):
        module.write_private_once(path,'synthetic value')
    assert not path.exists() and not list(tmp_path.iterdir())


class Docker:
    def run(self,*args,**kwargs):
        if args[0]=='info':return 'engine-one'
        if args[0]=='context':return 'local'
        if args[0]=='ps':return 'backend'
        if args[0]=='volume':return 'custom_data'
        raise AssertionError(args)
    def json(self,*args):
        if args[0]=='inspect':return [{'Id':'backend','Config':{'Labels':{'com.docker.compose.project':'custom','com.docker.compose.service':'backend'}},
            'State':{'Running':False},'Mounts':[{'Destination':'/var/lib/angmoo','Type':'volume','Name':'custom_data'}]}]
        return [{'Name':'custom_data','Labels':{'com.docker.compose.project':'custom','com.docker.compose.volume':'angmoo_contributor_embedded_data'}}]


def args(**values):
    return argparse.Namespace(language='en',source_volume=values.get('volume'),source_directory=None,source_project=None)


def test_custom_project_volume_deduplicates_and_never_mutates():
    result=module.discover(Docker())
    assert len(result)==1 and result[0]['project']=='custom' and result[0]['source']=='custom_data'
    assert result[0]['containers']==['backend']


def test_single_candidate_still_leaves_confirmation_to_migration():
    candidate=module.discover(Docker())[0]
    assert module.choose([candidate],args(),ask=lambda _:pytest.fail('single candidate must not request manual source'))==candidate


def test_multiple_candidates_require_user_selection():
    first={'project':'one','kind':'volume','source':'one','version':'0.1.3'}
    second=dict(first,project='two',source='two')
    assert module.choose([first,second],args(),ask=lambda _:'2')==second
    with pytest.raises(ValueError,match='selection_invalid'):module.choose([first,second],args(),ask=lambda _:'0')


def test_manual_input_only_after_zero_candidates():
    candidate=module.discover(Docker())[0]
    with pytest.raises(ValueError,match='manual_source_only'):module.choose([candidate],args(volume='other'))
    assert module.choose([],args(volume='retained_data'))['source']=='retained_data'


def test_discovery_failure_is_not_an_empty_result():
    class Unavailable(Docker):
        def run(self,*args,**kwargs):raise RuntimeError('docker_info_failed')
    with pytest.raises(RuntimeError,match='docker_info_failed'):module.discover(Unavailable())
