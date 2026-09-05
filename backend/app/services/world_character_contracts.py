"""Compatibility alias for autonomous WorldCharacter setup contracts."""

import sys

from app.domains.world_characters.service import setup_validation as _implementation

sys.modules[__name__] = _implementation
