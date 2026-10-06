"""The supported image provider paths, shared by credentials and execution."""
from typing import Literal

ImageProvider = Literal["novelai", "comfyui", "nanogpt", "openrouter"]
MODEL_CATALOG: dict[str, tuple[ImageProvider, str, bool]] = {
    "novelai:nai-diffusion-4-5-full": ("novelai", "nai-diffusion-4-5-full", True),
    "nanogpt:krea-v2/turbo": ("nanogpt", "krea-v2/turbo", True),
    "nanogpt:z-image-turbo": ("nanogpt", "z-image-turbo", False),
    "nanogpt:nano-banana-2": ("nanogpt", "nano-banana-2", True),
    "openrouter:krea/krea-2-medium-turbo": ("openrouter", "krea/krea-2-medium-turbo", True),
    "openrouter:google/gemini-3.1-flash-image": ("openrouter", "google/gemini-3.1-flash-image", True),
    "openrouter:openai/gpt-image-2.5-flare": ("openrouter", "openai/gpt-image-2.5-flare", True),
}
