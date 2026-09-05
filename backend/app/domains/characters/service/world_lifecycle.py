"""Character status changes participating in a selected-World leave command."""
from app.domains.characters.models import Character


def deactivate_for_world_leave(character: Character) -> None:
    """The WC transaction owns flush/commit/rollback of this attached object."""
    character.status = "inactive"
