"""Authenticated, opaque pagination for one World/character/profile tab."""
from __future__ import annotations

import binascii
import hashlib
import json
import os
from datetime import datetime
from typing import Any
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from app.config import settings
from app.pagination import decode_cursor_bytes, encode_cursor_bytes
from app.domains.social.contracts.profile_activity import WorldCharacterSocialProfileQuery, WorldCharacterSocialProfileValidationError


_CURSOR_VERSION = "world-character-social-profile-cursor-v1"


_CURSOR_AAD = _CURSOR_VERSION.encode("ascii")


_CURSOR_NONCE_BYTES = 12


def _encode_cursor(
    query: WorldCharacterSocialProfileQuery,
    *,
    created_at: datetime,
    item_id: str,
) -> str:
    payload = {
        "created_at": created_at.isoformat(),
        "item_id": item_id,
        "tab": query.tab,
        "version": _CURSOR_VERSION,
        "world_character_id": query.world_character_id,
        "world_id": query.world_id,
    }
    nonce = os.urandom(_CURSOR_NONCE_BYTES)
    plaintext = json.dumps(
        payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")
    encrypted = AESGCM(_cursor_key()).encrypt(nonce, plaintext, _CURSOR_AAD)
    return encode_cursor_bytes(nonce + encrypted)


def _decode_cursor(
    query: WorldCharacterSocialProfileQuery,
) -> tuple[datetime, str] | None:
    if query.cursor is None:
        return None
    try:
        encrypted = decode_cursor_bytes(query.cursor)
        if len(encrypted) <= _CURSOR_NONCE_BYTES + 16:
            raise ValueError("cursor_length")
        plaintext = AESGCM(_cursor_key()).decrypt(
            encrypted[:_CURSOR_NONCE_BYTES],
            encrypted[_CURSOR_NONCE_BYTES:],
            _CURSOR_AAD,
        )
        decoded: Any = json.loads(plaintext.decode("utf-8"))
        if not isinstance(decoded, dict) or set(decoded) != {
            "created_at",
            "item_id",
            "tab",
            "version",
            "world_character_id",
            "world_id",
        }:
            raise ValueError("cursor_shape")
        if (
            decoded["version"] != _CURSOR_VERSION
            or decoded["world_id"] != query.world_id
            or decoded["world_character_id"] != query.world_character_id
            or decoded["tab"] != query.tab
            or not isinstance(decoded["item_id"], str)
            or not decoded["item_id"]
            or not isinstance(decoded["created_at"], str)
        ):
            raise ValueError("cursor_scope")
        return datetime.fromisoformat(decoded["created_at"]), decoded["item_id"]
    except (
        binascii.Error,
        InvalidTag,
        UnicodeDecodeError,
        ValueError,
        json.JSONDecodeError,
    ) as exc:
        raise WorldCharacterSocialProfileValidationError() from exc


def _cursor_key() -> bytes:
    return hashlib.sha256(
        f"{_CURSOR_VERSION}\0{settings.app_secret}".encode("utf-8")
    ).digest()
