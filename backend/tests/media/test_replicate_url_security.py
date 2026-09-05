import socket
from urllib.request import Request

import pytest

from app.integrations import replicate_image


def _public_dns(_host, _port, **_kwargs):
    return [
        (
            socket.AF_INET,
            socket.SOCK_STREAM,
            socket.IPPROTO_TCP,
            "",
            ("93.184.216.34", 443),
        )
    ]


@pytest.mark.parametrize(
    "url",
    [
        "https://api.replicate.com/v1/predictions/prediction_123",
        replicate_image.REPLICATE_PREDICTIONS_URL,
        replicate_image.REPLICATE_P_IMAGE_EDIT_PREDICTIONS_URL,
    ],
)
def test_replicate_api_url_allowlist_accepts_only_documented_paths(
    monkeypatch: pytest.MonkeyPatch,
    url: str,
) -> None:
    monkeypatch.setattr(replicate_image.socket, "getaddrinfo", _public_dns)

    replicate_image._validate_replicate_url(url, purpose="api")


@pytest.mark.parametrize(
    "url",
    [
        "https://attacker.example/v1/predictions/prediction_123",
        "https://api.replicate.com.evil.example/v1/predictions/prediction_123",
        "https://user" + "@api.replicate.com/v1/predictions/prediction_123",
        "https://api.replicate.com:444/v1/predictions/prediction_123",
        "http://api.replicate.com/v1/predictions/prediction_123",
        "https://api.replicate.com/v1/models/other/predictions",
    ],
)
def test_replicate_api_url_allowlist_rejects_untrusted_destinations(
    monkeypatch: pytest.MonkeyPatch,
    url: str,
) -> None:
    monkeypatch.setattr(replicate_image.socket, "getaddrinfo", _public_dns)

    with pytest.raises(replicate_image.ReplicateImageError):
        replicate_image._validate_replicate_url(url, purpose="api")


def test_replicate_url_rejects_private_dns_results(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        replicate_image.socket,
        "getaddrinfo",
        lambda *_args, **_kwargs: [
            (
                socket.AF_INET,
                socket.SOCK_STREAM,
                socket.IPPROTO_TCP,
                "",
                ("169.254.169.254", 443),
            )
        ],
    )

    with pytest.raises(replicate_image.ReplicateImageError):
        replicate_image._validate_replicate_url(
            "https://api.replicate.com/v1/predictions/prediction_123",
            purpose="api",
        )


@pytest.mark.parametrize(
    "url",
    [
        "https://replicate.delivery/output.png",
        "https://pbxt.replicate.delivery/output.png",
    ],
)
def test_replicate_output_url_accepts_only_delivery_hosts(
    monkeypatch: pytest.MonkeyPatch,
    url: str,
) -> None:
    monkeypatch.setattr(replicate_image.socket, "getaddrinfo", _public_dns)

    replicate_image._validate_replicate_url(url, purpose="output")


@pytest.mark.parametrize(
    "url",
    [
        "https://replicate.delivery.evil.example/output.png",
        "https://evil.example/output.png",
        "https://127.0.0.1/output.png",
    ],
)
def test_replicate_output_url_rejects_lookalike_and_internal_hosts(
    monkeypatch: pytest.MonkeyPatch,
    url: str,
) -> None:
    monkeypatch.setattr(replicate_image.socket, "getaddrinfo", _public_dns)

    with pytest.raises(replicate_image.ReplicateImageError):
        replicate_image._validate_replicate_url(url, purpose="output")


def test_redirect_handler_revalidates_the_destination(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(replicate_image.socket, "getaddrinfo", _public_dns)
    handler = replicate_image._ValidatedRedirectHandler("api")
    request = Request(
        "https://api.replicate.com/v1/predictions/prediction_123",
        headers={"Authorization": "Bearer synthetic"},
    )

    with pytest.raises(replicate_image.ReplicateImageError):
        handler.redirect_request(
            request,
            None,
            302,
            "Found",
            {},
            "https://attacker.example/steal",
        )


def test_output_download_never_adds_the_provider_bearer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    class FakeResponse:
        headers = {"Content-Type": "image/png"}

        def __init__(self):
            self._read = False

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def read(self, size=-1):
            del size
            if self._read:
                return b""
            self._read = True
            return b"png-bytes"

        def geturl(self):
            return "https://pbxt.replicate.delivery/output.png"

    def fake_open(request, *, timeout_seconds, purpose):
        captured.update(
            request=request,
            timeout_seconds=timeout_seconds,
            purpose=purpose,
        )
        return FakeResponse()

    monkeypatch.setattr(replicate_image, "_open_validated_request", fake_open)

    content_type, content = replicate_image._download_image(
        "https://pbxt.replicate.delivery/output.png",
        timeout_seconds=5,
    )

    request = captured["request"]
    assert isinstance(request, Request)
    assert request.get_header("Authorization") is None
    assert captured["purpose"] == "output"
    assert content_type == "image/png"
    assert content == b"png-bytes"
