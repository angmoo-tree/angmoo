"""Attached actor views and caller-composed foreign lookup/search contracts."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement


class TreeAuthor(Protocol):
    id: str
    display_name: str


class TreeCharacter(Protocol):
    id: str
    owner_id: str
    deleted_at: datetime | None
    name: str
    handle: str
    avatar_url: str | None


@dataclass(frozen=True)
class TreeReferences:
    """Lookup stays in the caller Session; search returns the original SQL predicate."""

    get_character: Callable[[Session, str], TreeCharacter | None]
    author_name_matches: Callable[[str], ColumnElement[bool]]
