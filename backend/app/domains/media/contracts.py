"""Managed-media validation failure shared by storage and HTTP consumers."""

GENERATED_ASSET_MAX_BYTES = 24 * 1024 * 1024


class InvalidProfileMediaError(Exception):
    pass


# Supported immutable generation input contracts for other domains.
from .generation_contracts import (MODEL_CATALOG, NovelOptions, ApiImageOptions, ComfyOptions,
    ImagePreparationError, ImageSubmissionError, initial_reference)
from .api_image_policy import validate_api_options
