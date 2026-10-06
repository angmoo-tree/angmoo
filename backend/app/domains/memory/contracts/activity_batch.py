"""Versioned activity admission and lossless source identity for batch32.

These limits apply only to newly admitted work. The episode-selection.v1
constants and parsers remain the recovery contract for already accepted jobs.
"""
from dataclasses import dataclass
from hashlib import sha256

from app.domains.memory.exceptions import MemoryValidationError

ACTIVITY_POLICY_VERSION = "episode-activity-batch32.v1"
ACTIVITY_INPUT_VERSION = "episode-input.v2"
ACTIVITY_WORK_VERSION = "episode-work.v2"
MAX_ACTIVITIES = 32
MAX_ACTIVITY_CHAT_TURNS = 30
MAX_ACTIVITY_CONTEXT_TURNS = 5
MAX_CHAT_EXCERPT = 500
CHAT_HEAD = 350
CHAT_TAIL = 150
MAX_ACTIVITY_MEMORY_CHARACTERS = 1000
MAX_ACTIVITY_MEMORIES = 32
MAX_ACTIVITY_PRIORS = 8
MAX_ACTIVITY_ATTEMPTS = 3
MAX_ACTIVITY_INPUT_TOKENS = 800_000
MAX_ACTIVITY_OUTPUT_TOKENS = 65_536


@dataclass(frozen=True, slots=True)
class SourceExcerpt:
    text: str
    segments: tuple[tuple[int, int], ...]
    total_characters: int
    omitted_characters: int
    whole_hash: str
    policy: str = "chat-head350-tail150.v1"


def chat_excerpt(raw: str) -> SourceExcerpt:
    """Count Python Unicode code points, without stripping or rewriting raw."""
    count = len(raw)
    segments = ((0, count),) if count <= MAX_CHAT_EXCERPT else (
        (0, CHAT_HEAD), (count - CHAT_TAIL, count),
    )
    return SourceExcerpt("".join(raw[start:end] for start, end in segments),
        segments, count, max(0, count - MAX_CHAT_EXCERPT), sha256(raw.encode("utf-8")).hexdigest())


@dataclass(frozen=True, slots=True)
class MemoryActivity:
    activity_id: str
    kind: str
    unit_keys: tuple[str, ...]
    context_keys: tuple[str, ...] = ()
    thread_id: str | None = None

    def __post_init__(self):
        if not self.activity_id or self.kind not in {"chat", "sns"} or not self.unit_keys:
            raise MemoryValidationError("episode_activity_invalid")
        if len(set(self.unit_keys)) != len(self.unit_keys) or len(set(self.context_keys)) != len(self.context_keys):
            raise MemoryValidationError("episode_activity_duplicate")
        if self.kind == "chat":
            if not self.thread_id or len(self.unit_keys) > MAX_ACTIVITY_CHAT_TURNS or len(self.context_keys) > MAX_ACTIVITY_CONTEXT_TURNS:
                raise MemoryValidationError("episode_chat_activity_limit")
        elif self.thread_id or len(self.unit_keys) != 1 or self.context_keys:
            raise MemoryValidationError("episode_sns_activity_invalid")


def private_thread_intersection(thread_ids: tuple[str | None, ...]) -> str | None:
    """Public input imposes no extra restriction; private inputs intersect.

An intersection of two distinct private audiences is empty, never their union.
The caller must include *all* input sources and priors, including skipped refs.
"""
    private = {value for value in thread_ids if value is not None}
    if len(private) > 1 or "" in private:
        raise MemoryValidationError("episode_private_intersection_empty")
    return next(iter(private), None)
