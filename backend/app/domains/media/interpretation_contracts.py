"""Analysis is observed evidence; embedded image text remains untrusted data."""
import json
from typing import Any
from pydantic import BaseModel, Field, ConfigDict, ValidationError


class ImageAnalysis(BaseModel):
    model_config = ConfigDict(extra="ignore")
    description: str = Field(min_length=1, max_length=2000)
    visible_text: list[str] = Field(default_factory=list, max_length=16)
    uncertainties: list[str] = Field(default_factory=list, max_length=8)
    recall_hint: str | None = Field(default=None, max_length=120)


def parse_analysis(raw: str | dict[str, Any]) -> ImageAnalysis:
    payload = json.loads(raw) if isinstance(raw, str) else dict(raw)
    if not isinstance(payload, dict):
        raise ValueError("image_analysis_invalid")
    hint = payload.get("recall_hint")
    # An invalid auxiliary hint never discards a useful observation or retries AI.
    if not isinstance(hint, str) or not 1 <= len(hint.strip()) <= 120:
        payload["recall_hint"] = None
    else:
        payload["recall_hint"] = hint.strip()
    description = payload.get("description")
    if not isinstance(description, str) or not description.strip():
        raise ValueError("image_description_invalid")
    if any(not isinstance(text, str) or len(text) > 500 for text in payload.get("visible_text", [])):
        raise ValueError("image_visible_text_invalid")
    if any(not isinstance(text, str) or len(text) > 300 for text in payload.get("uncertainties", [])):
        raise ValueError("image_uncertainty_invalid")
    return ImageAnalysis.model_validate(payload)
