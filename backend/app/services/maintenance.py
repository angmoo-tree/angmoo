from sqlalchemy.orm import Session

from app import models, schemas
from app.core.config import settings


INFO_BANNER_KEY = "agent_activity_info"
MAINTENANCE_BANNER_KEY = "agent_activity_maintenance"


class AgentActivityMaintenanceError(Exception):
    pass


def get_agent_activity_maintenance(
    db: Session | None = None,
) -> schemas.AgentActivityMaintenanceRead:
    info = _info_banner(db)
    maintenance = _maintenance_banner(db)
    allowed_character_ids = agent_activity_auto_tick_allowed_character_ids()
    maintenance_visible = maintenance["enabled"] and bool(
        maintenance["title"] or maintenance["message"]
    )
    notice_enabled = (
        not maintenance_visible
        and info["enabled"]
        and bool(info["title"] or info["message"])
    )
    return schemas.AgentActivityMaintenanceRead(
        enabled=maintenance_visible,
        title=maintenance["title"],
        message=maintenance["message"],
        blocks_auto_ticks=maintenance["blocks_auto_ticks"],
        blocks_run_now=maintenance["blocks_run_now"],
        blocks_feed_cues=maintenance["blocks_feed_cues"],
        auto_tick_allowlist_active=maintenance["blocks_auto_ticks"]
        and bool(allowed_character_ids),
        auto_tick_allowed_count=len(allowed_character_ids),
        notice_enabled=notice_enabled,
        notice_title=info["title"],
        notice_message=info["message"],
    )


def agent_activity_maintenance_enabled(db: Session | None = None) -> bool:
    return _maintenance_banner(db)["enabled"]


def agent_activity_blocks_auto_ticks(db: Session | None = None) -> bool:
    maintenance = _maintenance_banner(db)
    return maintenance["enabled"] and maintenance["blocks_auto_ticks"]


def agent_activity_blocks_run_now(db: Session | None = None) -> bool:
    maintenance = _maintenance_banner(db)
    return maintenance["enabled"] and maintenance["blocks_run_now"]


def agent_activity_blocks_feed_cues(db: Session | None = None) -> bool:
    maintenance = _maintenance_banner(db)
    return maintenance["enabled"] and maintenance["blocks_feed_cues"]


def agent_activity_auto_tick_allowed_character_ids() -> set[str]:
    return set(settings.agent_activity_maintenance_auto_tick_allowed_character_ids)


def ensure_auto_ticks_available(db: Session | None = None) -> None:
    if agent_activity_blocks_auto_ticks(db):
        raise AgentActivityMaintenanceError(_maintenance_banner(db)["message"])


def ensure_run_now_available(db: Session | None = None) -> None:
    if agent_activity_blocks_run_now(db):
        raise AgentActivityMaintenanceError(_maintenance_banner(db)["message"])


def ensure_feed_cues_available(db: Session | None = None) -> None:
    if agent_activity_blocks_feed_cues(db):
        raise AgentActivityMaintenanceError(_maintenance_banner(db)["message"])


def ensure_agent_activity_available(db: Session | None = None) -> None:
    ensure_run_now_available(db)


def _banner_row(db: Session | None, key: str) -> models.SiteOperationBanner | None:
    if db is None:
        return None
    return db.get(models.SiteOperationBanner, key)


def _info_banner(db: Session | None) -> dict[str, object]:
    row = _banner_row(db, INFO_BANNER_KEY)
    if row is not None:
        return {
            "enabled": row.enabled,
            "title": row.title,
            "message": row.message,
            "blocks_auto_ticks": False,
            "blocks_run_now": False,
            "blocks_feed_cues": False,
        }
    return {
        "enabled": settings.agent_activity_notice_enabled,
        "title": settings.agent_activity_notice_title,
        "message": settings.agent_activity_notice_message,
        "blocks_auto_ticks": False,
        "blocks_run_now": False,
        "blocks_feed_cues": False,
    }


def _maintenance_banner(db: Session | None) -> dict[str, object]:
    row = _banner_row(db, MAINTENANCE_BANNER_KEY)
    if row is not None:
        return {
            "enabled": row.enabled,
            "title": row.title,
            "message": row.message,
            "blocks_auto_ticks": row.blocks_auto_ticks,
            "blocks_run_now": row.blocks_run_now,
            "blocks_feed_cues": row.blocks_feed_cues,
        }
    enabled = settings.agent_activity_maintenance_enabled
    return {
        "enabled": enabled,
        "title": settings.agent_activity_maintenance_title,
        "message": settings.agent_activity_maintenance_message,
        "blocks_auto_ticks": enabled,
        "blocks_run_now": enabled,
        "blocks_feed_cues": enabled,
    }
