"""Release-review acceptance for the PostgreSQL platform transition.

These reviewed evidence references supplement CI; they are never synthesized
from a green build. Frozen SQLite releases retain their original P5 contract.
"""
from launcher.termux.payload import require

PLATFORMS={'docker-amd64','docker-arm64','termux-arm64','windows-x64'}

def validate(value,source):
    require(isinstance(value,dict) and value.get('source_sha')==source
        and value.get('source_version')=='0.1.3' and value.get('target_schema')==5,'p5_postgresql_identity_missing')
    cases=value.get('platforms',{})
    require(isinstance(cases,dict) and set(cases)==PLATFORMS,'p5_postgresql_platforms_missing')
    for platform,row in cases.items():
        require(isinstance(row,dict) and row.get('result')=='PASS'
            and all(row.get(key) is True for key in ('fresh_install','migration','backup_restore','recovery','current_features'))
            and isinstance(row.get('evidence'),str) and len(row['evidence'])>=20,'p5_postgresql_platform_incomplete:'+platform)
    idle=value.get('termux_idle',{})
    cpu=idle.get('cpu_one_core_percent')
    require(idle.get('result')=='PASS' and idle.get('seconds')==600 and type(cpu) in (float,int)
        and 0<=cpu<=10 and isinstance(idle.get('evidence'),str) and len(idle['evidence'])>=20,'p5_postgresql_termux_idle_missing')
    provider=value.get('provider_budget',{})
    count,rolling,interval=(provider.get(k) for k in ('transmissions','maximum_rolling_60s','minimum_interval_seconds'))
    require(type(count) is int and 0<=count<=50 and type(rolling) is int and 0<=rolling<=14
        and (count<2 or type(interval) in (int,float) and interval>=5),'p5_postgresql_provider_budget_invalid')
    require(value.get('real_ai',{}).get('result')=='PASS' and count>0
        and isinstance(value['real_ai'].get('evidence'),str) and len(value['real_ai']['evidence'])>=20,'p5_postgresql_real_ai_missing')
    return value
