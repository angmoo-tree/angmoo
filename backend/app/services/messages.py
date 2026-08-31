"""Compatibility alias for the canonical Chat v1 runtime implementation."""

import sys

from app.runtime.chat import sqlalchemy_service as _implementation

sys.modules[__name__] = _implementation
