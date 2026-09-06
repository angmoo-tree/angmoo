"""Register the actual domain ORM classes without creating an engine or app."""
from sqlalchemy import MetaData
from app.models import Base


def register_models() -> MetaData:
    """Load each owner once through Python imports and return the one metadata."""
    import app.domains.character_lore.models  # noqa: F401 - explicit ORM registration
    import app.domains.characters.models  # noqa: F401 - explicit ORM registration
    import app.domains.chat.models  # noqa: F401 - explicit ORM registration
    import app.domains.identity.models  # noqa: F401 - explicit ORM registration
    import app.domains.local_bot.models  # noqa: F401 - explicit ORM registration
    import app.domains.memory.models.batch  # noqa: F401 - explicit ORM registration
    import app.domains.memory.models.daypart  # noqa: F401 - explicit ORM registration
    import app.domains.memory.models.items  # noqa: F401 - explicit ORM registration
    import app.domains.operations.models  # noqa: F401 - explicit ORM registration
    import app.domains.relationships.models.points  # noqa: F401 - explicit ORM registration
    import app.domains.relationships.models.projection  # noqa: F401 - explicit ORM registration
    import app.domains.relationships.models.social  # noqa: F401 - explicit ORM registration
    import app.domains.routines.models.plans  # noqa: F401 - explicit ORM registration
    import app.domains.routines.models.resident  # noqa: F401 - explicit ORM registration
    import app.domains.runtime.models  # noqa: F401 - explicit ORM registration
    import app.domains.social.models.feed  # noqa: F401 - explicit ORM registration
    import app.domains.social.models.manual_writes  # noqa: F401 - explicit ORM registration
    import app.domains.social.models.posts  # noqa: F401 - explicit ORM registration
    import app.domains.social.models.subjective_context  # noqa: F401 - explicit ORM registration
    import app.domains.tree.models  # noqa: F401 - explicit ORM registration
    import app.domains.world_characters.models  # noqa: F401 - explicit ORM registration
    import app.domains.world_packages.models  # noqa: F401 - explicit ORM registration
    import app.domains.worlds.models  # noqa: F401 - explicit ORM registration

    return Base.metadata
