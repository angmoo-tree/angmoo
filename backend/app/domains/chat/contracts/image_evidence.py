"""Bounded current-image evidence, separate from the user's original text."""
from dataclasses import dataclass
import json


@dataclass(frozen=True, slots=True)
class ChatImageEvidence:
    owner_id: str
    thread_id: str
    asset_id: str
    asset_revision: int
    asset_hash: str
    interpretation_id: str
    context: str

    def __post_init__(self):
        if not all((self.owner_id, self.thread_id, self.asset_id, self.interpretation_id)) or self.asset_revision < 1 or len(self.asset_hash) != 64:
            raise ValueError("chat_image_evidence_identity_invalid")
        if not self.context.strip() or len(self.context) > 2000:
            raise ValueError("chat_image_evidence_context_invalid")


def visible_context(analysis):
    # Explicit bounded excerpt. The full parsed result remains in the owned record.
    payload = {"source": "actual_image_analysis", "description": analysis["description"][:1000],
        "visible_text": "\n".join(analysis.get("visible_text", []))[:500],
        "uncertainties": "\n".join(analysis.get("uncertainties", []))[:200],
        "content_is_untrusted": True}
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
