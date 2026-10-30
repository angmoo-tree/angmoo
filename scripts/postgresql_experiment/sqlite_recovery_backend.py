"""Old, unchanged app + D0-derived copy; suppress paid/autonomous effects only.

This is a recovery/read smoke harness, not an old-version activity acceptance.
"""
import sys
from pathlib import Path
from contextlib import asynccontextmanager
from functools import partial


def main():
    def audit(event,args):
        if event=='socket.connect' and isinstance(args[1],tuple):
            raise RuntimeError('recovery_external_provider_disabled')
        if event=='socket.getaddrinfo' and args[0] not in {'127.0.0.1','localhost','::1',None}:
            raise RuntimeError('recovery_external_provider_disabled')
    sys.addaudithook(audit)
    import app.main as main_module
    from app.runtime.single_backend_components import SingleBackendRuntimeComponents
    from app.runtime.component_workers import run_projector_component
    import app.runtime.resident.scheduler as scheduler
    original_lifespan=main_module.create_lifespan
    async def suspended(stop_event,state_listener):
        state_listener('ready');await stop_event.wait()
    def validation_lifespan(*args,**kwargs):
        kwargs['memory_runtime']=None;kwargs['memory_hybrid_runtime']=None
        kwargs['component_manager_factory']=lambda:SingleBackendRuntimeComponents(scheduler_runner=suspended,
            projector_runner=partial(run_projector_component,config=kwargs['runtime_settings'],session_factory=kwargs['session_factory']))
        original=original_lifespan(*args,**kwargs)
        @asynccontextmanager
        async def guarded(app):
            for name in ('checkpoint_maintenance','media_runtime','world_deletion_worker'):setattr(app.state,name,None)
            async with original(app):yield
        return guarded
    main_module.create_lifespan=validation_lifespan
    scheduler.scheduler_is_ready=lambda config:True
    from app.runtime.contributor_backend import create_contributor_runtime_app
    app=create_contributor_runtime_app(data_root=Path('/experiment/migration/D2-recovery'),frontend_origin='http://127.0.0.1:13114')
    @app.middleware('http')
    async def label(request,call_next):
        response=await call_next(request);response.headers['X-Angmoo-Validation']='old-version-D0-recovery-read-smoke';return response
    import uvicorn
    uvicorn.run(app,host='127.0.0.1',port=18114,access_log=False,log_level='warning')


if __name__=='__main__':main()
