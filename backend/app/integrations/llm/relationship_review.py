"""Single provider call for one saved-memory relationship review unit."""

import json
from app.providers.contracts import ProviderRequest
from app.domains.relationships.contracts.daily_review import ReviewNeedsSplit
from app.providers.registry import get_provider_adapter
from app.domains.relationships.policies.daily_review import REVIEW_INSTRUCTIONS, fits_input


class DirectRelationshipReviewProvider:
    def __init__(self, material, *, validate_credential):
        self.material = material
        self.validate_credential = validate_credential
        self.usage = None

    async def review(self, payload, *, partial, timeout):
        if not fits_input(payload):
            raise ValueError("relationship_review_input_exceeds_budget")
        self.validate_credential()
        properties = {"memory_refs": {"type": "array", "items": {"type": "string"}}}
        if partial:
            properties.update(findings={"type": "array", "items": {"type": "string"}}, uncertainty={"type": "string"})
        else:
            properties.update(decision={"type": "string", "enum": ["keep", "update"]},
                relationship_label={"type": "string"}, perception={"type": "string"})
        response = await get_provider_adapter(self.material.provider, self.material.model).generate_json(ProviderRequest(
            api_key=self.material.reveal(), model=self.material.model, system_prompt=REVIEW_INSTRUCTIONS,
            user_prompt=json.dumps({**payload, "phase": "partial" if partial else "final"}, ensure_ascii=False),
            max_output_tokens=8192, timeout_seconds=timeout, thinking_level=self.material.thinking_level,
            response_schema={"type": "object", "properties": properties, "required": list(properties)},
            response_mime_type="application/json", sdk_attempts=1))
        self.usage = response.usage
        self.validate_credential()
        if response.finish_reason not in {None, "STOP"}:
            raise ReviewNeedsSplit("relationship_review_output_incomplete")
        return response.parsed if isinstance(response.parsed, dict) else json.loads(response.text)
