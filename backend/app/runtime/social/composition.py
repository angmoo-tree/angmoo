"""Connect concrete Social reads and write collaborators once per application."""

from fastapi import FastAPI
from app.runtime.social.timeline import timeline_service
from app.runtime.social.inbox import inbox_service
from app.runtime.social.discovery import discovery_service
from app.runtime.social.profile_activity import profile_activity_service

from app.runtime.social.profile_composition import (
    world_character_social_profile_service,
)
from app.runtime.social.manual_feed_references import RuntimeManualFeedReferences
from app.runtime.social.sqlalchemy_unit_of_work import SqlAlchemySocialWriteUnitOfWork


def configure_social_runtime(app: FastAPI) -> None:
    app.state.social_timeline_service = timeline_service
    app.state.social_inbox_service = inbox_service
    app.state.social_discovery_service = discovery_service
    app.state.social_profile_activity_service = profile_activity_service
    app.state.social_world_profile_factory = world_character_social_profile_service
    app.state.social_manual_feed_reference_factory = RuntimeManualFeedReferences
    app.state.social_source_write_executor_factory = SqlAlchemySocialWriteUnitOfWork
