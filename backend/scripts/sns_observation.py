"""Start, inspect and export a bounded local SNS V2 observation session.

Run this against the same resolved data root as the embedded backend. The
command never starts autonomous activity or calls an AI provider.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.runtime.diagnostics.sns_observation import active_session
from app.runtime.diagnostics.sns_observation_report import (
    export_session, list_worlds, session_status, start_session, stop_session,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, required=True,
                        help="Resolved embedded Angmoo data root used by the running backend")
    commands = parser.add_subparsers(dest="command", required=True)
    worlds = commands.add_parser("worlds", help="List local World IDs for a session")
    worlds.add_argument("--database", type=Path)
    start = commands.add_parser("start", help="Start one observation window")
    start.add_argument("--world", required=True, help="World ID")
    start.add_argument("--actor", action="append", default=None,
                       help="Autonomous WorldCharacter ID; repeat or omit for all active autonomous characters")
    start.add_argument("--minutes", type=int, default=120)
    start.add_argument("--tail-minutes", type=int, default=10)
    start.add_argument("--database", type=Path,
                       help="Canonical angmoo.sqlite3 under the data root; otherwise use current-generation.json")
    start.add_argument("--source-revision", help="Confirmed running source/image revision, if known")
    status = commands.add_parser("status", help="Inspect observation and recorder health")
    status.add_argument("--session", help="Defaults to active session")
    stop = commands.add_parser("stop", help="Stop admitting new diagnostic events")
    stop.add_argument("--session", help="Defaults to active session")
    export = commands.add_parser("export", help="Read-only SQLite and event export")
    export.add_argument("--session", required=True)
    export.add_argument("--output", type=Path, required=True,
                        help="An empty local directory, outside the source session")
    export.add_argument("--database", type=Path)
    args = parser.parse_args(argv)
    root = args.data_root
    try:
        if args.command == "worlds":
            result = list_worlds(root, args.database)
        elif args.command == "start":
            result = start_session(root, world_id=args.world, actor_ids=args.actor,
                minutes=args.minutes, tail_minutes=args.tail_minutes,
                explicit_db=args.database, source_revision=args.source_revision)
        else:
            chosen = args.session
            if not chosen:
                active = active_session(root)
                if active is None:
                    raise ValueError("sns_observation_no_active_session")
                chosen = active["session_id"]
            if args.command == "status":
                result = session_status(root, chosen)
            elif args.command == "stop":
                result = stop_session(root, chosen)
            else:
                result = export_session(root, chosen, destination=args.output,
                                        explicit_db=args.database)
    except (OSError, ValueError, KeyError) as exc:
        # Only fixed diagnostic identifiers may be printed. Paths and provider
        # text are kept out of the command's error output.
        import re
        reason = str(exc)
        safe = reason if re.fullmatch(r"sns_[a-z0-9_]{1,100}", reason) else type(exc).__name__
        print(json.dumps({"status": "error", "code": safe}, ensure_ascii=False), file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
