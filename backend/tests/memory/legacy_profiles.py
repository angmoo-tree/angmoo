"""Explicit historical fixture, not a new-admission global profile fallback."""
from app.domains.memory.models.batch import MemoryBatchProfile


def retain_legacy_profile(repo, scope, settings):
    repo.session.merge(MemoryBatchProfile(owner_id=scope.owner_id, model_id=settings.model_id,
        thinking_level=settings.thinking_level, version=settings.profile_version))
    repo.session.flush()
