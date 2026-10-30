"""Termux experiment entrypoint with an explicit opt-in real-use mode."""
import argparse,json,os,sys
from pathlib import Path


def install_validation_guards(*, validation_mode=True):
    def audit(event,args):
        if event=='sqlite3.connect':
            raise RuntimeError('postgresql_serving_sqlite_forbidden')
        if validation_mode and event=='socket.connect':
            address=args[1]
            if isinstance(address,tuple) and (address[0] not in {'127.0.0.1','::1'} or address[1]!=15414):
                raise RuntimeError('experiment_external_provider_disabled')
        if validation_mode and event=='socket.getaddrinfo' and args[0] not in {'127.0.0.1','::1','localhost',None}:
            raise RuntimeError('experiment_external_provider_disabled')
    sys.addaudithook(audit)


def create_app(root,dsn,origin,*,validation_mode=True):
    from app.runtime.postgresql_experiment import build_config
    from app.main import create_public_app
    from app.runtime.configuration import initialize_local_installation_identity
    app=create_public_app(runtime_config=build_config(root,dsn,frontend_origin=origin,validation_mode=validation_mode))
    initialize_local_installation_identity(app.state.runtime_composition.session_factory)
    return app


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--data-root',type=Path,required=True)
    parser.add_argument('--dsn-file',type=Path,required=True)
    parser.add_argument('--port',type=int,default=18114)
    parser.add_argument('--frontend-origin',default='http://127.0.0.1:13114')
    parser.add_argument('--mode',choices=['validation','real-use'],default='validation')
    args=parser.parse_args()
    if args.port!=18114:raise ValueError('experiment_port_invalid')
    os.umask(0o077)
    validation_mode=args.mode=='validation'
    install_validation_guards(validation_mode=validation_mode)
    dsn=args.dsn_file.read_text().strip()
    from urllib.parse import urlsplit
    if urlsplit(dsn).username!='angmoo_pg_run01_runtime':
        raise ValueError('postgresql_serving_runtime_role_required')
    app=create_app(args.data_root,dsn,args.frontend_origin,validation_mode=validation_mode)
    import uvicorn
    uvicorn.run(app,host='127.0.0.1',port=args.port,access_log=False,log_level='warning')


if __name__=='__main__':main()
