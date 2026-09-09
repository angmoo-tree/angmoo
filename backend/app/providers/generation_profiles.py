"""Supported generation profiles; presentation labels never become API IDs."""

from typing import Literal

GenerationModel = Literal["gemini-3.5-flash-lite", "gemini-3.1-flash-lite"]
ThinkingLevel = Literal["high", "medium"]
GENERATION_MODELS = ("gemini-3.5-flash-lite", "gemini-3.1-flash-lite")
THINKING_LEVELS = ("high", "medium")
DEFAULT_GENERATION_MODEL = "gemini-3.1-flash-lite"
DEFAULT_THINKING_LEVEL = "high"


def validate_generation_profile(model: str, thinking_level: str) -> None:
    if model not in GENERATION_MODELS or thinking_level not in THINKING_LEVELS:
        raise ValueError("generation_profile_unsupported")
