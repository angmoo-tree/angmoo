from __future__ import annotations

import csv
from functools import lru_cache
from pathlib import Path
import re
import unicodedata


SLANG_CSV_PATH = Path(__file__).with_name("slang.csv")
SLANG_COLUMN = "slang"

RESERVED_NAME_TERMS = (
    "admin",
    "administrator",
    "moderator",
    "staff",
    "support",
    "operator",
    "official",
    "angmoo",
    "deleted",
    "deleted_user",
    "deleted_character",
    "관리자",
    "운영자",
    "스태프",
    "공식",
    "앙무",
    "앵무",
    "탈퇴한 사용자",
    "삭제한 유저",
    "삭제한 앵무",
)

_COMPACT_DROP_RE = re.compile(r"[^0-9a-z가-힣]+")


class NamePolicyError(RuntimeError):
    pass


class NamePolicyViolation(ValueError):
    pass


class _BlockedTerms(tuple):
    __slots__ = ()

    @property
    def exact(self) -> set[str]:
        return self[0]

    @property
    def compact_exact(self) -> set[str]:
        return self[1]

    @property
    def compact_contains(self) -> tuple[str, ...]:
        return self[2]

    @property
    def slang_count(self) -> int:
        return self[3]


def is_blocked_name(value: str) -> bool:
    normalized = _normalize_for_exact_match(value)
    if not normalized:
        return False

    terms = _load_blocked_terms()
    if normalized in terms.exact:
        return True

    compact = _compact_for_match(normalized)
    if not compact:
        return False
    if compact in terms.compact_exact:
        return True
    return any(term in compact for term in terms.compact_contains)


def ensure_name_allowed(value: str) -> None:
    if is_blocked_name(value):
        raise NamePolicyViolation("name is blocked by policy")


def slang_entry_count() -> int:
    return _load_blocked_terms().slang_count


@lru_cache(maxsize=1)
def _load_blocked_terms() -> _BlockedTerms:
    exact: set[str] = set()
    compact_exact: set[str] = set()
    compact_contains: set[str] = set()
    slang_count = 0

    for raw in _iter_slang_terms():
        if _add_term(raw, exact, compact_exact, compact_contains):
            slang_count += 1
    for raw in RESERVED_NAME_TERMS:
        _add_term(raw, exact, compact_exact, compact_contains)

    return _BlockedTerms((exact, compact_exact, tuple(sorted(compact_contains)), slang_count))


def _iter_slang_terms() -> list[str]:
    if not SLANG_CSV_PATH.exists():
        raise NamePolicyError(f"missing slang policy file: {SLANG_CSV_PATH}")

    with SLANG_CSV_PATH.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if SLANG_COLUMN not in (reader.fieldnames or []):
            raise NamePolicyError("slang policy file must contain a slang column")
        return [
            value.strip()
            for row in reader
            if (value := (row.get(SLANG_COLUMN) or "").strip())
        ]


def _add_term(
    raw: str,
    exact: set[str],
    compact_exact: set[str],
    compact_contains: set[str],
) -> bool:
    normalized = _normalize_for_exact_match(raw)
    if not normalized:
        return False
    exact.add(normalized)

    compact = _compact_for_match(normalized)
    if compact:
        compact_exact.add(compact)
        if len(compact) >= 4:
            compact_contains.add(compact)
    return True


def _normalize_for_exact_match(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value)
    without_controls = "".join(
        char for char in normalized if not unicodedata.category(char).startswith("C")
    )
    return " ".join(without_controls.casefold().strip().split())


def _compact_for_match(value: str) -> str:
    return _COMPACT_DROP_RE.sub("", value)

