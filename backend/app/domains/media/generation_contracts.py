"""Immutable, secret-free inputs shared by image services and wire adapters."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

ImageProvider = Literal["novelai", "comfyui", "nanogpt", "openrouter"]
ReferenceSource = Literal["override", "card", "profile", "none"]

MODEL_CATALOG: dict[str, tuple[ImageProvider, str, bool]] = {
    "novelai:nai-diffusion-4-5-full": ("novelai", "nai-diffusion-4-5-full", True),
    "nanogpt:krea-v2/turbo": ("nanogpt", "krea-v2/turbo", True),
    "nanogpt:z-image-turbo": ("nanogpt", "z-image-turbo", False),
    "nanogpt:nano-banana-2": ("nanogpt", "nano-banana-2", True),
    "openrouter:krea/krea-2-medium-turbo": ("openrouter", "krea/krea-2-medium-turbo", True),
    "openrouter:google/gemini-3.1-flash-image": ("openrouter", "google/gemini-3.1-flash-image", True),
    "openrouter:openai/gpt-image-2.5-flare": ("openrouter", "openai/gpt-image-2.5-flare", True),
}


class StrictInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class NovelOptions(StrictInput):
    mode: Literal["opus_free", "allow_anlas"] = "opus_free"
    width: int = Field(default=1024, ge=64, le=2048, multiple_of=64)
    height: int = Field(default=1024, ge=64, le=2048, multiple_of=64)
    steps: int = Field(default=28, ge=1, le=50)
    scale: float = Field(default=5.0, ge=0, le=10)
    sampler: Literal["k_euler", "k_euler_ancestral", "k_dpmpp_2s_ancestral", "k_dpmpp_2m", "k_dpmpp_sde", "ddim_v3"] = "k_euler_ancestral"
    noise_schedule: Literal["native", "karras", "exponential", "polyexponential"] = "karras"
    seed: int = Field(default=-1, ge=-1, le=4294967295)
    cfg_rescale: float = Field(default=0.0, ge=0, le=1)
    decrisper: bool = False
    variety_boost: bool = False
    reference_strength: float = Field(default=1.0, ge=0, le=1)
    reference_fidelity: float = Field(default=1.0, ge=0, le=1)
    reference_type: Literal["character", "style", "character&style"] = "character&style"

    @model_validator(mode="after")
    def free_bounds(self):
        if self.mode == "opus_free" and (self.steps > 28 or self.width * self.height > 1048576):
            raise ValueError("opus_free_dimensions_or_steps")
        return self


class ApiImageOptions(StrictInput):
    resolution: str | None = Field(default=None, max_length=32)
    aspect_ratio: str | None = Field(default=None, max_length=16)
    quality: str | None = Field(default=None, max_length=20)
    background: str | None = Field(default=None, max_length=16)
    output_compression: int | None = Field(default=None, ge=0, le=100)
    seed: int | None = Field(default=None, ge=0, le=4294967295)


class Binding(StrictInput):
    node_id: str = Field(min_length=1, max_length=80)
    input_name: str = Field(min_length=1, max_length=80)


class ComfyWorkflow(StrictInput):
    prompt: dict[str, dict[str, Any]]
    bindings: dict[str, Binding]
    output_node: str = Field(min_length=1, max_length=80)
    reference_required: bool = False


class ComfyOptions(StrictInput):
    base_url: str = Field(default="http://127.0.0.1:8188", max_length=500)
    workflow: ComfyWorkflow | None = None
    text_workflow: ComfyWorkflow | None = None
    values: dict[str, str | int | float] = Field(default_factory=dict)
    # Set only by the service after object_info validation, never from user input.


@dataclass(frozen=True)
class EffectiveReference:
    preferred: bool
    source: ReferenceSource = "none"
    asset_id: str | None = None
    digest: str | None = None
    reason: str | None = None
    revision: int | None = None


@dataclass(frozen=True)
class GenerationRequest:
    provider: ImageProvider
    model: str
    positive: str
    negative: str | None
    options: dict[str, Any]
    reference: EffectiveReference
    endpoint: dict[str, Any] | None = None


@dataclass(frozen=True)
class ImageResult:
    content: bytes
    content_type: str
    receipt: str | None = None
    usage: dict[str, Any] | None = None


class ImagePreparationError(ValueError):
    """A deterministic failure before any generation submission."""


class ImageSubmissionError(RuntimeError):
    def __init__(self, code: str, *, outcome_unknown: bool = False, receipt: str | None = None):
        super().__init__(code)
        self.code = code
        self.outcome_unknown = outcome_unknown
        self.receipt = receipt


def compose_positive(*, style: str, appearance: str, scene: str) -> str:
    if not scene.strip() or len(scene) > 1800:
        raise ImagePreparationError("scene_invalid")
    if len(style) > 1200 or len(appearance) > 1200:
        raise ImagePreparationError("identity_text_too_long")
    return ", ".join(part.strip() for part in (style, appearance, scene) if part.strip())


def initial_reference(provider: ImageProvider, model: str, *, mode: str = "", reference_validated: bool = False) -> bool:
    if provider == "comfyui":
        return reference_validated
    entry = MODEL_CATALOG.get(f"{provider}:{model}")
    if entry is None:
        raise ImagePreparationError("model_not_supported")
    return entry[2] and not (provider == "novelai" and mode == "opus_free")
