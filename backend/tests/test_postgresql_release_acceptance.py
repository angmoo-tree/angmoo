from copy import deepcopy
import pytest
from scripts.release.postgresql_acceptance import validate,PLATFORMS

def acceptance():
    return {'source_sha':'a'*40,'source_version':'0.1.3','target_schema':5,
        'platforms':{p:{'result':'PASS','fresh_install':True,'migration':True,'backup_restore':True,
            'recovery':True,'current_features':True,'evidence':'Reviewed source-bound platform evidence record'} for p in PLATFORMS},
        'termux_idle':{'result':'PASS','seconds':600,'cpu_one_core_percent':9.5,'evidence':'Reviewed 600-second idle record for the fixed candidate'},
        'provider_budget':{'transmissions':4,'maximum_rolling_60s':4,'minimum_interval_seconds':5},
        'real_ai':{'result':'PASS','evidence':'Reviewed real provider representative Chat SNS and memory cases'}}

def test_current_adoption_requires_fixed_source_platforms_and_reviewed_evidence():
    assert validate(acceptance(),'a'*40)['target_schema']==5

@pytest.mark.parametrize('fault',['none','source','missing_platform','no_restore','idle_not_run','idle_cpu','idle_seconds','provider_limit','provider_rate','provider_interval','no_real_ai'])
def test_adoption_failures_cannot_become_publication_ready(fault):
    value=deepcopy(acceptance())
    if fault=='none':value=None
    elif fault=='source':value['source_sha']='b'*40
    elif fault=='missing_platform':value['platforms'].pop('termux-arm64')
    elif fault=='no_restore':value['platforms']['docker-amd64']['backup_restore']=False
    elif fault=='idle_not_run':value['termux_idle']['result']='NOT_RUN'
    elif fault=='idle_cpu':value['termux_idle']['cpu_one_core_percent']=10.01
    elif fault=='idle_seconds':value['termux_idle']['seconds']=599
    elif fault=='provider_limit':value['provider_budget']['transmissions']=51
    elif fault=='provider_rate':value['provider_budget']['maximum_rolling_60s']=15
    elif fault=='provider_interval':value['provider_budget']['minimum_interval_seconds']=4
    elif fault=='no_real_ai':value['real_ai']['result']='NOT_RUN'
    with pytest.raises(ValueError,match='p5_postgresql_'):validate(value,'a'*40)
