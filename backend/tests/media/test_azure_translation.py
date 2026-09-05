"""Provider character budgets and request outcomes survive transport extraction."""
from datetime import UTC, datetime
import json

from pydantic import SecretStr
import pytest

from app.config import settings
from app.integrations import azure_translation as client
from app.runtime.characters import creator


@pytest.fixture
def translation_settings(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "MEDIA_ROOT", str(tmp_path))
    monkeypatch.setattr(settings, "TRANSLATION_PROVIDER", "azure")
    monkeypatch.setattr(settings, "AZURE_TRANSLATOR_KEY", SecretStr("translation-test-fixture"))
    monkeypatch.setattr(settings, "TRANSLATION_MONTHLY_CHAR_LIMIT", 4)
    creator._TRANSLATION_CACHE.clear()
    yield tmp_path / "translation-usage.json"
    creator._TRANSLATION_CACHE.clear()


class Response:
    def __init__(self, payload):
        self.content = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, size=-1):
        chunk = self.content if size < 0 else self.content[:size]
        self.content = self.content[len(chunk):]
        return chunk


def test_success_cache_and_monthly_limit_keep_provider_call_count(
    translation_settings, monkeypatch,
):
    requests = []

    def respond(request, timeout):
        requests.append((request, timeout))
        return Response([{"translations": [{"text": " blue sky "}]}])

    monkeypatch.setattr(client, "_open_translation_request", respond)
    assert creator._translate_image_prompt_to_english("하늘") == "blue sky"
    assert creator._translate_image_prompt_to_english(" 하늘 ") == "blue sky"
    assert creator._translate_image_prompt_to_english(" plain English ") == "plain English"
    assert creator._translate_image_prompt_to_english("초과문자") == "초과문자"
    assert len(requests) == 1
    request, timeout = requests[0]
    assert request.get_header("Ocp-apim-subscription-key") == "translation-test-fixture"
    assert "translation-test-fixture" not in request.full_url
    assert json.loads(request.data) == [{"Text": "하늘"}]
    assert timeout == settings.translation_timeout_seconds
    assert json.loads(translation_settings.read_text())["chars"] == 2


@pytest.mark.parametrize("failure", ["transport", "payload"])
def test_failed_translation_releases_reserved_characters(
    translation_settings, monkeypatch, failure,
):
    calls = []

    def fail(request, timeout):
        calls.append(request)
        if failure == "transport":
            raise OSError("injected transport failure")
        return Response([])

    monkeypatch.setattr(client, "_open_translation_request", fail)
    assert creator._translate_image_prompt_to_english("하늘") == "하늘"
    assert len(calls) == 1
    assert json.loads(translation_settings.read_text())["chars"] == 0
    assert "하늘" not in creator._TRANSLATION_CACHE


def test_disabled_translation_has_no_file_or_provider_side_effect(
    translation_settings, monkeypatch,
):
    monkeypatch.setattr(settings, "AZURE_TRANSLATOR_KEY", None)

    def unexpected(*_args):
        raise AssertionError("disabled translation must not request a provider")

    monkeypatch.setattr(client, "_open_translation_request", unexpected)
    assert creator._translate_image_prompt_to_english("하늘") == "하늘"
    assert not translation_settings.exists()


def test_month_rollover_and_exact_limit_preserve_usage_file_semantics(
    translation_settings,
):
    translation_settings.write_text('{"month":"2000-01","chars":999}', encoding="utf-8")
    assert client._reserve_translation_chars(4)
    assert not client._reserve_translation_chars(1)
    assert json.loads(translation_settings.read_text()) == {
        "month": datetime.now(UTC).strftime("%Y-%m"), "chars": 4,
    }
    client._release_translation_chars(9)
    assert json.loads(translation_settings.read_text())["chars"] == 0
