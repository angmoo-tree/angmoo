"""Compatibility alias for the canonical direct-LLM integration."""

import sys

from app.integrations import direct_llm as _implementation

sys.modules[__name__] = _implementation
