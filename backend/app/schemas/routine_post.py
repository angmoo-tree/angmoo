"""Compatibility alias for the canonical routine-post schema module."""

from __future__ import annotations

import sys

from app.domains.routine_posts.api import schemas as _implementation


sys.modules[__name__] = _implementation
