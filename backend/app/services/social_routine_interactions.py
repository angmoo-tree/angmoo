"""Compatibility alias for the canonical routine interaction adapter."""

from __future__ import annotations

import sys

from app.compatibility.routine_posts import canonical_interactions as _implementation


sys.modules[__name__] = _implementation
