from __future__ import annotations

from io import BytesIO
import json
import socket
from urllib.error import HTTPError, URLError
from urllib.request import Request

import pytest

from app import schemas
from app.services import post_image_generation
from app.integrations import pollinations_image, provider_http, replicate_image
from app.runtime.characters import creator as agent_creation_drafts


CANARY = "phase7-provider-secret-canary-7f1d9e"


def _public_dns(*_args, **_kwargs):
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))]


def test_http_error_diagnostic_discards_raw_body_and_preserves_safe_fields() -> None:
    error = HTTPError(
        "https://provider.example/v1/generate",
        400,
        "Bad Request",
        {
            "Content-Type": "application/json; charset=utf-8",
            "X-Request-Id": "req_safe-123",
        },
        BytesIO(f'{{"nested":{{"credential":"{CANARY}"}},"error":"blocked"}}'.encode()),
    )

    diagnostic = provider_http.read_safe_http_error_diagnostic(
        error,
        classify_body=lambda body, _content_type: (
            "safe_filter_possible" if "blocked" in body else None
        ),
    )

    assert diagnostic.status_code == 400
    assert diagnostic.content_type == "application/json"
    assert diagnostic.request_id == "req_safe-123"
    assert diagnostic.diagnostic_hint == "safe_filter_possible"
    assert CANARY not in repr(diagnostic)
    assert CANARY not in repr(error.__dict__)


def test_provider_exceptions_never_retain_raw_response_body() -> None:
    pollinations_error = pollinations_image.PollinationsImageError(
        "Pollinations failed",
        failure_class="http_400",
        response_body_preview=CANARY,
    )
    replicate_error = replicate_image.ReplicateImageError(
        "Replicate failed",
        failure_class="http_400",
        response_body_preview=CANARY,
    )

    assert pollinations_error.response_body_preview is None
    assert replicate_error.response_body_preview is None
    assert CANARY not in repr(pollinations_error.__dict__)
    assert CANARY not in repr(replicate_error.__dict__)


def test_provider_failure_attempt_and_log_never_retain_raw_body(caplog) -> None:
    error = pollinations_image.PollinationsImageError(
        "Pollinations failed",
        failure_class="http_400",
        status_code=400,
        response_body_preview=CANARY,
        response_content_type="application/json",
        diagnostic_hint="provider_input_or_model_policy",
    )

    pollinations_image._log_failure(
        model="flux",
        failure_class="http_400",
        status_code=400,
        response_body_preview=CANARY,
        response_content_type="application/json",
        prompt_hash="synthetic-hash",
        prompt_length=11,
        request_url_length=100,
        reference_sent=False,
        prompt="safe prompt",
        log_context={"source": "security-test"},
    )
    prepared = post_image_generation._pollinations_failed(
        error,
        key_source="user",
        reference_source=None,
        reference_sent=False,
        prompt_hash="synthetic-hash",
        prompt_length=11,
        quota_reservation_id=None,
    )

    assert prepared.attempt["pollinations_response_body_preview"] is None
    assert prepared.attempt["pollinations_status_code"] == 400
    assert prepared.attempt["diagnostic_hint"] == "provider_input_or_model_policy"
    assert CANARY not in json.dumps(prepared.attempt)
    assert CANARY not in caplog.text
    api_payload = schemas.AgentFirstGreetingRead(
        run_id="run-security",
        status="failed",
        character_id="char-security",
        image_attempt=prepared.attempt,
        gateway_result={},
    ).model_dump_json()
    assert CANARY not in api_payload


def test_public_https_validator_rejects_non_https_and_non_global_dns(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.raises(provider_http.ProviderUrlError):
        provider_http.validate_public_https_url("http://provider.example/result")

    monkeypatch.setattr(
        provider_http.socket,
        "getaddrinfo",
        lambda *_args, **_kwargs: [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("169.254.169.254", 443))
        ],
    )
    with pytest.raises(provider_http.ProviderUrlError):
        provider_http.validate_public_https_url("https://provider.example/result")


def test_cross_origin_redirect_strips_provider_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(provider_http.socket, "getaddrinfo", _public_dns)
    handler = provider_http.ValidatedRedirectHandler(
        redirect_validator=provider_http.validate_public_https_url,
        sensitive_headers={
            "Authorization",
            "X-Pollinations-Api-Key",
            "Ocp-Apim-Subscription-Key",
            "Ocp-Apim-Subscription-Region",
        },
        allow_cross_origin_redirects=True,
    )
    request = Request(
        "https://source.example/start",
        headers={
            "Authorization": "Bearer synthetic",
            "X-Pollinations-Api-Key": "synthetic-pollinations",
            "Ocp-Apim-Subscription-Key": "synthetic-azure",
            "Ocp-Apim-Subscription-Region": "synthetic-region",
            "Accept": "application/json",
        },
    )

    redirected = handler.redirect_request(
        request,
        None,
        302,
        "Found",
        {},
        "https://destination.example/result",
    )

    assert redirected is not None
    assert redirected.get_header("Authorization") is None
    assert redirected.get_header("X-Pollinations-Api-Key") is None
    assert redirected.get_header("Ocp-Apim-Subscription-Key") is None
    assert redirected.get_header("Ocp-Apim-Subscription-Region") is None
    assert redirected.get_header("Accept") == "application/json"


def test_same_origin_redirect_keeps_provider_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(provider_http.socket, "getaddrinfo", _public_dns)
    handler = provider_http.ValidatedRedirectHandler(
        redirect_validator=provider_http.validate_public_https_url,
        sensitive_headers={"Authorization"},
    )
    request = Request(
        "https://source.example/start",
        headers={"Authorization": "Bearer synthetic"},
    )

    redirected = handler.redirect_request(
        request,
        None,
        302,
        "Found",
        {},
        "https://source.example/result",
    )

    assert redirected is not None
    assert redirected.get_header("Authorization") == "Bearer synthetic"


def test_cross_origin_redirect_is_rejected_by_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(provider_http.socket, "getaddrinfo", _public_dns)
    handler = provider_http.ValidatedRedirectHandler(
        redirect_validator=provider_http.validate_public_https_url,
        sensitive_headers={"Authorization"},
    )
    request = Request(
        "https://source.example/start",
        data=b"synthetic-body",
        headers={"Authorization": "Bearer synthetic"},
        method="POST",
    )

    with pytest.raises(provider_http.ProviderUrlError):
        handler.redirect_request(
            request,
            None,
            307,
            "Temporary Redirect",
            {},
            "https://destination.example/result",
        )


def test_provider_call_sites_use_validated_transport(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[set[str]] = []

    def fake_open(request, **kwargs):
        del request
        calls.append({name.lower() for name in kwargs["sensitive_headers"]})
        return object()

    monkeypatch.setattr(provider_http, "open_validated_request", fake_open)
    monkeypatch.setattr(
        agent_creation_drafts.settings,
        "AZURE_TRANSLATOR_ENDPOINT",
        "https://translator.example",
    )

    pollinations_image._open_pollinations_request(
        Request("https://gen.pollinations.ai/image/prompt"),
        1,
    )
    pollinations_image._open_relay_request(
        Request("https://relay.example/v1/image"),
        1,
    )
    agent_creation_drafts._open_pollinations_request(
        Request("https://gen.pollinations.ai/image/models"),
        1,
    )
    agent_creation_drafts._open_translation_request(
        Request("https://translator.example/translate"),
        1,
    )

    assert len(calls) == 4
    assert "authorization" in calls[0]
    assert "x-pollinations-api-key" in calls[1]
    assert "authorization" in calls[2]
    assert "ocp-apim-subscription-key" in calls[3]


def test_open_validated_request_revalidates_final_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeResponse:
        closed = False

        def geturl(self) -> str:
            return "https://metadata.example/result"

        def close(self) -> None:
            self.closed = True

    response = FakeResponse()

    class FakeOpener:
        def open(self, _request, **_kwargs):
            return response

    def fake_dns(host, *_args, **_kwargs):
        ip = "169.254.169.254" if host == "metadata.example" else "93.184.216.34"
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, 443))]

    monkeypatch.setattr(provider_http.socket, "getaddrinfo", fake_dns)
    monkeypatch.setattr(provider_http, "build_opener", lambda *_args: FakeOpener())

    with pytest.raises(provider_http.ProviderUrlError):
        provider_http.open_validated_request(
            Request("https://source.example/start"),
            timeout_seconds=1,
            initial_validator=provider_http.validate_public_https_url,
            redirect_validator=provider_http.validate_public_https_url,
            sensitive_headers={"Authorization"},
        )

    assert response.closed is True


def test_pollinations_initial_url_allowlist_is_fail_closed() -> None:
    with pytest.raises(URLError):
        pollinations_image._open_pollinations_request(
            Request("https://attacker.example/image"),
            1,
        )
    with pytest.raises(URLError):
        pollinations_image._open_pollinations_request(
            Request("https://gen.pollinations.ai/image-evil"),
            1,
        )
