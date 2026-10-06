"""Model input built from the actual World configuration, without a fake Character."""
from app.domains.characters.service.prompt_persona import model_persona
from app.domains.world_characters.service.configuration import effective_configuration


def world_persona(db, actor_id):
    value = effective_configuration(db, world_character_id=actor_id)
    return model_persona({**value.settings.model_dump(), "name": value.profile.display_name, "one_liner": value.profile.intro})
