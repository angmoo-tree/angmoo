"""Composition of private owner journals with World erasure."""
from app.config import settings
from app.core.result_journal import ResultJournal


def result_journal(namespace, *, media_root=None):
    return ResultJournal((media_root or settings.media_root_path) / "private-result-journals", namespace)


def close_world_results(world_id, *, media_root=None):
    for namespace in ("relationship-review", "relationship-review-rejected", "memory-embedding"):
        result_journal(namespace, media_root=media_root).close_world(world_id)
