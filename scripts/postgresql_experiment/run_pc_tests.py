"""Provide the private DSN to pytest without writing it into commands/logs."""
import os,pathlib,subprocess,sys
from sqlalchemy import URL
ROOT=pathlib.Path(__file__).resolve().parents[2]
password=pathlib.Path('E:/angmoo-local/postgresql-termux-20261027/run-01/secrets/pc-postgres-password').read_text().strip()
env=dict(os.environ)
env['ANGMOO_EXPERIMENT_DATABASE_URL']=URL.create('postgresql+psycopg',username='angmoo_pg_run01_admin',password=password,host='127.0.0.1',port=15414,database='angmoo_pg_run01').render_as_string(hide_password=False)
env['ANGMOO_DENY_EXTERNAL_NETWORK']='1'
raise SystemExit(subprocess.run([sys.executable,'-m','pytest',*sys.argv[1:]],cwd=ROOT/'backend',env=env).returncode)
