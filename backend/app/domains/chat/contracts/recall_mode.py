"""Coherent request capabilities; runtime defaults to social hybrid."""
from enum import StrEnum
import hashlib


class ChatRecallMode(StrEnum):
    LEGACY = "legacy_checkpoint"
    SOCIAL_BASELINE = "social_context_baseline"
    SOCIAL_HYBRID = "social_hybrid"

    @property
    def graph_tools_enabled(self):
        return self is ChatRecallMode.LEGACY

    @property
    def fingerprint(self):
        return hashlib.sha256(("chat-recall.v1:" + self.value).encode()).hexdigest()
