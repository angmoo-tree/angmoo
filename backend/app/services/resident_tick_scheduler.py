import asyncio
import logging

from app import schemas
from app.core.config import settings
from app.core.db import SessionLocal
from app.services import agent_runs


logger = logging.getLogger(__name__)


async def run_resident_tick_scheduler() -> None:
    while True:
        try:
            with SessionLocal() as db:
                await agent_runs.tick_resident_slots(
                    db,
                    schemas.ResidentSlotTickCreate(
                        post_id=settings.resident_tick_post_id,
                        max_runs=settings.resident_tick_max_runs,
                        timeout_seconds=settings.openclaw_timeout_seconds,
                    ),
                )
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("resident tick scheduler failed")
        await asyncio.sleep(settings.resident_tick_interval_seconds)
