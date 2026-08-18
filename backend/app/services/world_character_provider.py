"""Compatibility alias for the direct-LLM WorldCharacter setup adapter."""

import sys

from app.domains.world_characters.infrastructure import (
    direct_llm_setup_provider as _implementation,
)

sys.modules[__name__] = _implementation
