import asyncio
from types import SimpleNamespace

import pytest

from app.domains.identity.contracts import CredentialMaterial, CredentialPurpose
from app.domains.memory.contracts.episode import EpisodeBundle
from app.domains.memory.exceptions import MemoryValidationError
from app.integrations.llm import episode_selection as module
from app.providers.contracts import ProviderResponse, ProviderUsage
from memory.test_episode_contracts import unit


@pytest.mark.parametrize("case", ["valid", "bad_ref", "truncated", "split", "credential_changed"])
def test_episode_single_physical_call_and_untrusted_result(monkeypatch, case):
    bundle = EpisodeBundle("B1", unit(1).scope, (unit(1), unit(2)))
    payload = {"bundle_ref": "B1", "episodes": [{"summary": "9월 13일 공연은 취소됐다.",
                "source_refs": ["S1", "S2"], "follows_episode_refs": []}],
                "skipped_new_refs": [], "needs_split": False}
    if case == "bad_ref":
        payload["episodes"][0]["source_refs"] = ["S1", "S999"]
    if case == "split":
        payload.update(episodes=[], needs_split=True)
    calls, validations = [], []
    async def generate(request):
        calls.append(request)
        return ProviderResponse("", payload, ProviderUsage(input_tokens=100, output_tokens=40),
            finish_reason="MAX_TOKENS" if case == "truncated" else "STOP")
    def validate():
        validations.append(True)
        if case == "credential_changed" and len(validations) == 2:
            raise MemoryValidationError("credential_changed")
    monkeypatch.setattr(module, "get_provider_adapter", lambda *_: SimpleNamespace(generate_json=generate))
    material = CredentialMaterial(credential_id="test", provider="google", model="gemini-3.1-flash-lite",
        purpose=CredentialPurpose.MESSAGE_LLM, fingerprint="test", _secret="fake")
    provider = module.DirectLlmEpisodeSelectionProvider(material, validate_credential=validate)
    if case in {"bad_ref", "truncated", "credential_changed"}:
        with pytest.raises(MemoryValidationError):
            asyncio.run(provider.select(bundle, timeout=10))
    else:
        result = asyncio.run(provider.select(bundle, timeout=10))
        assert result.needs_split == (case == "split")
    assert len(calls) == provider.physical_calls == 1
    assert len(validations) == 2
    assert calls[0].max_output_tokens == 8192
    assert calls[0].sdk_attempts == 1
    assert calls[0].thinking_level == "high"
    assert provider.usage.input_tokens == 100
    assert "message-1" not in calls[0].user_prompt


def test_episode_input_budget_rejects_before_provider_or_credentials(monkeypatch):
    bundle = EpisodeBundle("B1", unit(1).scope, (unit(1, "가" * 25000),))
    def unexpected(*args, **kwargs): raise AssertionError("provider was called")
    monkeypatch.setattr(module, "get_provider_adapter", unexpected)
    material = CredentialMaterial(credential_id="test", provider="google", model="gemini-3.1-flash-lite",
        purpose=CredentialPurpose.MESSAGE_LLM, fingerprint="test", _secret="fake")
    provider = module.DirectLlmEpisodeSelectionProvider(material, validate_credential=unexpected)
    with pytest.raises(MemoryValidationError, match="input_budget"):
        asyncio.run(provider.select(bundle, timeout=10))
    assert provider.physical_calls == 0
