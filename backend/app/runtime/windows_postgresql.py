"""Per-user native PostgreSQL cluster, owned by Angmoo's sidecar lifetime."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
from uuid import uuid4
import psycopg
from psycopg import sql
from sqlalchemy import URL
from app.runtime.postgresql_installation import private_file,write_json,read_dsn,initialize,migrate,snapshot


def source_inventory(root):
    from app.runtime.postgresql_migration import files
    # The new sidecar holds its serving byte lock while copying old data.
    # Windows refuses reads of that locked byte, even from another handle in
    # the same process. Exclude only new process-ownership files before IO;
    # checkpoints, journals and every other old runtime file remain included.
    transient={'sidecar.owner.json','sidecar.endpoint.json','canonical-serving.lock'}
    return {name:files(root/name,exclude=transient if name=='runtime' else ())
        for name in ('canonical','secrets','media','runtime','search','graph') if (root/name).exists()}


class NativePostgres:
    def __init__(self,root,resources):
        if os.name=='nt' and sys.getwindowsversion().build<18362:
            raise ValueError('postgresql_native_windows_1903_required')
        self.root=Path(root).absolute()
        self.resources=Path(resources).absolute()
        if any(p.is_symlink() or p.is_junction() for p in (self.root,self.resources,*self.root.parents,*self.resources.parents)):
            raise ValueError('postgresql_native_path_link_refused')
        manifest=json.loads((self.resources/'angmoo-resources.json').read_text(encoding='utf-8'))
        if (manifest.get('postgresql'),manifest.get('pgvector'),manifest.get('platform'))!=('17.11','0.8.7','windows-x64'):
            raise ValueError('postgresql_native_resources_unsupported')
        for name,digest in manifest['files'].items():
            path=self.resources/name
            if not path.resolve().is_relative_to(self.resources.resolve()) or hashlib.file_digest(path.open('rb'),'sha256').hexdigest()!=digest:
                raise ValueError('postgresql_native_resource_hash_mismatch')
        self.root.mkdir(parents=True,exist_ok=True)
        self.marker=self.root/'installation.json'
        if self.marker.exists():
            self.state=json.loads(self.marker.read_text(encoding='utf-8'))
            if self.state.get('schema')!='angmoo-native-postgresql.v1':raise ValueError('postgresql_native_identity_invalid')
        else:
            if any(self.root.iterdir()):raise ValueError('postgresql_native_root_not_empty')
            with socket.socket() as probe:
                probe.bind(('127.0.0.1',0));port=probe.getsockname()[1]
            self.state={'schema':'angmoo-native-postgresql.v1','installation_id':'angmoo-'+uuid4().hex,'port':port,'database':'angmoo'}
            write_json(self.marker,self.state)
        from app.core.secret_file_access import protect_existing_secret
        protect_existing_secret(self.marker,protect_parent=True)
        self.cluster=self.root/'cluster'
        if self.cluster.is_symlink() or self.cluster.is_junction():raise ValueError('postgresql_native_path_link_refused')
        self.owner_file=self.root/'secrets/owner-dsn'
        self.runtime_file=self.root/'secrets/runtime-dsn'
        password_file=self.root/'secrets/owner-password'
        if (self.cluster/'PG_VERSION').exists() and not all(p.is_file() for p in (password_file,self.owner_file,self.runtime_file)):
            raise ValueError('postgresql_native_credentials_missing')
        if not password_file.exists():private_file(password_file,(secrets.token_urlsafe(48)+'\n').encode())
        password=password_file.read_text().strip()
        for path,user,pw in ((self.owner_file,'angmoo_owner',password),(self.runtime_file,'angmoo_runtime',secrets.token_urlsafe(48))):
            if not path.exists():
                dsn=URL.create('postgresql+psycopg',username=user,password=pw,host='127.0.0.1',port=self.state['port'],database=self.state['database']).render_as_string(hide_password=False)
                private_file(path,(dsn+'\n').encode())

    def run(self,executable,*args,env=None,timeout=120):
        command=[str(self.resources/'bin'/executable),*map(str,args)]
        # pg_ctl starts a server descendant on Windows. A pipe inherited by
        # that descendant can keep communicate() waiting after pg_ctl exits.
        # A private regular file gives the control command a bounded lifetime.
        with (self.root/'control-operation.log').open('w+b') as stream:
            result=subprocess.run(command,env=env,stdout=stream,stderr=subprocess.STDOUT,timeout=timeout,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            stream.seek(0);output=stream.read()
        if result.returncode:
            # A subsequent controlled shutdown must not overwrite the failure
            # evidence. It stays private because restore errors can name data.
            failure=self.root/(executable.replace('.exe','')+'-failed-'+uuid4().hex+'.log')
            private_file(failure,output)
            raise RuntimeError('postgresql_native_'+executable.replace('.exe','')+'_failed')
        return output

    def owner(self,database=None):
        value=read_dsn(self.owner_file)
        from sqlalchemy.engine import make_url
        return make_url(value).set(drivername='postgresql',database=database or self.state['database']).render_as_string(hide_password=False)

    def verify_running(self):
        with psycopg.connect(self.owner('postgres'),connect_timeout=5) as db:
            directory,pid=db.execute("SELECT current_setting('data_directory'),pg_backend_pid()").fetchone()
            if os.path.normcase(str(Path(directory).resolve()))!=os.path.normcase(str(self.cluster.resolve())):
                raise ValueError('postgresql_native_cluster_mismatch')
            system_id=db.execute('SELECT system_identifier::text FROM pg_control_system()').fetchone()[0]
            if self.state.get('system_id') not in (None,system_id):raise ValueError('postgresql_native_system_identity_mismatch')
            self.state['system_id']=system_id;write_json(self.marker,self.state)
            return pid

    def start(self):
        if not (self.cluster/'PG_VERSION').exists():
            if self.cluster.exists() and any(self.cluster.iterdir()):raise ValueError('postgresql_native_partial_cluster')
            self.run('initdb.exe','-D',self.cluster,'-U','angmoo_owner','--encoding=UTF8','--locale=C','--auth-host=scram-sha-256','--auth-local=scram-sha-256',
                '--pwfile',self.root/'secrets/owner-password')
            with (self.cluster/'postgresql.conf').open('a',encoding='utf-8') as out:
                out.write("\nlisten_addresses='127.0.0.1'\nport="+str(self.state['port'])+"\nmax_connections=28\nshared_buffers='64MB'\nwork_mem='4MB'\nmax_pred_locks_per_transaction=256\nmax_pred_locks_per_relation=32\n")
        if (self.cluster/'PG_VERSION').read_text().strip()!='17':raise ValueError('postgresql_native_major_upgrade_required')
        if (self.cluster/'postmaster.pid').exists():
            # Never kill or overwrite a PID file for an unverified owner.
            self.verify_running()
        else:
            self.run('pg_ctl.exe','-D',self.cluster,'-l',self.root/'server.log','-w','-t','60','start',timeout=90)
            self.verify_running()
        with psycopg.connect(self.owner('postgres'),autocommit=True) as db:
            if not db.execute('SELECT 1 FROM pg_database WHERE datname=%s',(self.state['database'],)).fetchone():
                db.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(self.state['database'])))

    def stop(self):
        if not (self.cluster/'postmaster.pid').exists():return
        self.verify_running()
        with psycopg.connect(self.owner()) as db:
            if db.execute("SELECT count(*) FROM pg_stat_activity WHERE datname=current_database() AND pid<>pg_backend_pid()").fetchone()[0]:
                raise ValueError('postgresql_native_application_must_be_stopped')
        self.run('pg_ctl.exe','-D',self.cluster,'-m','fast','-w','-t','60','stop',timeout=90)

    def backup(self,target):
        self.verify_running()
        target=Path(target)
        if target.exists():raise ValueError('postgresql_backup_target_exists')
        from sqlalchemy.engine import make_url
        value=make_url(read_dsn(self.owner_file))
        env=dict(os.environ,PGHOST=value.host,PGPORT=str(value.port),PGUSER=value.username,PGPASSWORD=value.password,PGDATABASE=value.database)
        self.run('pg_dump.exe','--format=custom','--file',target,env=env,timeout=600)
        receipt={'schema':'angmoo-native-backup.v1','installation_id':self.state['installation_id'],
            'bytes':target.stat().st_size,'sha256':hashlib.file_digest(target.open('rb'),'sha256').hexdigest()}
        write_json(target.with_suffix(target.suffix+'.json'),receipt)
        return receipt

    def restore(self,target):
        """Restore only this owned installation, with application clients stopped."""
        self.verify_running()
        target=Path(target)
        receipt=json.loads(target.with_suffix(target.suffix+'.json').read_text(encoding='utf-8'))
        if (receipt.get('schema'),receipt.get('installation_id'),receipt.get('bytes'),receipt.get('sha256')) != (
            'angmoo-native-backup.v1',self.state['installation_id'],target.stat().st_size,hashlib.file_digest(target.open('rb'),'sha256').hexdigest()):
            raise ValueError('postgresql_native_backup_identity_mismatch')
        with psycopg.connect(self.owner(),autocommit=True) as db:
            if db.execute("SELECT count(*) FROM pg_stat_activity WHERE datname=current_database() AND pid<>pg_backend_pid()").fetchone()[0]:
                raise ValueError('postgresql_restore_requires_application_stopped')
        from sqlalchemy.engine import make_url
        value=make_url(read_dsn(self.owner_file))
        env=dict(os.environ,PGHOST=value.host,PGPORT=str(value.port),PGUSER=value.username,PGPASSWORD=value.password,PGDATABASE=value.database)
        # Restore into an empty database of this verified owned cluster. DDL
        # replacement of every table inside one transaction needlessly holds
        # both the old and new relation locks until commit.
        before=target.with_name(target.stem+'-before-restore-'+uuid4().hex+target.suffix)
        self.backup(before)
        with psycopg.connect(self.owner('postgres'),autocommit=True) as db:
            db.execute(sql.SQL('DROP DATABASE {}').format(sql.Identifier(value.database)))
            db.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(value.database)))
        self.run('pg_restore.exe','--exit-on-error','--single-transaction','--dbname',value.database,target,env=env,timeout=600)
        return {'state':'restored','installation_id':self.state['installation_id']}


def prepare(data_root,resources,*,allow_migration=False):
    root=Path(data_root)
    old=(root/'canonical/current-generation.json').exists()
    target=root/'postgresql-appdata'
    if old and not (target/'runtime/postgresql-runtime.json').exists() and not allow_migration:
        raise ValueError('desktop_postgresql_migration_required')
    if old and not (target/'runtime/postgresql-runtime.json').exists():
        import shutil
        source_bytes=sum(p.stat().st_size for name in ('canonical','secrets','media','runtime','search','graph')
            for p in (root/name).rglob('*') if p.is_file())
        if shutil.disk_usage(root).free<source_bytes*3+512*1024**2:raise ValueError('migration_disk_space_low')
    manager=NativePostgres(root/'postgresql',resources)
    manager.start()
    try:
        owner,runtime=read_dsn(manager.owner_file),read_dsn(manager.runtime_file)
        if old and not (target/'runtime/postgresql-runtime.json').exists():
            # Snapshot only the old data directories, never the live PG cluster,
            # installed executables or this migration's own workspace.
            staging=root/'postgresql-migration/source'
            import shutil
            from app.runtime.postgresql_migration import files
            inventory=source_inventory(root)
            source_marker=root/'postgresql-migration/source-inventory.json'
            if source_marker.exists():
                if json.loads(source_marker.read_text(encoding='utf-8'))!=inventory:raise ValueError('migration_native_source_changed')
            else:write_json(source_marker,inventory)
            for name,rows in inventory.items():
                for row in rows:
                    destination=staging/name/row['path']
                    if not destination.exists():
                        destination.parent.mkdir(parents=True,exist_ok=True)
                        shutil.copy2(root/name/row['path'],destination)
                (staging/name).mkdir(parents=True,exist_ok=True)
            if {name:files(staging/name) for name in inventory}!=inventory:
                raise ValueError('migration_native_partial_source_changed')
            work=root/'postgresql-migration/work'
            snapshot(staging,work,manager.state['installation_id'])
            migrate(work,owner,runtime,target)
        elif not (target/'runtime/postgresql-runtime.json').exists():
            initialize(target,owner,runtime,manager.state['installation_id'])
        return manager,target
    except BaseException:
        try:manager.stop()
        except Exception as cleanup:
            write_json(manager.root/'cleanup-failure.json',{'code':type(cleanup).__name__})
        raise
