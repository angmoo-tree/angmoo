"""Compose Tree's foreign references without querying or creating a Session."""

from sqlalchemy.sql.elements import ColumnElement
from app.domains.characters.service.profile import get_character
from app.domains.identity.models import User
from app.domains.tree.contracts import TreeReferences
from app.domains.tree.models import TreePost


def _author_name_matches(pattern: str) -> ColumnElement[bool]:
    return TreePost.author.has(User.display_name.ilike(pattern))


def build_tree_references() -> TreeReferences:
    return TreeReferences(
        get_character=get_character, author_name_matches=_author_name_matches
    )
