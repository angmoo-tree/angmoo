"""Social model-specific reference-image eligibility and fallback rules."""
from __future__ import annotations
from app.domains.social.contracts.image_generation import ImageReferenceLocation
from app.core.image_generation import POLLINATIONS_IMAGE_MODEL_FLUX_KLEIN, POLLINATIONS_IMAGE_MODEL_PRUNA_EDIT, REPLICATE_IMAGE_MODEL_PRUNA_EDIT


def _pollinations_reference_url(
    model: str,
    reference: ImageReferenceLocation | None,
) -> str | None:
    if not _accepts_pollinations_reference(model) or reference is None:
        return None
    return reference.public_url


def _reference_image_url(
    model: str,
    reference: ImageReferenceLocation | None,
) -> str | None:
    if reference is None:
        return None
    if model == REPLICATE_IMAGE_MODEL_PRUNA_EDIT:
        return reference.public_url
    return _pollinations_reference_url(model, reference)


def _accepts_pollinations_reference(model: str) -> bool:
    return model in {
        POLLINATIONS_IMAGE_MODEL_FLUX_KLEIN,
        POLLINATIONS_IMAGE_MODEL_PRUNA_EDIT,
    }


def _requires_pollinations_reference(model: str) -> bool:
    return model == POLLINATIONS_IMAGE_MODEL_PRUNA_EDIT


def _requires_reference(model: str) -> bool:
    return model in {
        POLLINATIONS_IMAGE_MODEL_PRUNA_EDIT,
        REPLICATE_IMAGE_MODEL_PRUNA_EDIT,
    }


def _allows_reference_fallback(model: str) -> bool:
    return model == POLLINATIONS_IMAGE_MODEL_FLUX_KLEIN
