"""Compatibility alias for WorldCharacter setup API schemas."""

import sys

from app.domains.world_characters.api import setup_schemas as _implementation

sys.modules[__name__] = _implementation
