from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
import logging

from app import models
from app.core.config import settings
from app.core.db import SessionLocal
from app.cruds import community as community_crud
from app.services import post_image_generation


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
        community_crud.mark_stale_post_image_generation_jobs_failed(
            db,
            stale_before=stale_before,
        )
        job = community_crud.claim_next_post_image_generation_job(db)
        if job is None:
            return False
        character = db.get(models.Character, job.character_id)
        if character is None or character.deleted_at is not None:
            community_crud.finish_post_image_generation_job(
                db,
                job,
                status="failed",
                failure_class="character_missing",
            )
            return True
        post = db.get(models.Post, job.post_id)
        if post is None or post.deleted_at is not None:
            community_crud.finish_post_image_generation_job(
                db,
                job,
                status="failed",
                failure_class="post_missing",
            )
            return True
        prepared = await post_image_generation.prepare_local_api_post_image(
            db=db,
            character=character,
            image_prompt=job.image_prompt,
            run_started_at=job.started_at or datetime.now(UTC),
            key_source=job.key_source,
            quota_reservation_id=job.quota_reservation_id,
            post_id=job.post_id,
            job_id=job.id,
        )
        attached = post_image_generation.attach_prepared_post_image(
            db=db,
            post_id=job.post_id,
            prepared=prepared,
        )
        community_crud.finish_post_image_generation_job(
            db,
            job,
            status=attached.get("status", "failed"),
            prompt_hash=attached.get("prompt_hash"),
            reference_source=attached.get("reference_source"),
            skip_reason=attached.get("skip_reason"),
            failure_class=attached.get("failure_class"),
            media_url=attached.get("media_url"),
            byte_size=attached.get("byte_size"),
        )
        return True
