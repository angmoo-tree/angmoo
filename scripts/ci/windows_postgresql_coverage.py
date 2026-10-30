"""Current Windows qualification union, distinct from frozen SQLite history."""
from __future__ import annotations
import argparse,json,re
from pathlib import Path

SCHEMA='angmoo-windows-postgresql-qualification.v1'
KINDS={'clean-install','upgrade-013','failure-recovery'}
CHECKS={'packaged_source','native_resources','health','schema5','new_write','restart',
        'token_required','foreign_origin_denied','clean_shutdown','source_preserved',
        'no_provider_transmissions','no_developer_runtime','silent_uninstall_preserved_data',
        'reinstall_reused_data','host_launch','host_first_initialization',
        'unicode_paths','backup_restore','independent_cluster_preserved'}

def verify_reports(reports,*,source_sha,run_id,run_attempt,profile='full'):
    if (not re.fullmatch('[0-9a-f]{40}',source_sha) or not str(run_id).isdecimal()
            or not re.fullmatch('[1-9][0-9]*',str(run_attempt))):raise ValueError('windows_pg_identity_invalid')
    expected=KINDS if profile=='full' else {'clean-install','upgrade-013'} if profile=='installer-smoke' else set()
    if not expected or len(reports)!=len(expected) or {r.get('kind') for r in reports}!=expected:
        raise ValueError('windows_pg_cases_missing')
    for report in reports:
        if (set(report)!={'schema','status','source_sha','run_id','run_attempt','kind','checks','source_version','target_schema','resources_sha256'}
                or report.get('schema')!=SCHEMA or report.get('status')!='PASS'
                or (report.get('source_sha'),str(report.get('run_id')),str(report.get('run_attempt')))!=(source_sha,str(run_id),str(run_attempt))):
            raise ValueError('windows_pg_report_invalid')
        checks=report['checks']
        needed=(CHECKS | ({'migration_consent'} if report['kind']!='clean-install' else set())
                | ({'interrupted_after_canonical','same_migration_resumed'} if report['kind']=='failure-recovery' else set()))
        if set(checks)!=needed or any(value is not True for value in checks.values()):raise ValueError('windows_pg_checks_incomplete')
        if report['source_version']!=('0.1.3' if report['kind']!='clean-install' else None) or report['target_schema']!=5:
            raise ValueError('windows_pg_version_invalid')
        if not re.fullmatch('[0-9a-f]{64}',report['resources_sha256']):raise ValueError('windows_pg_resources_invalid')
    if len({r['resources_sha256'] for r in reports})!=1:raise ValueError('windows_pg_resources_differ')
    return {'schema':SCHEMA,'profile':profile,'source_sha':source_sha,'run_id':str(run_id),'run_attempt':str(run_attempt),
            'source_versions':['0.1.3'],'target_schema':5,'cases':sorted(expected),'resources_sha256':reports[0]['resources_sha256']}

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--directory',type=Path,required=True)
    p.add_argument('--source-sha',required=True);p.add_argument('--run-id',required=True);p.add_argument('--run-attempt',required=True)
    p.add_argument('--profile',choices=['full','installer-smoke'],default='full');a=p.parse_args()
    paths=sorted(a.directory.glob('angmoo-postgresql-*.json'))
    if any(f.is_symlink() or f.stat().st_size>8192 for f in paths):raise ValueError('windows_pg_report_file_invalid')
    print(json.dumps(verify_reports([json.loads(f.read_text(encoding='utf-8-sig')) for f in paths],source_sha=a.source_sha,
        run_id=a.run_id,run_attempt=a.run_attempt,profile=a.profile)))

if __name__=='__main__':main()
