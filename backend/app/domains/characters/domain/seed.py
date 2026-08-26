"""Caller-owned Character seed contracts."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class AutonomousCharacterSeedData:
    owner_id: str
    display_name: str
    handle_hint: str
    one_liner: str
    personality: str
    speech_style: str
    worldview: str
    topic_preferences: tuple[str, ...]
    safety_rules: tuple[str, ...]
    persona_summary: str
    planned_handle: str | None = None
    avatar_url: str | None = None
    banner_url: str | None = None


__all__ = ["AutonomousCharacterSeedData"]
