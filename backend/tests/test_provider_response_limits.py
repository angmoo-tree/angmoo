from io import BytesIO

import pytest

from app.integrations import bounded_http


class _Response:
    def __init__(self, content: bytes, *, content_length: str | None = None) -> None:
        self._stream = BytesIO(content)
        self.headers: dict[str, str] = {}
        if content_length is not None:
            self.headers["Content-Length"] = content_length
        self.bytes_read = 0

    def read(self, size: int) -> bytes:
        chunk = self._stream.read(size)
        self.bytes_read += len(chunk)
        return chunk


def test_bounded_provider_reader_rejects_large_content_length_before_read() -> None:
    response = _Response(
        b"not-read",
        content_length=str(bounded_http.MAX_PROVIDER_IMAGE_BYTES + 1),
    )

    with pytest.raises(bounded_http.ResponseTooLargeError):
        bounded_http.read_bounded_response(
            response,
            max_bytes=bounded_http.MAX_PROVIDER_IMAGE_BYTES,
        )

    assert response.bytes_read == 0


def test_bounded_provider_reader_rejects_deceptive_stream_at_max_plus_one() -> None:
    response = _Response(
        b"x" * 1025,
        content_length="1",
    )

    with pytest.raises(bounded_http.ResponseTooLargeError):
        bounded_http.read_bounded_response(response, max_bytes=1024)

    assert response.bytes_read == 1025


def test_bounded_provider_reader_accepts_exact_limit() -> None:
    response = _Response(b"x" * 1024)

    content = bounded_http.read_bounded_response(response, max_bytes=1024)

    assert len(content) == 1024
