"""Public context text normalization and bounded representation."""
from app.core.context_text import neutralize_context_text


def _clip(value: object, limit: int) -> str:
    return neutralize_context_text(str(value or "")).strip()[:limit]
