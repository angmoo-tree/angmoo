"""Canonical setting/banner reads and privacy scrub on the caller's Session."""
from sqlalchemy import update
from sqlalchemy.orm import Session
from app.domains.operations.models import SiteOperationSetting, SiteOperationBanner, AdminAuditLog

def read_setting(db: Session, key: str) -> SiteOperationSetting | None:
    return db.get(SiteOperationSetting, key)

def read_banner(db: Session | None, key: str) -> SiteOperationBanner | None:
    if db is None:
        return None
    return db.get(SiteOperationBanner, key)


def scrub_user_attribution(db: Session, user_id: str) -> None:
    db.execute(
        update(AdminAuditLog)
        .where(AdminAuditLog.admin_user_id == user_id)
        .values(note=None, metadata_json=None, request_ip=None, user_agent=None)
    )
    db.execute(
        update(SiteOperationBanner)
        .where(SiteOperationBanner.updated_by_user_id == user_id)
        .values(updated_by_user_id=None)
    )
    db.execute(
        update(SiteOperationSetting)
        .where(SiteOperationSetting.updated_by_user_id == user_id)
        .values(updated_by_user_id=None)
    )
