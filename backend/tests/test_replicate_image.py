from app.services import replicate_image


def test_p_image_edit_posts_reference_payload_and_downloads_output(monkeypatch) -> None:
    calls: list[tuple[str, str, dict[str, object] | None]] = []

    def fake_request_json(
        *,
        method: str,
        url: str,
        api_key: str,
        payload: dict[str, object] | None,
        timeout_seconds: float,
    ) -> dict[str, object]:
        del api_key, timeout_seconds
        calls.append((method, url, payload))
        if method == "POST":
            return {
                "id": "prediction-1",
                "urls": {"get": "https://api.replicate.com/v1/predictions/prediction-1"},
            }
        return {"id": "prediction-1", "status": "succeeded", "output": "https://cdn.example/image.png"}

    monkeypatch.setattr(replicate_image, "_request_json", fake_request_json)
    monkeypatch.setattr(
        replicate_image,
        "_download_image",
        lambda _url, *, timeout_seconds: ("image/png", b"png-bytes"),
    )

    result = replicate_image._generate_p_image_edit_sync(
        "replicate-token",
        "[Modification] Change the setting.",
        "https://angmoo.com/media/seed.webp",
        42,
        5,
    )

    assert result.content_type == "image/png"
    assert result.content == b"png-bytes"
    assert calls[0][0] == "POST"
    assert calls[0][1] == replicate_image.REPLICATE_P_IMAGE_EDIT_PREDICTIONS_URL
    assert calls[0][2] == {
        "input": {
            "prompt": "[Modification] Change the setting.",
            "images": ["https://angmoo.com/media/seed.webp"],
            "turbo": True,
            "aspect_ratio": "match_input_image",
            "seed": 42,
            "disable_safety_checker": False,
            "no_op": False,
        }
    }


def test_p_image_edit_requires_reference_in_provider(monkeypatch) -> None:
    import asyncio

    from app.core.image_generation import REPLICATE_IMAGE_MODEL_PRUNA_EDIT
    from app.services import image_provider

    called = False

    async def fail_if_called(**_kwargs):
        nonlocal called
        called = True
        raise AssertionError("provider must not be called without a reference")

    monkeypatch.setattr(replicate_image, "generate_p_image_edit", fail_if_called)

    try:
        asyncio.run(
            image_provider.generate_image(
                api_key="replicate-token",
                model=REPLICATE_IMAGE_MODEL_PRUNA_EDIT,
                prompt="edit",
            )
        )
    except replicate_image.ReplicateImageError as exc:
        assert exc.failure_class == "reference_required"
    else:
        raise AssertionError("missing reference should fail")

    assert called is False
