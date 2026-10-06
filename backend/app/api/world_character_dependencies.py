"""HTTP composition shared by WC and its current API consumers."""
from app.runtime.world_characters.composition import (
    public_profile_service, studio_service, lifecycle_service, leave_service,
)


def entry_created_workflow():
    from app.runtime.world_characters.creation_configuration import initialize_entered_world_character
    return initialize_entered_world_character
