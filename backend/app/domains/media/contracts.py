"""Managed-media validation failure shared by storage and HTTP consumers."""


class InvalidProfileMediaError(Exception):
    pass


# Supported immutable generation input contracts for other domains.
from .generation_contracts import (MODEL_CATALOG, NovelOptions, ApiImageOptions, ComfyOptions,
    ImagePreparationError, ImageSubmissionError, initial_reference)
