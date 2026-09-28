"""Read Tavern PNG metadata/JSON without interpreting instructions in the card.

Format references and supported subset are documented in character-card-import.md.
Pillow owns image decoding; this module only checks the PNG container and reads tEXt.
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import io
import json
import struct
import zlib
from dataclasses import dataclass
from typing import Any

from PIL import Image, UnidentifiedImageError

MAX_FILE_BYTES = 20 * 1024 * 1024
MAX_JSON_BYTES = 2 * 1024 * 1024
MAX_TEXT_BYTES = 3 * 1024 * 1024
MAX_TOTAL_TEXT_BYTES = 6 * 1024 * 1024
MAX_DEPTH = 32
MAX_NODES = 50_000
MAX_CHUNKS = 4096
MAX_PIXELS = 16_000_000
MAX_DIMENSION = 8192
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
PARSER_VERSION = "angmoo-card-import-v1"
COMMON_FIELDS = ("name", "description", "personality", "scenario", "first_mes", "mes_example")


class CardParseError(ValueError):
    """Safe error code only; never echoes card content or filesystem paths."""


@dataclass(frozen=True)
class ParsedCard:
    version: int
    source_format: str
    source_sha256: str
    document: dict[str, Any]
    data: dict[str, Any]
    parser_version: str = PARSER_VERSION


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise CardParseError("card_duplicate_json_key")
        result[key] = value
    return result


def _reject_constant(_value):
    raise CardParseError("card_invalid_json_number")


def _json(content: bytes) -> dict[str, Any]:
    if len(content) > MAX_JSON_BYTES:
        raise CardParseError("card_json_too_large")
    try:
        document = json.loads(content.decode("utf-8"), object_pairs_hook=_object,
                              parse_constant=_reject_constant)
    except (UnicodeError, json.JSONDecodeError, RecursionError, ValueError) as exc:
        if isinstance(exc, CardParseError):
            raise
        raise CardParseError("card_invalid_json") from None
    if not isinstance(document, dict):
        raise CardParseError("card_json_object_required")
    stack = [(document, 1)]
    count = 0
    while stack:
        value, depth = stack.pop()
        count += 1
        if depth > MAX_DEPTH or count > MAX_NODES:
            raise CardParseError("card_json_complexity_limit")
        if isinstance(value, dict):
            stack.extend((child, depth + 1) for child in value.values())
        elif isinstance(value, list):
            stack.extend((child, depth + 1) for child in value)
    return document


def _png_metadata(content: bytes) -> tuple[bytes, str]:
    offset, chunks, total_text = 8, 0, 0
    texts = {}
    ended = False
    while offset < len(content):
        chunks += 1
        if chunks > MAX_CHUNKS or offset + 12 > len(content):
            raise CardParseError("card_invalid_png_chunks")
        size = struct.unpack_from(">I", content, offset)[0]
        kind = content[offset + 4:offset + 8]
        end = offset + 12 + size
        if end > len(content):
            raise CardParseError("card_truncated_png")
        data = content[offset + 8:offset + 8 + size]
        crc = struct.unpack_from(">I", content, offset + 8 + size)[0]
        if zlib.crc32(kind + data) & 0xFFFFFFFF != crc:
            raise CardParseError("card_png_crc_mismatch")
        if chunks == 1 and (kind != b"IHDR" or size != 13):
            raise CardParseError("card_invalid_png_header")
        if kind in {b"tEXt", b"iTXt", b"zTXt"}:
            total_text += size
            if size > MAX_TEXT_BYTES or total_text > MAX_TOTAL_TEXT_BYTES:
                raise CardParseError("card_png_text_too_large")
        if kind == b"tEXt":
            keyword, separator, encoded = data.partition(b"\0")
            if not separator or not 1 <= len(keyword) <= 79:
                raise CardParseError("card_invalid_png_text")
            key = keyword.lower()
            if key in {b"chara", b"ccv3"}:
                if key in texts:
                    raise CardParseError("card_duplicate_metadata")
                texts[key] = encoded
        offset = end
        if kind == b"IEND":
            if size or end != len(content):
                raise CardParseError("card_invalid_png_end")
            ended = True
            break
    if not ended:
        raise CardParseError("card_truncated_png")
    selected = b"ccv3" if b"ccv3" in texts else b"chara"
    if selected not in texts:
        raise CardParseError("card_metadata_missing")
    try:
        decoded = base64.b64decode(texts[selected], validate=True)
    except (binascii.Error, ValueError):
        raise CardParseError("card_invalid_base64") from None
    # Validate the actual image, after bounded container checks, without changing metadata.
    try:
        with Image.open(io.BytesIO(content)) as picture:
            width, height = picture.size
            if max(width, height) > MAX_DIMENSION or width * height > MAX_PIXELS:
                raise CardParseError("card_image_too_large")
            picture.verify()
        with Image.open(io.BytesIO(content)) as picture:
            picture.load()
    except CardParseError:
        raise
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
        raise CardParseError("card_invalid_image") from None
    return decoded, selected.decode("ascii")


def parse_card(content: bytes) -> ParsedCard:
    if not content or len(content) > MAX_FILE_BYTES:
        raise CardParseError("card_file_size_limit")
    is_png = content.startswith(PNG_SIGNATURE)
    selected = None
    if is_png:
        json_bytes, selected = _png_metadata(content)
    else:
        json_bytes = content
    document = _json(json_bytes)
    spec = document.get("spec")
    if spec is None:
        version, data = 1, document
        if not all(field in data for field in COMMON_FIELDS):
            raise CardParseError("card_v1_fields_missing")
    elif spec in {"chara_card_v2", "chara_card_v3"}:
        version = 2 if spec == "chara_card_v2" else 3
        if document.get("spec_version") != f"{version}.0":
            raise CardParseError("card_unsupported_version")
        data = document.get("data")
        if not isinstance(data, dict):
            raise CardParseError("card_data_object_required")
    else:
        raise CardParseError("card_unsupported_version")
    if selected == "ccv3" and version != 3:
        raise CardParseError("card_metadata_version_mismatch")
    for field in COMMON_FIELDS:
        if not isinstance(data.get(field), str):
            raise CardParseError("card_common_field_type")
    if not data["name"].strip():
        raise CardParseError("card_name_required")
    return ParsedCard(version, "png" if is_png else "json",
                      hashlib.sha256(content).hexdigest(), document, data)
