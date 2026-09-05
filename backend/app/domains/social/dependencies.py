"""Request access to application-composed Social services and shared HTTP dependencies."""

from fastapi import Depends, Request
from sqlalchemy.orm import Session
from app.api.identity_dependencies import get_current_user, get_optional_current_user
from app.database import get_db
from app.domains.social.contracts.manual_feed import ManualFeedReferences
from app.domains.social.contracts.write_execution import SocialWriteUnitOfWorkPort
from app.domains.social.service.world_profile import WorldSocialProfileService
from app.domains.social.service.timeline import SocialTimelineService
from app.domains.social.service.inbox import SocialInboxService
from app.domains.social.service.discovery import SocialDiscoveryService
from app.domains.social.service.profile_activity import ProfileActivityService


def get_timeline_service(request: Request) -> SocialTimelineService:
    service = getattr(request.app.state, "social_timeline_service", None)
    if service is None:
        raise RuntimeError("social timeline service is not configured")
    return service


def get_inbox_service(request: Request) -> SocialInboxService:
    service = getattr(request.app.state, "social_inbox_service", None)
    if service is None:
        raise RuntimeError("social inbox service is not configured")
    return service


def get_discovery_service(request: Request) -> SocialDiscoveryService:
    service = getattr(request.app.state, "social_discovery_service", None)
    if service is None:
        raise RuntimeError("social discovery service is not configured")
    return service


def get_profile_activity_service(request: Request) -> ProfileActivityService:
    service = getattr(request.app.state, "social_profile_activity_service", None)
    if service is None:
        raise RuntimeError("social profile_activity service is not configured")
    return service


def get_world_profile_service(
    request: Request,
    db: Session = Depends(get_db),
) -> WorldSocialProfileService:
    factory = getattr(request.app.state, "social_world_profile_factory", None)
    if factory is None:
        raise RuntimeError("social World profile service is not configured")
    return factory(db)


def get_manual_feed_references(
    request: Request,
    db: Session = Depends(get_db),
) -> ManualFeedReferences:
    factory = getattr(request.app.state, "social_manual_feed_reference_factory", None)
    if factory is None:
        raise RuntimeError("social manual feed references are not configured")
    return factory(db)


def get_source_write_executor(
    request: Request,
    db: Session = Depends(get_db),
) -> SocialWriteUnitOfWorkPort:
    factory = getattr(request.app.state, "social_source_write_executor_factory", None)
    if factory is None:
        raise RuntimeError("social source write executor is not configured")
    return factory(db)
