from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from app.providers.contracts import ProviderCapabilities
from app.providers.gemini import GeminiAdapter


AGENT_GOOGLE_MODELS = (
    "gemma-4-26b-a4b-it",
    "gemini-3.1-flash-lite",
    "gemma-4-31b-it",
)
MESSAGE_GOOGLE_MODELS = (
    "gemini-2.5-flash-lite",
    "gemini-2.5-flash",
    "gemini-3.1-flash-lite",
    "gemma-4-26b-a4b-it",
    "gemma-4-31b-it",
)
EMBEDDING_GOOGLE_MODELS = ("gemini-embedding-2",)
GoogleProviderName = Literal["google", "google-generative-ai", "gemini"]


@dataclass(frozen=True)
class ProviderModelSpec:
    provider: str
    model: str
    capabilities: ProviderCapabilities


_GENERATIVE_CAPABILITIES = ProviderCapabilities(
    text=True,
    structured_json=True,
    image_input=True,
)
_EMBEDDING_CAPABILITIES = ProviderCapabilities(embedding=True)
_MODEL_SPECS = {
    **{
        model: ProviderModelSpec("google", model, _GENERATIVE_CAPABILITIES)
        for model in dict.fromkeys((*AGENT_GOOGLE_MODELS, *MESSAGE_GOOGLE_MODELS))
    },
    **{
        model: ProviderModelSpec("google", model, _EMBEDDING_CAPABILITIES)
        for model in EMBEDDING_GOOGLE_MODELS
    },
}
_GEMINI_ADAPTER = GeminiAdapter()


def normalize_provider_name(provider: str) -> str:
    normalized = provider.strip().lower()
    if normalized in {"google", "google-generative-ai", "gemini"}:
        return "google"
    raise ValueError(f"unsupported provider: {provider}")


def get_model_spec(provider: str, model: str) -> ProviderModelSpec:
    normalized_provider = normalize_provider_name(provider)
    spec = _MODEL_SPECS.get(model)
    if spec is None or spec.provider != normalized_provider:
        raise ValueError(f"unsupported provider model: {normalized_provider}/{model}")
    return spec


def get_provider_adapter(provider: str, model: str) -> GeminiAdapter:
    spec = get_model_spec(provider, model)
    if not spec.capabilities.text:
        raise ValueError(f"model does not support text generation: {model}")
    return _GEMINI_ADAPTER


def get_embedding_adapter(provider: str, model: str) -> GeminiAdapter:
    spec = get_model_spec(provider, model)
    if not spec.capabilities.embedding:
        raise ValueError(f"model does not support embeddings: {model}")
    return _GEMINI_ADAPTER
