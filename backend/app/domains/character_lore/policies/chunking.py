from __future__ import annotations

import re
from app.domains.character_lore.constants import (
    TARGET_CHUNK_TARGET_CHARS,
    TARGET_CHUNK_MAX_CHARS,
)
from app.domains.character_lore.exceptions import CharacterLoreValidationError
from app.domains.character_lore.contracts import LoreChunkDraft
from app.domains.character_lore.utils import _normalize_text, _sha256_text


def chunk_lore_text(text: str) -> list[LoreChunkDraft]:
    normalized = _normalize_text(text)
    if not normalized:
        raise CharacterLoreValidationError("설정집에서 텍스트를 추출하지 못했습니다.")
    units = _split_lore_units(normalized)
    chunks: list[tuple[str | None, str]] = []
    current_section: str | None = None
    current_parts: list[str] = []
    current_length = 0

    def flush_current() -> None:
        nonlocal current_parts, current_length, current_section
        if not current_parts:
            return
        chunks.append((current_section, "\n".join(current_parts).strip()))
        current_parts = []
        current_length = 0

    for section_hint, unit in units:
        for piece in _split_long_unit(unit):
            piece_length = len(piece)
            if current_parts:
                next_length = current_length + piece_length + 1
                if (
                    section_hint != current_section
                    or next_length > TARGET_CHUNK_MAX_CHARS
                ):
                    flush_current()
            if not current_parts:
                current_section = section_hint
            current_parts.append(piece)
            current_length += piece_length + 1
            if current_length >= TARGET_CHUNK_TARGET_CHARS:
                flush_current()
    flush_current()

    drafts = [
        LoreChunkDraft(
            section_hint=section,
            text=chunk_text,
            content_hash=_sha256_text(chunk_text),
        )
        for section, chunk_text in chunks
        if chunk_text
    ]
    if not drafts:
        raise CharacterLoreValidationError(
            "설정집에서 검색 가능한 chunk를 만들지 못했습니다."
        )
    return drafts


def _split_lore_units(text: str) -> list[tuple[str | None, str]]:
    units: list[tuple[str | None, str]] = []
    section_hint: str | None = None
    paragraph: list[str] = []

    def flush_paragraph() -> None:
        nonlocal paragraph
        if paragraph:
            units.append((section_hint, " ".join(paragraph).strip()))
            paragraph = []

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            flush_paragraph()
            continue
        if _looks_like_section_heading(line):
            flush_paragraph()
            section_hint = _clean_heading(line)
            continue
        if _looks_like_boundary_line(line):
            flush_paragraph()
            units.append((section_hint, line))
            continue
        paragraph.append(line)
    flush_paragraph()
    return units


def _looks_like_section_heading(line: str) -> bool:
    stripped = line.strip().strip("#").strip()
    if not stripped or len(stripped) > 80:
        return False
    if line.lstrip().startswith("#"):
        return True
    if stripped.endswith(":"):
        return True
    return bool(re.match(r"^[\[(<【].+[\])>】]$", stripped))


def _clean_heading(line: str) -> str:
    return line.strip().strip("#").strip().rstrip(":")[:200]


def _looks_like_boundary_line(line: str) -> bool:
    return bool(
        re.match(r"^([-*•]|\d+[.)])\s+", line)
        or re.match(r"^(Q|A|문|답)\s*[:：]", line, re.IGNORECASE)
    )


def _split_long_unit(unit: str) -> list[str]:
    if len(unit) <= TARGET_CHUNK_MAX_CHARS:
        return [unit]
    sentences = re.split(r"(?<=[.!?。！？])\s+", unit)
    pieces: list[str] = []
    current = ""
    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue
        if len(sentence) > TARGET_CHUNK_MAX_CHARS:
            if current:
                pieces.append(current)
                current = ""
            pieces.extend(
                sentence[index : index + TARGET_CHUNK_MAX_CHARS]
                for index in range(0, len(sentence), TARGET_CHUNK_MAX_CHARS)
            )
            continue
        if current and len(current) + len(sentence) + 1 > TARGET_CHUNK_MAX_CHARS:
            pieces.append(current)
            current = sentence
        else:
            current = f"{current} {sentence}".strip()
    if current:
        pieces.append(current)
    return pieces or [unit[:TARGET_CHUNK_MAX_CHARS]]
