"""Exercise the actual upstream smoke boundary without Docker or HTTP traffic."""

import io
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.release import upstream_smoke as smoke


@pytest.mark.parametrize("identity", [{}, {"version": "0.1.0"}, [], {"version": "0.1.2"}])
def test_wrong_identity_fails_before_media_requests_and_cleans_up(tmp_path, monkeypatch, identity):
    calls = []
    cleanups = []

    def docker(*args):
        calls.append(args)
        if args[0] == "inspect":
            return json.dumps([{"NetworkSettings": {"Ports": {"3000/tcp": [{"HostPort": "12345"}]}}}])
        return "synthetic"

    requests = []

    def response(url, **kwargs):
        requests.append(url)
        return io.BytesIO(json.dumps(identity).encode())

    monkeypatch.setattr(smoke, "docker", docker)
    monkeypatch.setattr(smoke.urllib.request, "urlopen", response)
    monkeypatch.setattr(smoke.subprocess, "run", lambda *args, **kwargs: cleanups.append(args[0]))
    monkeypatch.setattr(smoke.time, "sleep", lambda _: pytest.fail("identity mismatch must not become a readiness retry"))
    with pytest.raises(ValueError, match="upstream_identity_invalid"):
        smoke.run("synthetic-front", "synthetic-back", "linux/arm64", tmp_path, expected_version="0.1.1")
    assert requests == ["http://127.0.0.1:12345/api/runtime-identity"]
    assert len(cleanups) == 2
    assert calls[-1][:2] == ("network", "rm")
    assert not (tmp_path / "upstreams.json").exists()
