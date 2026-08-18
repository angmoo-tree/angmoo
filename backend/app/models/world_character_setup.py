"""Compatibility alias for WorldCharacter setup persistence."""

import sys

from app.domains.world_characters.infrastructure import (
    sqlalchemy_setup_models as _implementation,
)

sys.modules[__name__] = _implementation
