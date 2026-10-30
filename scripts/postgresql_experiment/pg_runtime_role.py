"""Create private runtime credentials for already migrated trial databases."""
import json,os,secrets
from pathlib import Path
from urllib.parse import urlsplit,urlunsplit,quote
from app.runtime.persistence.postgresql_privileges import provision_runtime,RUNTIME_ROLE


if __name__=='__main__':
    os.umask(0o077)
    root=Path('/experiment');secret=root/'secrets/runtime-password'
    if not secret.exists():
        with secret.open('x') as f:f.write(secrets.token_urlsafe(32)+'\n')
    password=secret.read_text().strip();reports=[]
    for source,target in [('app-dsn','runtime-dsn'),('restore-dsn','restore-runtime-dsn')]:
        path=root/'secrets'/source
        if not path.exists():continue
        dsn=path.read_text().strip();reports.append(provision_runtime(dsn,password))
        parsed=urlsplit(dsn)
        value=urlunsplit((parsed.scheme,RUNTIME_ROLE+':'+quote(password,safe='')+'@127.0.0.1:15414',parsed.path,'',''))
        output=root/'secrets'/target
        output.write_text(value+'\n');output.chmod(0o600)
    print(json.dumps({'state':'RUNTIME_ROLE_READY','databases':reports}))
