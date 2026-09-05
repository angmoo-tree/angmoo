"""Compatibility alias for the direct-LLM WorldCharacter setup adapter."""

import sys

from app.domains.world_characters import client as _implementation

sys.modules[__name__] = _implementation
