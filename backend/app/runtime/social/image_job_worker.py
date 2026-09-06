from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
import logging

from functools import partial
from app.domains.characters.service.profile import get_character
from app.domains.social.service.image_jobs import process_one_post_image_job as process_image_job
from app.config import settings
from app.core.db import SessionLocal
from app.runtime.social import image_generation as post_image_generation
from app.domains.social.service import image_attachment


logger = logging.getLogger(__name__)


async def run_post_image_job_worker() -> None:
    while True:
        try:
            await process_one_post_image_job()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("post image job worker failed")
        await asyncio.sleep(settings.post_image_job_worker_interval_seconds)


async def process_one_post_image_job() -> bool:
    with SessionLocal() as db:
        stale_before = datetime.now(UTC) - timedelta(
            seconds=settings.post_image_job_stale_seconds
        )
        return await process_image_job(
            db, stale_before=stale_before,
            get_character=partial(get_character, db),
            prepare_image=post_image_generation.prepare_local_api_post_image,
            attach_image=image_attachment.attach_prepared_post_image,
        )
