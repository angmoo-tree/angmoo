"""Byte encoding shared by cursors with independently owned payloads and scope."""

import base64


def encode_cursor_bytes(payload: bytes) -> str:
    return base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")


def decode_cursor_bytes(cursor: str) -> bytes:
    return base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4))
