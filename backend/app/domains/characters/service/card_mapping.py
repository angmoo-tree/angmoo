"""Map supported card fields into editable Character fields; raw is never a prompt."""
from __future__ import annotations

import re
from dataclasses import dataclass

from app.domains.characters.policies.persona import PERSONA_LIMITS
from app.integrations.character_cards.parser import ParsedCard

_DYNAMIC = re.compile(r"\{\{[^{}]*\}\}|<(?:char|bot|user)>", re.IGNORECASE)
_RAW_ONLY = ("first_mes", "alternate_greetings", "character_book", "system_prompt",
             "post_history_instructions", "extensions", "assets", "creator_notes", "tags")


@dataclass(frozen=True)
class CardMapping:
    fields: dict[str, str]
    review: tuple[str, ...]
    raw_only: tuple[str, ...]


def map_card(card: ParsedCard) -> CardMapping:
    data = card.data
    name = data["name"].strip()
    nickname = data.get("nickname") if card.version == 3 else None
    replacement = nickname.strip() if isinstance(nickname, str) and nickname.strip() else name

    def replace(value: str, *, dialogue: bool = False) -> str:
        result = value.replace("{{char}}", replacement)
        if card.version == 3:
            result = result.replace("<char>", replacement).replace("<bot>", replacement)
        if dialogue:
            result = result.replace("{{user}}", "대화 상대")
        return result

    fields = {
        "name": name,
        "personality": replace(data["personality"]),
        "worldview": replace(data["description"]),
        "speech_style": replace(data["mes_example"], dialogue=True),
        "one_liner": "",
        "topic_preferences": "",
        "safety_rules": "",
    }
    review = []
    if not fields["worldview"].strip():
        review.append("description_required_review")
    if data["scenario"].strip():
        review.append("scenario_manual_merge")
    for field, value in fields.items():
        if len(value) > ({"name": 80} | PERSONA_LIMITS).get(field, 8000):
            # Keep the full value visible for editing; never silently truncate.
            review.append(f"{field}_length_limit")
        if _DYNAMIC.search(value):
            review.append(f"{field}_dynamic_text_review")
    if card.version == 3:
        review.append("v3_common_fields_only")
    return CardMapping(fields, tuple(review), tuple(key for key in _RAW_ONLY if data.get(key)))
