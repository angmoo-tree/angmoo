"""The live runner's durable guard and private observer, with no keys/network."""
import base64
import importlib.util
import json
from pathlib import Path
import sys
import httpx
import pytest
from image_integration.test_image_formats import encoded

SUPPORT = Path(__file__).resolve().parents[3] / "scripts/diagnostics/nanogpt_retest_support.py"
spec = importlib.util.spec_from_file_location("nanogpt_retest_support", SUPPORT)
support = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = support
spec.loader.exec_module(support)


def make_guard(tmp_path):
    guard = support.RetestGuard(tmp_path / "evidence", tmp_path / "private")
    support.atomic_json(guard.active, {"id": "NG01"})
    return guard


def generation(model="krea-v2/turbo", **changes):
    return httpx.Request("POST", "https://api.nano-gpt.com/api/v1/images", json={"model": model,
        "n": 1, "prompt": "synthetic scene", "resolution": "1k", "aspect_ratio": "1:1", **changes})


def test_durable_before_send_and_resume_do_not_permit_a_second_case_post(tmp_path):
    guard = make_guard(tmp_path)
    index = guard.before(generation())
    assert index == 0 and json.loads(guard.counter.read_text())["requests"][0]["status"] == "reserved_before_send"
    resumed = support.RetestGuard(guard.evidence, guard.private)
    with pytest.raises(RuntimeError, match="duplicate"):
        resumed.before(generation())
    guard.after(index, httpx.Response(200))
    assert json.loads(guard.counter.read_text())["image_submissions"] == 1


@pytest.mark.parametrize("changes", [{"n": 2}, {"resolution": "4k"}, {"model": "wrong-model"},
    {"output_format": "png"}, {"input_references": [{}]}])
def test_foreign_models_options_batches_and_reference_modes_are_denied_before_reserving(tmp_path, changes):
    guard = make_guard(tmp_path)
    with pytest.raises(RuntimeError):
        guard.before(generation(**changes))
    assert json.loads(guard.counter.read_text())["image_submissions"] == 0


def test_maximum_text_requests_counts_setup_retries_and_restart(tmp_path):
    guard = make_guard(tmp_path)
    request = httpx.Request("POST", "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.1-flash-lite:generateContent", json={})
    for _ in range(10):
        guard.before(request)
    with pytest.raises(RuntimeError, match="text_budget"):
        support.RetestGuard(guard.evidence, guard.private).before(request)
    with pytest.raises(RuntimeError, match="submission_denied"):
        guard.before(httpx.Request("POST", "https://openrouter.ai/api/v1/images", json={}))
    assert json.loads(guard.counter.read_text())["text_requests"] == 10


@pytest.mark.parametrize("format", ["PNG", "JPEG", "WEBP"])
def test_private_candidate_is_bounded_and_public_shape_contains_no_payload_or_credentials(tmp_path, format):
    guard = make_guard(tmp_path)
    guard.before(generation())
    content = encoded(format)
    value = base64.b64encode(content).decode()
    shape = guard.observe_image(httpx.Response(200, json={"data": [{"b64_json": value}], "private-unrecognized": "synthetic secret"}))
    assert shape["stage"] == "validated" and shape["format"] == format and shape["candidate_retained"]
    assert next((guard.private / "received-candidates").glob("*.candidate")).read_bytes() == content
    public = (guard.evidence / "response-shapes.json").read_text()
    assert value not in public and "synthetic secret" not in public and "private-unrecognized" not in public
    assert not (guard.evidence / "received-candidates").exists()


def test_url_only_candidate_is_not_fetched_or_promoted_to_success(tmp_path):
    guard = make_guard(tmp_path); guard.before(generation())
    shape = guard.observe_image(httpx.Response(200, json={"data": [{"url": "https://invalid.example/?secret=private"}]}))
    assert shape["stage"] == "base64" and not shape["candidate_retained"]
    assert "private" not in (guard.evidence / "response-shapes.json").read_text()


@pytest.mark.parametrize("name", ["run_nanogpt_mime_retest", "serve_nanogpt_mime_retest"])
def test_default_dry_run_opens_no_key_network_or_data_root(tmp_path, monkeypatch, capsys, name):
    spec = importlib.util.spec_from_file_location(name, SUPPORT.with_name(name + ".py"))
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    monkeypatch.setattr(sys, "argv", [name, "--private-root", str(tmp_path / "private"), "--evidence", str(tmp_path / "evidence")])
    module.main()
    record = json.loads(capsys.readouterr().out)
    assert record["key_reads"] == record["network_calls"] == 0 and not list(tmp_path.iterdir())


def test_cleanup_resume_accepts_disabled_empty_credential_rows_without_revalidating_profiles(tmp_path, monkeypatch):
    from types import SimpleNamespace
    spec = importlib.util.spec_from_file_location("run_nanogpt_mime_retest", SUPPORT.with_name("run_nanogpt_mime_retest.py"))
    runner = importlib.util.module_from_spec(spec); spec.loader.exec_module(runner)
    monkeypatch.setattr(runner, "read_db", lambda *args: [{"rows": 1, "enabled": 0, "secrets": 0}])
    calls = []
    class ClearedApi:
        def call(self, method, path, body=None):
            calls.append((method, path))
            assert method in {"GET", "POST"}
            if method == "POST":
                assert path.endswith("/deactivate")
                return None
            return {"provider": "nanogpt", "auto_enabled": False, "has_api_key": False}
    args = SimpleNamespace(private_root=tmp_path / "private", evidence=tmp_path / "evidence")
    runner.cleanup(ClearedApi(), args, {"character_id": "isolated"})
    record = json.loads((args.evidence / "cleanup.json").read_text())
    assert record["image_credential_rows"] == record["text_credential_rows"] == 1
    assert record["image_secrets_remaining"] == record["text_secrets_remaining"] == 0
    assert not any(method in {"PUT", "DELETE"} for method, _ in calls)
