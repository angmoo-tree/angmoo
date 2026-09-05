"""Bind canonical WC services to joined reads in the same caller Session."""
from app.domains.world_characters.service.public_profile import WorldCharacterProfileService
from app.domains.world_characters.service.studio import WorldCharacterStudioService
from app.domains.world_characters.service.lifecycle import WorldCharacterLifecycleService
from app.runtime.world_characters.queries import SqlAlchemyWorldCharacterQueries


def public_profile_service(db):
    return WorldCharacterProfileService(db, queries=SqlAlchemyWorldCharacterQueries())


def studio_service(db):
    return WorldCharacterStudioService(db, queries=SqlAlchemyWorldCharacterQueries())


def lifecycle_service(db, *, runtime_guard=None):
    return WorldCharacterLifecycleService(
        db, queries=SqlAlchemyWorldCharacterQueries(), runtime_guard=runtime_guard,
    )
