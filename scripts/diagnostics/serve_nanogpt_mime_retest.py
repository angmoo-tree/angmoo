"""Opt-in isolated source runtime; actual scheduler and actual NanoGPT only."""
from __future__ import annotations
import argparse
import asyncio
from functools import partial
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
from nanogpt_retest_support import RetestGuard, CASES, atomic_json


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--private-root", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--port", type=int, default=18388)
    parser.add_argument("--execute-authorized-plan", action="store_true")
    args = parser.parse_args()
    if not args.execute_authorized_plan:
        print(json.dumps({"mode": "dry_run", "image_limit": 5, "text_limit": 10, "key_reads": 0, "network_calls": 0}))
        return
    private, evidence = args.private_root.resolve(), args.evidence.resolve()
    if private == evidence or private in evidence.parents or evidence in private.parents:
        raise SystemExit("retest_private_and_evidence_must_be_separate")
    # Apply test timing before the first app.config import. This keeps the
    # normal initial_tick_schedule path, with an explicit zero initial spread.
    os.environ.update(RESIDENT_TICK_SCHEDULER_ENABLED="false", POST_IMAGE_JOB_WORKER_ENABLED="false",
        DIRECT_LLM_RATE_LIMIT_MAX_WAIT_SECONDS="0", SEED_DEMO_DATA="false", RESIDENT_TICK_INITIAL_SPREAD_SECONDS="0",
        RESIDENT_TICK_INTERVAL_SECONDS="5")
    guard = RetestGuard(evidence, private)
    atomic_json(evidence / "server-process.json", {"pid": os.getpid(), "port": args.port,
        "private_root": str(private), "data_root": str(private / "data")})
    import httpx
    send, async_send = httpx.Client.send, httpx.AsyncClient.send
    def counted_send(client, request, *a, **kw):
        index = guard.before(request)
        response = send(client, request, *a, **kw)
        guard.after(index, response)
        return response
    async def counted_async_send(client, request, *a, **kw):
        index = guard.before(request)
        response = await async_send(client, request, *a, **kw)
        guard.after(index, response)
        return response
    httpx.Client.send, httpx.AsyncClient.send = counted_send, counted_async_send
    from app.integrations.image_api import ImageHttp, API_ROOTS
    bounded_request = ImageHttp.request
    async def observed_request(client, method, url, **kw):
        response = await bounded_request(client, method, url, **kw)
        if method == "POST" and url == API_ROOTS["nanogpt"]:
            try:
                guard.observe_image(response)
            except Exception as exc:
                # Observation failure must not discard an already received
                # valid result, or cause an extra paid submission.
                atomic_json(evidence / "observation-error.json", {"stage": "observation", "error_type": type(exc).__name__})
        return response
    ImageHttp.request = observed_request
    import app.main as composition_root
    from app.runtime.single_backend_components import SingleBackendRuntimeComponents
    from app.runtime.component_workers import run_projector_component
    from app.runtime.resident.scheduler import run_resident_tick_scheduler, _tick_once
    from app.domains.routines.schemas import ResidentSlotTickRead
    def controlled_components(config, *, session_factory):
        async def gated_tick():
            with guard.lock:
                state = json.loads(guard.active.read_text("utf8")) if guard.active.exists() else {}
                if not state.get("tick_requested"):
                    return ResidentSlotTickRead(due_count=0, started_count=0, results=[], slots=[])
                state["tick_requested"] = False
                atomic_json(guard.active, state)
                case = state["id"]
            result = await _tick_once(config, session_factory)
            if result.started_count == 0 and result.due_count == 0:
                with guard.lock:
                    state = json.loads(guard.active.read_text("utf8"))
                    if state["id"] == case:
                        state["tick_requested"] = True; atomic_json(guard.active, state)
                return result
            # Retain identities and counts, not private model/conversation text.
            record = {"due_count": result.due_count, "started_count": result.started_count,
                "run_ids": [row.run_id for row in result.results]}
            atomic_json(evidence / (case + "-routine-run.json"), record)
            return result
        async def scheduler(stop, listener):
            await run_resident_tick_scheduler(stop_event=stop, state_listener=listener,
                config=config, session_factory=session_factory, tick_runner=gated_tick)
        return SingleBackendRuntimeComponents(scheduler_runner=scheduler,
            projector_runner=partial(run_projector_component, config=config, session_factory=session_factory),
            startup_timeout_seconds=config.LOCAL_RUNTIME_COMPONENT_STARTUP_TIMEOUT_SECONDS,
            shutdown_timeout_seconds=config.LOCAL_RUNTIME_COMPONENT_SHUTDOWN_TIMEOUT_SECONDS)
    composition_root.create_single_backend_runtime_components = controlled_components
    from app.runtime.contributor_backend import create_contributor_runtime_app
    from app.runtime.logging_config import configure_application_logging, uvicorn_logging_config
    configure_application_logging()
    app = create_contributor_runtime_app(data_root=private / "data", frontend_origin="http://127.0.0.1:13000")
    from fastapi import Depends, HTTPException
    from app.domains.identity.service.http_auth import get_current_user
    @app.post("/_diagnostics/tick")
    async def tick(user=Depends(get_current_user)):
        if not guard.active.exists():
            raise HTTPException(409, "authorized_case_required")
        state = json.loads(guard.active.read_text("utf8"))
        if state["id"] not in CASES:
            raise HTTPException(409, "authorized_case_required")
        path = evidence / (state["id"] + "-routine-run.json")
        if path.exists():
            return json.loads(path.read_text("utf8"))
        state["tick_requested"] = True; atomic_json(guard.active, state)
        for _ in range(600):
            if path.exists():
                return json.loads(path.read_text("utf8"))
            await asyncio.sleep(1)
        raise HTTPException(504, "diagnostic_tick_result_pending")
    @app.post("/_diagnostics/worker-recover")
    async def recover(user=Depends(get_current_user)):
        # Existing worker only: no separate insertion/attachment implementation.
        await app.state.media_runtime.worker.tick()
        return {"completed": True}
    import uvicorn
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=args.port,
        log_config=uvicorn_logging_config(), access_log=False))
    @app.post("/api/_diagnostics/stop")
    async def stop(user=Depends(get_current_user)):
        server.should_exit = True
        return {"stopping": True}
    server.run()


if __name__ == "__main__":
    main()
