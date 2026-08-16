from __future__ import annotations

from pathlib import Path
import asyncio
import logging
import sys


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.services.resident_tick_scheduler import run_resident_tick_scheduler
from app.runtime.shutdown import installed_shutdown_signal_handlers


logger = logging.getLogger(__name__)


async def _run() -> None:
    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()

    def request_shutdown(signum: int) -> None:
        logger.info("resident scheduler shutdown requested signal=%s", signum)
        loop.call_soon_threadsafe(stop_event.set)

    with installed_shutdown_signal_handlers(request_shutdown):
        await run_resident_tick_scheduler(stop_event=stop_event)


def main() -> int:
    try:
        asyncio.run(_run())
    except KeyboardInterrupt:
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
