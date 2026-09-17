"""One physical request for a bounded episode bundle, without a second selector."""

from collections.abc import Callable
import json

from app.domains.identity.contracts import CredentialMaterial, CredentialPurpose
from app.domains.memory.contracts.episode import EpisodeBundle, MAX_EPISODE_OUTPUT_TOKENS
from app.domains.memory.exceptions import MemoryValidationError
from app.domains.memory.policies.episode_prompt import EPISODE_PROMPT, episode_prompt_payload
from app.domains.memory.policies.episode_selection import parse_episode_selection
from app.providers.contracts import ProviderRequest
from app.providers.generation_profiles import validate_generation_profile
from app.providers.gemini import classify_generation_failure
from app.providers.registry import get_provider_adapter


class DirectLlmEpisodeSelectionProvider:
    def __init__(self, material: CredentialMaterial, *, validate_credential: Callable[[], None] | None = None):
        if material.purpose is not CredentialPurpose.MESSAGE_LLM:
            raise MemoryValidationError("episode_credential_purpose_invalid")
        self.phase_observer = None
        self.material = material
        self.validate_credential = validate_credential
        self.usage = None
        self.finish_reason = None
        self.physical_calls = 0
        self.provider_code = None
        self.provider_status = None
        self.retryable = False

    def validate_bundle(self, bundle: EpisodeBundle):
        return episode_prompt_payload(bundle)

    async def select(self, bundle: EpisodeBundle, *, timeout: float):
        self.usage = None
        self.finish_reason = None
        self.physical_calls = 0
        self.provider_code = None
        self.provider_status = None
        self.retryable = False
        prompt, schema = self.validate_bundle(bundle)
        validate_generation_profile(self.material.model, self.material.thinking_level)
        if self.validate_credential:
            self.validate_credential()
        adapter = get_provider_adapter(self.material.provider, self.material.model)
        request = ProviderRequest(
            api_key=self.material.reveal(), model=self.material.model,
            system_prompt=EPISODE_PROMPT, user_prompt=prompt,
            max_output_tokens=MAX_EPISODE_OUTPUT_TOKENS, timeout_seconds=timeout,
            response_schema=schema, response_mime_type="application/json",
            thinking_level=self.material.thinking_level, sdk_attempts=1,
        )
        try:
            if self.phase_observer:
                self.phase_observer("ai_running")
            self.physical_calls = 1
            response = await adapter.generate_json(request)
        except Exception as exc:
            failure = classify_generation_failure(exc)
            self.provider_code = failure.provider_code
            self.provider_status = failure.provider_status
            self.retryable = failure.retryable
            raise MemoryValidationError(f"episode_{failure.failure_class}") from None
        finally:
            if self.phase_observer:
                self.phase_observer("applying")
        self.usage = response.usage
        self.finish_reason = response.finish_reason
        if self.validate_credential:
            self.validate_credential()
        if response.finish_reason == "MAX_TOKENS":
            raise MemoryValidationError("episode_max_tokens")
        if response.finish_reason not in {None, "STOP"}:
            raise MemoryValidationError("episode_output_incomplete")
        try:
            payload = response.parsed if isinstance(response.parsed, dict) else json.loads(response.text)
        except (ValueError, TypeError):
            raise MemoryValidationError("episode_output_invalid") from None
        return parse_episode_selection(payload, bundle)
