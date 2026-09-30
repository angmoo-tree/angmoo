import pytest
from pydantic import ValidationError
from app.domains.media.generation_contracts import (
    MODEL_CATALOG, ApiImageOptions, NovelOptions, ImagePreparationError,
    compose_positive, initial_reference,
)


@pytest.mark.parametrize("style,appearance,expected", [
    ("", "", "walking in a park"), ("ink", "", "ink, walking in a park"),
    ("", "green hair", "green hair, walking in a park"),
    ("ink", "green hair", "ink, green hair, walking in a park"),
])
def test_optional_identity(style, appearance, expected):
    assert compose_positive(style=style, appearance=appearance, scene="walking in a park") == expected


def test_scene_required_and_no_provider_option_leak():
    with pytest.raises(ImagePreparationError):
        compose_positive(style="ink", appearance="hair", scene=" ")
    with pytest.raises(ValidationError):
        ApiImageOptions.model_validate({"steps": 28})


def test_reference_initialization_does_not_enable_generation():
    assert len(MODEL_CATALOG) == 7
    assert sum(initial_reference(p, m, mode="allow_anlas") for p, m, _ in MODEL_CATALOG.values()) == 6
    assert not initial_reference("novelai", "nai-diffusion-4-5-full", mode="opus_free")
    assert not initial_reference("comfyui", "custom")
    assert initial_reference("comfyui", "custom", reference_validated=True)


@pytest.mark.parametrize("values", [{"steps":29}, {"width":1088}, {"n":2}, {"scale":"5"}])
def test_free_request_bounds_and_strict_types(values):
    with pytest.raises(ValidationError):
        NovelOptions.model_validate(values)
