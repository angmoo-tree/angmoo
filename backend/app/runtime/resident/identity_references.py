"""Same-Session owner reads, preserving nullable rows and original error identity."""
from collections.abc import Callable

from sqlalchemy.orm import Session

from app.domains.characters.models import Character
from app.domains.characters.service.profile import get_character
from app.domains.identity.models import LlmCredential
from app.domains.social.exceptions import CharacterNotFoundError


class SqlAlchemyRunIdentityReferences:
    def __init__(self, db: Session, *, credential_lookup: Callable[[Session, str], LlmCredential | None]) -> None:
        self.db = db
        self._credential_lookup = credential_lookup

    def get_character(self, character_id: str) -> Character | None:
        return get_character(self.db, character_id)

    def get_credential(self, credential_id: str) -> LlmCredential | None:
        return self._credential_lookup(self.db, credential_id)

    def character_not_found(self, character_id: str) -> CharacterNotFoundError:
        return CharacterNotFoundError(character_id)
