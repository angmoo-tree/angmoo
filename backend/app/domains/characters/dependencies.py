"""HTTP connection to the application-composed Character runtime callbacks."""
from fastapi import Request
from app.api.identity_dependencies import get_current_user
from app.core.db import get_db
from app.domains.characters.contracts import CharacterManagementWorkflows, CreatorWorkflows, CharacterMediaWorkflows, CharacterImageGenerationWorkflows


def get_character_management_workflows(request: Request) -> CharacterManagementWorkflows:
    factory = getattr(request.app.state, "character_management_workflows", None)
    if not callable(factory):
        raise RuntimeError("character management workflows are not configured")
    return factory()


def get_creator_workflows(request: Request) -> CreatorWorkflows:
    factory = getattr(request.app.state, "creator_workflows", None)
    if not callable(factory):
        raise RuntimeError("creator workflows are not configured")
    return factory()


def get_character_media_workflows(request: Request) -> CharacterMediaWorkflows:
    factory = getattr(request.app.state, "character_media_workflows", None)
    if not callable(factory):
        raise RuntimeError("character media workflows are not configured")
    return factory()


def get_image_generation_workflows(request: Request) -> CharacterImageGenerationWorkflows:
    factory = getattr(request.app.state, "image_generation_workflows", None)
    if not callable(factory):
        raise RuntimeError("image generation workflows are not configured")
    return factory()


from app.domains.identity.contracts import CharacterCredentialWorkflows


def get_character_credential_workflows(request: Request) -> CharacterCredentialWorkflows:
    factory = getattr(request.app.state, "character_credential_workflows", None)
    if not callable(factory):
        raise RuntimeError("character credential workflows are not configured")
    return factory()


from app.domains.characters import schemas
from app.api.schemas.first_greeting import AgentFirstGreetingRead
from app.domains.routines.contracts.activity_management import ActivityManagementReferences
from app.domains.routines.contracts.autonomy_management import AutonomyWorkflows
from app.domains.routines.contracts.manual_activity import ManualActivityWorkflows
from app.domains.routines.contracts.feed_cues import FeedCueWorkflows
from app.domains.routines.contracts.first_greeting import FirstGreetingWorkflows
from app.domains.routines.contracts.tendency_analysis import TendencyAnalysisRunner


def get_activity_management_references(request: Request) -> ActivityManagementReferences:
    factory = getattr(request.app.state, "activity_management_references", None)
    if not callable(factory):
        raise RuntimeError("activity management references are not configured")
    return factory()


def get_autonomy_workflows(request: Request) -> AutonomyWorkflows[schemas.AgentDetailRead]:
    factory = getattr(request.app.state, "autonomy_workflows", None)
    if not callable(factory):
        raise RuntimeError("autonomy workflows are not configured")
    return factory()


def get_manual_activity_workflows(request: Request) -> ManualActivityWorkflows:
    factory = getattr(request.app.state, "manual_activity_workflows", None)
    if not callable(factory):
        raise RuntimeError("manual activity workflows are not configured")
    return factory()


def get_feed_cue_workflows(request: Request) -> FeedCueWorkflows:
    factory = getattr(request.app.state, "feed_cue_workflows", None)
    if not callable(factory):
        raise RuntimeError("feed cue workflows are not configured")
    return factory()


def get_first_greeting_workflows(request: Request) -> FirstGreetingWorkflows[AgentFirstGreetingRead]:
    factory = getattr(request.app.state, "first_greeting_workflows", None)
    if not callable(factory):
        raise RuntimeError("first greeting workflows are not configured")
    return factory()


def get_tendency_analysis_runner(request: Request) -> TendencyAnalysisRunner[schemas.AgentDetailRead]:
    factory = getattr(request.app.state, "tendency_analysis_runner", None)
    if not callable(factory):
        raise RuntimeError("tendency analysis runner are not configured")
    return factory()
