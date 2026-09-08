"""Normalized Unicode persona admission shared through Characters contracts."""
import unicodedata

PERSONA_LIMITS = {
    "one_liner": 500,
    "personality": 6000,
    "speech_style": 4000,
    "worldview": 8000,
    "topic_preferences": 3000,
    "safety_rules": 4000,
}
PERSONA_SUMMARY_LIMIT = 32000


def normalize_persona_text(value: str) -> str:
    return unicodedata.normalize("NFC", value.replace("\r\n", "\n").replace("\r", "\n"))
