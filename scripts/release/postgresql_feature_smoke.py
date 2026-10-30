"""Run current storage/search/recovery contracts in unchanged candidate images."""
import json,os,secrets,shutil,subprocess,tempfile,time,uuid
from pathlib import Path
from launcher.termux.payload import require
from scripts.release.candidate import ROOT
from scripts.release.feature_smoke import test_tools
from launcher.migrate.docker_migrate import write_private_once

TESTS=('postgresql/test_release_migration_integration.py','postgresql/test_vector_contracts.py',
    'postgresql/test_fulltext_contracts.py','postgresql/test_checkpoint_contracts.py',
    'postgresql/test_maintenance_schema_pg.py','postgresql/test_round_upgrade_pg.py')


def run(backend,postgres,platform,output):
    tooling=test_tools(output)
    name='angmoo-pg-feature-'+uuid.uuid4().hex[:12]
    pg=name+'-db';password=secrets.token_hex(32)
    dsn='postgresql+psycopg://angmoo_pg_run01_admin:'+password+'@127.0.0.1:15414/angmoo_pg_run01'
    def docker(*args,**kwargs):
        return subprocess.run(['docker',*args],check=True,capture_output=True,text=True,encoding='utf-8',**kwargs).stdout.strip()
    with tempfile.TemporaryDirectory(prefix=name) as directory:
        root=Path(directory);stage=root/'validation';stage.mkdir();stage.chmod(0o755)
        write_private_once(root/'password',password)
        write_private_once(root/'fixture.env','ANGMOO_EXPERIMENT_DATABASE_URL='+dsn+'\nANGMOO_TEST_ADMIN_DSN='+dsn+'\n')
        ignore=shutil.ignore_patterns('__pycache__','*.pyc','.pytest_cache')
        shutil.copytree(ROOT/'backend/tests',stage/'tests',ignore=ignore)
        shutil.copytree(tooling,stage/'test-tools',ignore=ignore)
        shutil.copyfile(ROOT/'scripts/ci/prepare_postgresql_tests.py',stage/'prepare.py')
        try:
            docker('run','-d','--name',pg,'--network','none','--platform',platform,
                '--env','POSTGRES_PASSWORD_FILE=/fixture-password','--env','POSTGRES_USER=angmoo_pg_run01_admin',
                '--env','POSTGRES_DB=angmoo_pg_run01','--mount',f'type=bind,source={root / "password"},target=/fixture-password,readonly',
                postgres,'postgres','-p','15414','-c','max_connections=28','-c','max_pred_locks_per_transaction=256')
            deadline=time.monotonic()+120
            while True:
                probe=subprocess.run(['docker','exec',pg,'pg_isready','-p','15414','-U','angmoo_pg_run01_admin','-d','angmoo_pg_run01'],capture_output=True)
                if probe.returncode==0:break
                require(time.monotonic()<deadline,'candidate_postgresql_fixture_not_ready');time.sleep(1)
            program="import runpy,pytest; runpy.run_path('/validation/prepare.py',run_name='__main__'); raise SystemExit(pytest.main(['-q','-p','no:cacheprovider',"+','.join(repr('/validation/tests/'+test) for test in TESTS)+"]))"
            docker('create','--name',name,'--network','container:'+pg,'--platform',platform,'--no-healthcheck',
                '--env-file',str(root/'fixture.env'),'--env','PYTHONPATH=/app:/validation/tests:/validation/test-tools',
                '--env','PYTEST_DISABLE_PLUGIN_AUTOLOAD=1','--env','ANGMOO_DENY_EXTERNAL_NETWORK=1',
                '--entrypoint','python',backend,'-c',program)
            docker('cp',str(stage),name+':/validation')
            result=subprocess.run(['docker','start','-a',name],capture_output=True,text=True,encoding='utf-8',timeout=900)
            status=docker('inspect','--format','{{.State.ExitCode}}',name)
            (output/'postgresql-features.txt').write_text(result.stdout+result.stderr,encoding='utf-8')
            require(result.returncode==0 and status=='0' and ' skipped' not in result.stdout,'candidate_postgresql_features_failed')
            (output/'postgresql-features.json').write_text(json.dumps({'status':'PASS','platform':platform,'tests':TESTS,
                'backend':backend,'postgres':postgres,'external_network':'disabled','provider_transmissions':0,
                'summary':result.stdout.strip().splitlines()[-1]},indent=2)+'\n')
        finally:
            for container in (name,pg):
                subprocess.run(['docker','rm','-f','-v',container],capture_output=True)
