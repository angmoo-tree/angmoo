from __future__ import annotations

import re
import unicodedata


class UnsafeImagePromptError(ValueError):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


SEXUAL_TERMS = (
    "nude",
    "nudity",
    "naked",
    "sex",
    "sexual",
    "erotic",
    "porn",
    "pornographic",
    "seductive",
    "lingerie",
    "fetish",
    "orgasm",
    "genital",
    "breast",
    "nipples",
    "노출",
    "나체",
    "누드",
    "성적",
    "성행위",
    "섹스",
    "포르노",
    "야한",
    "에로",
    "유혹적",
    "속옷",
    "성기",
    "가슴 노출",
)
MINOR_TERMS = (
    "child",
    "children",
    "minor",
    "underage",
    "teen",
    "kid",
    "아동",
    "미성년",
    "어린이",
    "아이",
    "청소년",
)
GORE_TERMS = (
    "gore",
    "gory",
    "bloodbath",
    "dismember",
    "disembowel",
    "decapitat",
    "mutilat",
    "intestines",
    "고어",
    "유혈",
    "사지절단",
    "절단",
    "참수",
    "내장",
    "훼손된 시체",
)
HATE_TERMS = (
    "swastika",
    "nazi",
    "kkk",
    "hate symbol",
    "white supremacist",
    "하켄크로이츠",
    "나치",
    "혐오 상징",
)


def ensure_safe_image_text(text: str | None) -> None:
    reason = unsafe_image_text_reason(text)
    if reason:
        raise UnsafeImagePromptError(reason)


def unsafe_image_text_reason(text: str | None) -> str | None:
    normalized = _normalize(text)
    if not normalized:
        return None
    normalized = _strip_negative_safety_phrases(normalized)
    if _contains_any(normalized, GORE_TERMS):
        return "gore"
    if _contains_any(normalized, HATE_TERMS):
        return "hate_symbol"
    has_sexual = _contains_any(normalized, SEXUAL_TERMS)
    has_minor = _contains_any(normalized, MINOR_TERMS)
    if has_sexual and has_minor:
        return "minor_sexual_context"
    if has_sexual:
        return "sexual_content"
    return None


def _normalize(text: str | None) -> str:
    if not text:
        return ""
    normalized = unicodedata.normalize("NFKC", text).lower()
    return re.sub(r"\s+", " ", normalized).strip()


def _contains_any(text: str, terms: tuple[str, ...]) -> bool:
    return any(term in text for term in terms)


def _strip_negative_safety_phrases(text: str) -> str:
    phrases = (
        "no sexual content",
        "non-sexual",
        "no nudity",
        "no nude",
        "no naked",
        "no gore",
        "no hate symbols",
        "safe public social illustration",
        "성적이지 않은",
        "노출 없음",
        "나체 없음",
        "고어 없음",
        "혐오 상징 없음",
    )
    for phrase in phrases:
        text = text.replace(phrase, " ")
    return re.sub(r"\s+", " ", text).strip()
