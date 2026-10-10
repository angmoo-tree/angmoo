"""Project a final SNS draft into the representation owned by Social storage."""
from .text import sanitize_visible_post_body, sanitize_visible_post_title

NORMALIZATION_REVISION = "social-visible-text.v1"


def stored_output(raw: dict) -> dict:
    if raw.get("action") not in {"post", "reply", "like"}:
        raise ValueError("situation_expected_action_invalid")
    result = dict(raw)
    fields = ("title", "body") if raw["action"] == "post" else (("body",) if raw["action"] == "reply" else ())
    for field in fields:
        if not isinstance(raw.get(field), str):
            raise ValueError("situation_expected_text_invalid")
        result[field] = (sanitize_visible_post_title if field == "title" else sanitize_visible_post_body)(raw[field])
    return result
