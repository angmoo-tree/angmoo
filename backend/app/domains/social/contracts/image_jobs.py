"""Typed image-worker collaborators bound to the caller's Session."""
from datetime import datetime
from typing import Any, Protocol
from sqlalchemy.orm import Session
from app.domains.social.contracts.image_generation import ImageCharacter, PreparedPostImage


class LocalImagePreparer(Protocol):
    async def __call__(self, *, db: Session, character: ImageCharacter, image_prompt: str,
                       run_started_at: datetime, key_source: str, quota_reservation_id: int | None,
                       post_id: str, job_id: int) -> PreparedPostImage: ...


class PreparedImageAttacher(Protocol):
    def __call__(self, *, db: Session, post_id: str, prepared: PreparedPostImage) -> dict[str, Any]: ...
