from __future__ import annotations

from pathlib import Path
import sys


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

import argparse
import socket
import threading

from app.core.db import SessionLocal
from app.runtime.graph_projection.replay import (
    GraphProjectionReplayService,
    create_replay_run,
)
from app.runtime.graph_projection.process_client import graph_client_from_settings


def main() -> int:
    parser = argparse.ArgumentParser(description="Run an audited P7 graph replay")
    parser.add_argument("--resume-run-id")
    parser.add_argument("--world-id")
    parser.add_argument(
        "--mode",
        choices=("world_rebuild", "event_reprocess", "dead_retry"),
    )
    parser.add_argument("--source-event-id")
    parser.add_argument("--requested-by")
    parser.add_argument("--reason-code")
    args = parser.parse_args()

    if args.resume_run_id:
        create_values = (
            args.world_id,
            args.mode,
            args.source_event_id,
            args.requested_by,
            args.reason_code,
        )
        if any(value is not None for value in create_values):
            parser.error("--resume-run-id cannot be combined with create arguments")
        run_id = args.resume_run_id
    else:
        required = {
            "--world-id": args.world_id,
            "--mode": args.mode,
            "--requested-by": args.requested_by,
            "--reason-code": args.reason_code,
        }
        missing = [name for name, value in required.items() if not value]
        if missing:
            parser.error("required for a new replay: " + ", ".join(missing))
        with SessionLocal() as db:
            run = create_replay_run(
                db,
                world_id=args.world_id,
                mode=args.mode,
                source_event_id=args.source_event_id,
                requested_by=args.requested_by,
                reason_code=args.reason_code,
            )
            db.commit()
            run_id = run.id
        print(f"graph_replay_created run_id={run_id}")

    client = graph_client_from_settings()
    try:
        client.verify_connectivity()
        client.bootstrap()
        service = GraphProjectionReplayService(
            session_factory=SessionLocal,
            store=client,
            worker_id=f"replay-{socket.gethostname()}-{threading.get_native_id()}",
        )
        completed = service.execute(run_id)
        print(
            "graph_replay "
            f"run_id={completed.id} status={completed.status} "
            f"total={completed.total_count} applied={completed.applied_count} "
            f"noop={completed.noop_count} failed={completed.failed_count}"
        )
        return 0
    finally:
        client.close()


if __name__ == "__main__":
    raise SystemExit(main())
