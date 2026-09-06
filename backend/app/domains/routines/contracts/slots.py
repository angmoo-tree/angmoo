"""Foreign reads needed by the existing SQL-owning slot workflows."""
from __future__ import annotations
from datetime import datetime
from typing import Protocol
from sqlalchemy.sql.elements import ColumnElement


class SlotCharacterRead(Protocol):
    @property
    def deleted_at(self) -> datetime | None: ...
    @property
    def moderation_status(self) -> str: ...


class SlotReferences(Protocol):
    def lock_character_id(self, character_id: str) -> str | None: ...
    def owner_controlled_predicate(self) -> ColumnElement[bool]: ...
    def get_character(self, character_id: str) -> SlotCharacterRead | None: ...
