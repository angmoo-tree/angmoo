"""Compatibility alias for the canonical prompt-safety policy."""

import sys

from app.core import prompt_safety as _implementation

sys.modules[__name__] = _implementation

