"""Bounded, deterministic list composition; quota is separate from relevance."""
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
import hashlib


@dataclass(frozen=True)
class Candidate:
    id: str
    author_id: str
    created_at: datetime
    interest: float
    relation: float
    sources: frozenset[str]
    novelty: float = 1.0


def compose(candidates: list[Candidate], *, now: datetime, seed: str) -> list[tuple[Candidate, str]]:
    selected: list[tuple[Candidate, str]] = []
    seen: set[str] = set()
    authors: Counter = Counter()
    recent = sorted(candidates, key=lambda c: (-c.created_at.timestamp(), c.id))

    def score(c):
        age = max(0, now.timestamp() - c.created_at.timestamp())
        recency = 1 / (1 + age / 86400)
        noise = int(hashlib.sha256((seed + c.id).encode()).hexdigest()[:8], 16) / 0xffffffff
        return .45 * c.interest + .25 * c.relation + .20 * recency + .10 * c.novelty + .001 * noise

    ranked = sorted(candidates, key=lambda c: (-score(c), c.id))

    def add(lane, count, *, author_limit=True):
        added = 0
        for candidate in recent if lane == "latest" else ranked:
            if lane not in candidate.sources or candidate.id in seen:
                continue
            if author_limit and authors[candidate.author_id] >= 2:
                continue
            selected.append((candidate, lane))
            seen.add(candidate.id)
            authors[candidate.author_id] += 1
            added += 1
            if added >= count or len(selected) >= 20:
                break

    add("latest", 10, author_limit=False)
    for lane, count in (("interest", 5), ("relation", 3), ("explore", 2)):
        add(lane, count)
    for lane in ("interest", "relation", "explore", "latest"):
        if len(selected) < 20:
            add(lane, 20 - len(selected))
    return selected
