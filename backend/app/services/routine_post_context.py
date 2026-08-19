"""Compatibility alias for the canonical routine-post context module."""

from __future__ import annotations

import sys

from app.domains.routine_posts.infrastructure import sqlalchemy_context as _implementation


sys.modules[__name__] = _implementation
