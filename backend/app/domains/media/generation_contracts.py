"""Immutable, secret-free inputs shared by image services and wire adapters."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator, model_serializer

from app.providers.image_profiles import ImageProvider, MODEL_CATALOG

ReferenceSource = Literal["override", "card", "profile", "none"]

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
    """Unversioned stored contract: explicit bindings and exactly one output."""
    prompt: dict[str, dict[str, Any]]
    bindings: dict[str, Binding]
    output_node: str = Field(min_length=1, max_length=80)
    reference_required: bool = False


class AutoImageOutput(StrictInput):
    mode: Literal["auto_first_image"] = "auto_first_image"


class ExplicitImageOutput(StrictInput):
    mode: Literal["explicit_node"]
    node_id: str = Field(min_length=1, max_length=80)


class PlaceholderWorkflow(StrictInput):
    input_mode: Literal["placeholders"]
    prompt: dict[str, dict[str, Any]]
    output: Annotated[AutoImageOutput | ExplicitImageOutput, Field(discriminator="mode")] = Field(default_factory=AutoImageOutput)


class BoundWorkflow(StrictInput):
    input_mode: Literal["node_bindings"]
    prompt: dict[str, dict[str, Any]]
    bindings: dict[str, Binding]
    output: Annotated[AutoImageOutput | ExplicitImageOutput, Field(discriminator="mode")] = Field(default_factory=AutoImageOutput)


WorkflowInput = ComfyWorkflow | Annotated[PlaceholderWorkflow | BoundWorkflow, Field(discriminator="input_mode")]


class ComfyOptions(StrictInput):
    options_schema_version: Literal[2] | None = None
    clip_skip_value_mode: Literal["skip_count", "node_value"] | None = None
    base_url: str = Field(default="http://127.0.0.1:8188", max_length=500)
    partner_auth: bool = False
    workflow: WorkflowInput | None = None
    text_workflow: WorkflowInput | None = None
    values: dict[str, str | int | float] = Field(default_factory=dict)
    @model_validator(mode="after")
    def version_contract(self):
        import math
        versioned = self.options_schema_version == 2
        for graph in (self.workflow, self.text_workflow):
            if graph is not None and versioned == isinstance(graph, ComfyWorkflow):
                raise ValueError("comfy_options_version_invalid")
        if not versioned and self.clip_skip_value_mode is not None:
            raise ValueError("comfy_options_version_invalid")
        if any(isinstance(value, float) and not math.isfinite(value) for value in self.values.values()):
            raise ValueError("comfy_value_invalid")
        return self

    @model_serializer(mode="wrap")
    def stored_options(self, handler):
        result = handler(self)
        if self.options_schema_version is None:
            result.pop("options_schema_version", None)
            result.pop("clip_skip_value_mode", None)
        else:
            result["clip_skip_value_mode"] = self.clip_skip_value_mode or "skip_count"
        return result


@dataclass(frozen=True)
class ComfyExecution:
    options_schema_version: int | None
    selected_path: Literal["workflow", "text_workflow"]
    graph_digest: str
    base_url: str
    input_mode: Literal["legacy_bindings", "placeholders", "node_bindings"]
    output: dict[str, str]
    prepared_values: dict[str, str | int | float]
    seed: int | None
    clip_skip_display: int | None
    clip_skip_value_mode: Literal["node_value", "skip_count"]
    clip_skip_actual: int | None

    def __post_init__(self):
        import math
        import re
        if (self.options_schema_version not in (None, 2)
            or self.selected_path not in ("workflow", "text_workflow")
            or self.input_mode not in ("legacy_bindings", "placeholders", "node_bindings")
            or (self.options_schema_version is None) != (self.input_mode == "legacy_bindings")
            or not isinstance(self.graph_digest, str) or not re.fullmatch(r"[a-f0-9]{64}", self.graph_digest)
            or self.clip_skip_value_mode not in ("node_value", "skip_count")
            or not isinstance(self.prepared_values, dict)
            or "reference" in self.prepared_values
            or any(type(value) not in (str, int, float) or (type(value) is float and not math.isfinite(value)) for value in self.prepared_values.values())
            or any(value is not None and type(value) is not int for value in (self.seed, self.clip_skip_display, self.clip_skip_actual))):
            raise ImagePreparationError("comfy_execution_snapshot_invalid")
        policy = self.output
        if not isinstance(policy, dict) or not (
            policy == {"mode": "auto_first_image"}
            or (policy.get("mode") in ("explicit_node", "legacy_single")
                and set(policy) == {"mode", "node_id"} and isinstance(policy["node_id"], str)
                and 0 < len(policy["node_id"]) <= 80)):
            raise ImagePreparationError("comfy_execution_snapshot_invalid")
        if self.seed != self.prepared_values.get("seed") or self.clip_skip_actual != self.prepared_values.get("clip_skip"):
            raise ImagePreparationError("comfy_execution_snapshot_invalid")


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
    partner_credential_id: str | None = None
    partner_credential_revision: int | None = None
    world_id: str | None = None
    world_character_id: str | None = None
    world_configuration_revision: int | None = None
    credential_binding: dict | None = None
    world_image_policy_revision: int | None = None
    comfy_execution: ComfyExecution | None = None


@dataclass(frozen=True)
class ImageResult:
    content: bytes
    content_type: str
    receipt: str | None = None
    usage: dict[str, Any] | None = None
    diagnostic: dict | None = None


class ImagePreparationError(ValueError):
    """A deterministic failure before any generation submission."""


class ImageSubmissionError(RuntimeError):
    def __init__(self, code: str, *, outcome_unknown: bool = False, receipt: str | None = None, stage: str | None = None, diagnostic: dict | None = None):
        super().__init__(code)
        self.code = code
        self.outcome_unknown = outcome_unknown
        self.receipt = receipt
        self.stage = stage
        self.diagnostic = diagnostic


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
