"""Pinned build inputs fail closed without relying on sqlite.org availability."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import importlib.util
import io
from pathlib import Path
import ssl
from urllib.error import HTTPError, URLError

import pytest

SPEC = importlib.util.spec_from_file_location("vec1_build", Path(__file__).parents[2] / "scripts/build_vec1.py")
build = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(build)
DATA = b"fixed official input"
DIGEST = hashlib.sha256(DATA).hexdigest()


@pytest.fixture
def transport(monkeypatch):
    calls, responses, delays = [], [], []
    def open_url(url, timeout):
        calls.append((url, timeout))
        result = responses.pop(0)
        if isinstance(result, Exception):
            raise result
        return io.BytesIO(result)
    monkeypatch.setattr(build, "urlopen", open_url)
    monkeypatch.setattr(build.time, "sleep", delays.append)
    return calls, responses, delays


@pytest.mark.parametrize("status", sorted(build.TRANSIENT_HTTP))
def test_transient_retry_keeps_url_digest_and_bounded_attempts(transport, status):
    calls, responses, delays = transport
    responses.extend([HTTPError("https://fixture", status, "temporary", {"Retry-After": "999"}, None), DATA])
    assert build.download("https://fixture", DIGEST) == DATA
    assert len(calls) == 2 and {url for url, _ in calls} == {"https://fixture"}
    assert all(0 < timeout <= 60 for _, timeout in calls)
    assert delays == [5.0]


@pytest.mark.parametrize("error", [HTTPError("https://fixture", 404, "missing", {}, None),
                                  URLError(ssl.SSLCertVerificationError("certificate"))])
def test_permanent_or_tls_error_is_not_retried(transport, error):
    calls, responses, delays = transport
    responses.append(error)
    with pytest.raises(type(error)):
        build.download("https://fixture", DIGEST)
    assert len(calls) == 1 and not delays


def test_transient_attempt_limit(transport):
    calls, responses, delays = transport
    responses.extend([URLError(ConnectionResetError()) for _ in range(3)])
    with pytest.raises(URLError):
        build.download("https://fixture", DIGEST)
    assert len(calls) == 3 and len(delays) == 2


@pytest.mark.parametrize("value,code", [(b"wrong", "integrity"), (b"x" * 65, "too_large")])
def test_bad_bytes_fail_without_retry_or_cache_publication(tmp_path, monkeypatch, transport, value, code):
    monkeypatch.setattr(build, "MAX_BYTES", 64)
    calls, responses, delays = transport
    responses.append(value)
    with pytest.raises(RuntimeError, match=code):
        build.download("https://fixture", DIGEST, tmp_path)
    assert len(calls) == 1 and not delays and not list(tmp_path.iterdir())


def test_cache_is_rehashed_and_corruption_is_quarantined(tmp_path, transport):
    calls, responses, _ = transport
    responses.append(DATA)
    assert build.download("https://fixture", DIGEST, tmp_path) == DATA
    assert build.download("https://fixture", DIGEST, tmp_path) == DATA
    assert len(calls) == 1
    target = build._cache_path(tmp_path, DIGEST)
    target.write_bytes(b"corrupt")
    responses.append(DATA)
    assert build.download("https://fixture", DIGEST, tmp_path) == DATA
    assert len(calls) == 2 and target.read_bytes() == DATA
    assert len(list(tmp_path.glob("*.invalid-*"))) == 1


def test_concurrent_cache_writers_publish_only_complete_verified_bytes(tmp_path, monkeypatch):
    monkeypatch.setattr(build, "urlopen", lambda *args, **kwargs: io.BytesIO(DATA))
    with ThreadPoolExecutor(max_workers=4) as pool:
        assert list(pool.map(lambda _: build.download("https://fixture", DIGEST, tmp_path), range(12))) == [DATA] * 12
    assert build._cache_path(tmp_path, DIGEST).read_bytes() == DATA
    assert not list(tmp_path.glob("*.tmp"))


def test_cache_cannot_follow_redirected_path(tmp_path):
    link = tmp_path / "redirect"
    try:
        link.symlink_to(tmp_path, target_is_directory=True)
    except OSError:
        pytest.skip("Windows symlink privilege unavailable; hosted Linux covers rejection")
    with pytest.raises(ValueError, match="redirected"):
        build._cache_path(link, DIGEST)


def test_deadline_stops_before_another_attempt(monkeypatch, transport):
    calls, responses, delays = transport
    clock = iter((0.0, 0.0, 179.5))
    monkeypatch.setattr(build.time, "monotonic", lambda: next(clock))
    responses.append(URLError(TimeoutError()))
    with pytest.raises(TimeoutError, match="deadline"):
        build.download("https://fixture", DIGEST)
    assert len(calls) == 1 and not delays


def test_prepare_sources_rejects_invalid_archive_without_retry(tmp_path, monkeypatch):
    monkeypatch.setattr(build, "download", lambda url, digest, cache: b"not a zip")
    with pytest.raises(build.zipfile.BadZipFile):
        build.prepare_sources(tmp_path)


def test_pinned_vec1_source_needs_no_network_and_keeps_existing_digest(tmp_path, monkeypatch):
    monkeypatch.setattr(build, "urlopen", lambda *args, **kwargs: pytest.fail("Vec1 source used network"))
    data = build.download(build.SOURCE_URL, build.SOURCE_SHA256, tmp_path)
    assert hashlib.sha256(data).hexdigest() == "8571bb4f77f9547d11ad11e2f72e0de7d3b2ab44e7930151998bce9377ed4b86"
    assert data == build.BUNDLED_SOURCE.read_bytes()
    assert build._cache_path(tmp_path, build.SOURCE_SHA256).read_bytes() == data


@pytest.mark.parametrize("missing", [False, True])
def test_invalid_bundled_source_fails_without_network_fallback(tmp_path, monkeypatch, missing):
    source = tmp_path / "vec1.c"
    if not missing:
        source.write_bytes(b"not the reviewed source")
    monkeypatch.setattr(build, "BUNDLED_SOURCE", source)
    monkeypatch.setattr(build, "urlopen", lambda *args, **kwargs: pytest.fail("unreviewed fallback"))
    with pytest.raises(FileNotFoundError if missing else RuntimeError):
        build.download(build.SOURCE_URL, build.SOURCE_SHA256)


def test_arm64_compiler_patch_preserves_upstream_and_other_platform_bytes():
    original = build.BUNDLED_SOURCE.read_bytes()
    assert build.compiler_source(original, "x86_64") == (original, None)
    changed, patch = build.compiler_source(original, "aarch64")
    assert patch == build.ARM64_PATCH and changed != original
    assert b"vorrq_u32(cmp, vceqq_s32(lhs, rhs2))" in changed
    assert build.BUNDLED_SOURCE.read_bytes() == original
    with pytest.raises(RuntimeError, match="integrity"):
        build.compiler_source(original + b"changed", "aarch64")
