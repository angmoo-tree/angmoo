from typing import Any


READ_CHUNK_BYTES = 64 * 1024
MAX_PROVIDER_IMAGE_BYTES = 12 * 1024 * 1024
MAX_PROVIDER_JSON_BYTES = 1024 * 1024
MAX_PROVIDER_RELAY_JSON_BYTES = 17 * 1024 * 1024


class ResponseTooLargeError(Exception):
    pass


def read_bounded_response(response: Any, *, max_bytes: int) -> bytes:
    headers = getattr(response, "headers", {})
    content_length = headers.get("Content-Length")
    if content_length:
        try:
            if int(content_length) > max_bytes:
                raise ResponseTooLargeError("Provider response is too large")
        except ValueError:
            pass

    content = bytearray()
    while len(content) <= max_bytes:
        remaining = max_bytes + 1 - len(content)
        chunk = response.read(min(READ_CHUNK_BYTES, remaining))
        if not chunk:
            return bytes(content)
        content.extend(chunk)
    raise ResponseTooLargeError("Provider response is too large")
