"""Canonical response-model binding policy for Chat threads."""

from enum import StrEnum


class MessageModelBindingMode(StrEnum):
    """Describe whether a thread follows the owner default or pins a model."""

    DEFAULT = "default"
    THREAD_OVERRIDE = "thread_override"


MESSAGE_MODEL_BINDING_MODES = tuple(mode.value for mode in MessageModelBindingMode)


__all__ = ["MESSAGE_MODEL_BINDING_MODES", "MessageModelBindingMode"]
