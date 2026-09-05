"""Compatibility alias for WorldCharacter setup API schemas."""

import sys

from app.domains.world_characters.schemas import setup as _implementation

sys.modules[__name__] = _implementation
