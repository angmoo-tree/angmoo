"""Compatibility alias for the canonical routine-post runtime module."""

from __future__ import annotations

import sys

from app.runtime.routine_posts import sqlalchemy_runtime as _implementation


sys.modules[__name__] = _implementation
