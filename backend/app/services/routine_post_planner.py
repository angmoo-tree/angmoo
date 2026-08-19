"""Compatibility alias for the canonical routine-post provider module."""

from __future__ import annotations

import sys

from app.domains.routine_posts.infrastructure import direct_llm_provider as _implementation


sys.modules[__name__] = _implementation
