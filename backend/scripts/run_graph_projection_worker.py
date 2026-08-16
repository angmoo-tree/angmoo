from __future__ import annotations

from pathlib import Path
import sys


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

import argparse
import logging
import socket
import threading

from app.core.config import settings
from app.core.db import SessionLocal
from app.services.graph_projection_runtime import graph_client_from_settings
from app.services.graph_projection_worker import GraphProjectionWorker
from app.runtime.shutdown import installed_shutdown_signal_handlers


logger = logging.getLogger(__name__)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the P7 Neo4j projection worker")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--once", action="store_true")
    mode.add_argument("--loop", action="store_true")
    mode.add_argument("--bootstrap-only", action="store_true")
    parser.add_argument("--bootstrap", action="store_true")
    args = parser.parse_args()

    client = graph_client_from_settings()
    stop_event = threading.Event()
    ready_path = Path(settings.GRAPH_PROJECTOR_READY_PATH)

    def write_state(state: str) -> None:
        ready_path.parent.mkdir(parents=True, exist_ok=True)
        ready_path.write_text(f"state={state}\n", encoding="utf-8")

    def request_shutdown(signum: int) -> None:
        logger.info("graph projector shutdown requested signal=%s", signum)
        write_state("draining")
        stop_event.set()

    try:
        with installed_shutdown_signal_handlers(request_shutdown):
            client.verify_connectivity()
            if args.bootstrap:
                client.bootstrap()
            if args.bootstrap_only:
                client.bootstrap()
                print("graph_projection_bootstrap_succeeded=true")
                return 0
            worker_id = settings.graph_projector_worker_id or (
                f"{socket.gethostname()}-{threading.get_native_id()}"
            )
            worker = GraphProjectionWorker(
                session_factory=SessionLocal,
                store=client,
                worker_id=worker_id,
                batch_size=settings.graph_projector_batch_size,
                concurrency=settings.graph_projector_concurrency,
                command_timeout_seconds=settings.graph_projector_command_timeout_seconds,
                shutdown_drain_seconds=settings.graph_projector_shutdown_drain_seconds,
            )
            write_state("ready")
            if args.once:
                result = worker.process_batch(stop_event=stop_event)
                print(
                    "graph_projection_batch "
                    f"claimed={result.claimed} succeeded={result.succeeded} "
                    f"retried={result.retried} dead={result.dead} "
                    f"cancelled={result.cancelled} lease_lost={result.lease_lost}"
                )
            else:
                worker.run_loop(
                    poll_interval_seconds=settings.graph_projector_poll_interval_seconds,
                    stop_event=stop_event,
                    connectivity_probe=client.verify_connectivity,
                    state_listener=write_state,
                )
        return 0
    finally:
        ready_path.unlink(missing_ok=True)
        client.close()


if __name__ == "__main__":
    raise SystemExit(main())
