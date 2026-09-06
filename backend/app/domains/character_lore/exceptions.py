"""Lore upload, lookup, embedding, and parser admission errors."""

from dataclasses import dataclass
from app.domains.character_lore.constants import RETRY_AFTER_SECONDS


class CharacterLoreError(Exception):
    pass


class CharacterLoreNotFoundError(CharacterLoreError):
    pass


class CharacterLoreValidationError(CharacterLoreError):
    pass


class CharacterLoreFileTooLargeError(CharacterLoreValidationError):
    pass


class CharacterLoreEmbeddingError(CharacterLoreError):
    pass


class CharacterLoreParserBusyError(CharacterLoreError):
    retry_after_seconds = RETRY_AFTER_SECONDS


@dataclass(frozen=True)
class LoreParserCapacityError(Exception):
    retry_after_seconds: int = RETRY_AFTER_SECONDS


class LoreParserLeaseUnavailableError(Exception):
    pass
