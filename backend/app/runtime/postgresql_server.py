"""The official PostgreSQL API process; schema changes use the owner CLI."""
import argparse
from pathlib import Path


def create_app(data_root, origin, *, validation_mode=False, desktop_launch_token=''):
    from app.runtime.postgresql_installation import read_dsn
    from app.runtime.postgresql_runtime import build_config
    from app.main import create_public_app
    from app.runtime.configuration import initialize_local_installation_identity
    root=Path(data_root)
    config=build_config(root,read_dsn(root/'secrets/postgresql-runtime-dsn'),frontend_origin=origin,
        validation_mode=validation_mode,desktop_launch_token=desktop_launch_token)
    app=create_public_app(runtime_config=config)
    initialize_local_installation_identity(app.state.runtime_composition.session_factory)
    return app


def main():
    parser=argparse.ArgumentParser(description='Angmoo PostgreSQL backend / PostgreSQL 백엔드')
    parser.add_argument('--data-root',type=Path,required=True)
    parser.add_argument('--host',default='127.0.0.1')
    parser.add_argument('--port',type=int,default=8080)
    parser.add_argument('--frontend-origin',default='http://127.0.0.1:3000')
    parser.add_argument('--validation',action='store_true')
    parser.add_argument('--diagnostics',action='store_true')
    args=parser.parse_args()
    if args.diagnostics:
        import json
        from app.runtime.postgresql_installation import read_dsn
        from app.runtime.postgresql_runtime import build_config
        from app.runtime.configuration import compose_runtime
        from app.domains.runtime.service.status import ReadApplicationRuntimeStatus
        from app.runtime.diagnostics.status_composition import create_runtime_status_reader
        from app.domains.runtime.schemas import runtime_status_read
        from app.core.redaction import sanitize_support_bundle_metadata
        config=build_config(args.data_root,read_dsn(args.data_root/'secrets/postgresql-runtime-dsn'),frontend_origin=args.frontend_origin)
        composition=compose_runtime(config)
        try:
            with composition.session_factory() as session:
                result=ReadApplicationRuntimeStatus(create_runtime_status_reader(session,config=composition.settings)).execute()
                payload=runtime_status_read(result,runtime_profile=config.profile.value,canonical_generation=config.generation,
                    persistence_provider='postgresql',graph_provider='ladybug').model_dump(mode='json')
            print(json.dumps(sanitize_support_bundle_metadata(payload)))
        finally:composition.dispose()
        return
    from app.runtime.logging_config import configure_application_logging,uvicorn_logging_config
    configure_application_logging()
    import uvicorn
    uvicorn.run(create_app(args.data_root,args.frontend_origin,validation_mode=args.validation),
        host=args.host,port=args.port,log_config=uvicorn_logging_config())


if __name__=='__main__':main()
