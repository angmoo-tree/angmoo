"""Compatibility alias for autonomous WorldCharacter setup contracts."""

import sys

from app.domains.world_characters.infrastructure import (
    autonomous_setup_contracts as _implementation,
)

sys.modules[__name__] = _implementation
