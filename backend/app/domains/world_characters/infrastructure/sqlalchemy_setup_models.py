"""Exact model compatibility for the immutable SQLite v2->v3 migration."""

from app.domains.world_characters.models import (
    WorldCommunityProfile,
    WorldActivityRepertoire,
    WorldActivityCandidate,
    WorldCharacterSetupAttempt,
)

__all__ = ['WorldCommunityProfile', 'WorldActivityRepertoire', 'WorldActivityCandidate', 'WorldCharacterSetupAttempt']
