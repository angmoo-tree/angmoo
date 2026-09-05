"""Bounds shared by Social page requests."""


def _safe_limit(limit: int) -> int:
    return max(1, min(limit, 100))
