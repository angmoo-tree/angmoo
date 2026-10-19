"""Bounded staging maintenance, independent of the draft/import orchestrators."""
import logging
from sqlalchemy import select, or_
from sqlalchemy.exc import SQLAlchemyError
from app.domains.characters import models
from app.integrations.media.card_staging import cleanup_staging

logger = logging.getLogger(__name__)

def display_is_referenced(db, url):
    return bool(db.scalar(select(models.AgentCreationDraft.id).where(or_(
        models.AgentCreationDraft.avatar_temp_url == url, models.AgentCreationDraft.banner_temp_url == url)).limit(1))
        or db.scalar(select(models.Character.id).where(or_(models.Character.avatar_url == url,
            models.Character.banner_url == url)).limit(1)))


def cleanup_card_staging(db):
    if db.new or db.dirty or db.deleted:
        raise RuntimeError("card_cleanup_requires_clean_unit_of_work")
    db.rollback()
    def referenced(url):
        try:
            return display_is_referenced(db, url)
        finally:
            db.rollback()
    try:
        cleanup_staging(referenced)
    except (SQLAlchemyError, OSError):
        # Cleanup is retryable maintenance. Unconfirmed references are retained;
        # a temporary read failure must not prevent a new draft from opening.
        logger.warning("card_staging_cleanup_deferred")
