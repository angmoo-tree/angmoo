from __future__ import annotations

from pathlib import Path
import sys


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

import argparse
import json
import os
import socket
import threading
import time

from sqlalchemy.engine import URL


def _bootstrap_compose_database_url() -> None:
    """Let ``docker compose exec`` reuse the entrypoint-owned DB secret."""

    if os.getenv("DATABASE_URL"):
        return
    secret_dir = Path(os.getenv("ANGMOO_SECRET_DIR", "/run/angmoo-secrets"))
    password_path = secret_dir / "postgresql_password"
    if not password_path.is_file():
        return
    password = password_path.read_text(encoding="utf-8").strip()
    user = os.getenv("ANGMOO_POSTGRES_USER", "angmoo")
    host = os.getenv("ANGMOO_POSTGRES_HOST", "postgresql")
    database = os.getenv("ANGMOO_POSTGRES_DB", "angmoo")
    os.environ["DATABASE_URL"] = URL.create(
        "postgresql+psycopg",
        username=user,
        password=password,
        host=host,
        port=5432,
        database=database,
    ).render_as_string(
        hide_password=False
    )


_bootstrap_compose_database_url()

from app.core.config import settings
from app.core.db import SessionLocal
from app.integrations.ladybug_projection import LadybugRelationshipProjection
from app.services.graph_projection_replay import (
    GraphProjectionReplayService,
    create_replay_run,
)


def _projection(root: str | None) -> LadybugRelationshipProjection:
    database_root = (
        Path(root).resolve() if root else settings.ladybug_database_root
    )
    return LadybugRelationshipProjection(database_root=database_root)


def _print_digest(
    projection: LadybugRelationshipProjection,
    *,
    world_id: str,
) -> None:
    print(
        json.dumps(
            projection.world_digest(world_id),
            ensure_ascii=True,
            sort_keys=True,
        )
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Manage the production-OFF LadybugDB relationship-graph preview"
        )
    )
    parser.add_argument(
        "command",
        choices=("replay", "clear", "digest", "hold"),
    )
    parser.add_argument("--world-id")
    parser.add_argument("--database-root")
    parser.add_argument("--hold-seconds", type=float, default=300.0)
    args = parser.parse_args()

    if args.command != "hold" and not args.world_id:
        parser.error("--world-id is required")

    with _projection(args.database_root) as projection:
        projection.verify_connectivity()
        if args.command == "clear":
            projection.clear_world(args.world_id)
            print(f"ladybug_preview_cleared world_id={args.world_id}")
            _print_digest(projection, world_id=args.world_id)
            return 0
        if args.command == "digest":
            _print_digest(projection, world_id=args.world_id)
            return 0
        if args.command == "hold":
            seconds = max(1.0, min(args.hold_seconds, 900.0))
            print(
                "ladybug_preview_lock_held "
                f"seconds={seconds:g}",
                flush=True,
            )
            try:
                time.sleep(seconds)
            except KeyboardInterrupt:
                print("ladybug_preview_lock_released", flush=True)
            return 0

        with SessionLocal() as db:
            run = create_replay_run(
                db,
                world_id=args.world_id,
                mode="world_rebuild",
                source_event_id=None,
                requested_by="ladybug-preview",
                reason_code="ui_provider_validation",
            )
            db.commit()
            run_id = run.id
        replay = GraphProjectionReplayService(
            session_factory=SessionLocal,
            store=projection,
            worker_id=(
                f"ladybug-preview-{socket.gethostname()}-"
                f"{threading.get_native_id()}"
            ),
        )
        completed = replay.execute(run_id)
        print(
            "ladybug_preview_replay "
            f"run_id={completed.id} status={completed.status} "
            f"total={completed.total_count} applied={completed.applied_count} "
            f"noop={completed.noop_count} failed={completed.failed_count}"
        )
        _print_digest(projection, world_id=args.world_id)
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
