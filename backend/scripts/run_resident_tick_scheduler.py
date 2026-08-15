from __future__ import annotations

from pathlib import Path
import asyncio
import sys


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.services.resident_tick_scheduler import run_resident_tick_scheduler


def main() -> int:
    try:
        asyncio.run(run_resident_tick_scheduler())
    except KeyboardInterrupt:
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
