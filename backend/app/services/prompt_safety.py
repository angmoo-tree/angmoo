from __future__ import annotations

from dataclasses import dataclass
import re
import unicodedata


@dataclass(frozen=True)
class PromptSafetyResult:
    allowed: bool
    category: str | None = None
    reason: str = ""
    matched: str = ""


class PromptSafetyError(ValueError):
    def __init__(self, field_name: str, result: PromptSafetyResult) -> None:
        self.field_name = field_name
        self.result = result
        super().__init__("prompt_injection_detected")


_TARGET_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("system_prompt", re.compile(r"(?:system|developer)\s+prompt|시스템\s*프롬프트|개발자\s*(?:프롬프트|지시)")),
    ("privileged_instruction", re.compile(r"(?:previous|prior|system|developer)\s+instruction|이전\s*지시|상위\s*지시|시스템\s*지시")),
    ("hidden_instruction", re.compile(r"hidden\s+instruction|숨겨진\s*지시|비밀\s*지시")),
    ("api_secret", re.compile(r"api\s*key|\bsecret\b|api\s*키|비밀\s*키|인증\s*토큰")),
    ("hidden_tool", re.compile(r"hidden\s+tool|tool\s+list|숨겨진\s*도구|도구\s*목록")),
    ("backend_policy", re.compile(r"backend\s+policy|백엔드\s*정책")),
    ("safety_rule", re.compile(r"safety\s+rule|안전\s*규칙|보안\s*규칙")),
)

_REVEAL_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("reveal", re.compile(r"\b(?:reveal|show|print|leak|disclose)\b|공개\s*해|공개\s*하라|공개\s*하세요|출력\s*해|출력\s*하라|보여\s*줘|보여\s*라|노출\s*해|유출\s*해")),
    ("bypass", re.compile(r"\b(?:ignore|override|bypass|disable|disregard)\b|무시\s*해|무시\s*하라|우회\s*해|우회\s*하라|해제\s*해|덮어\s*써")),
)

_NEGATED_SAFE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"공개\s*하지|출력\s*하지|노출\s*하지|유출\s*하지|보여\s*주지"),
    re.compile(r"공개\s*하지\s*않|출력\s*하지\s*않|노출\s*하지\s*않|유출\s*하지\s*않"),
    re.compile(r"공개\s*못\s*해|출력\s*못\s*해|노출\s*못\s*해|보여\s*줄\s*수\s*없"),
    re.compile(r"\b(?:do\s+not|don't|never|should\s+not|must\s+not)\s+(?:reveal|show|print|leak|disclose)\b"),
    re.compile(r"\b(?:cannot|can't|can\s+not|won't|will\s+not)\s+(?:reveal|show|print|leak|disclose)\b"),
)

_OUTPUT_LEAK_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "system_prompt:leak_format",
        re.compile(
            r"(?:system|developer)\s+prompt\s*(?::|\s+(?:is|as\s+follows|below))|"
            r"(?:시스템|개발자)\s*(?:프롬프트|지시)\s*(?:는|은)?\s*(?:다음과\s*같|:)"
        ),
    ),
    (
        "api_secret:leak_format",
        re.compile(
            r"(?:api\s*key|secret)\s*(?:is|=|:)|"
            r"(?:인증\s*토큰|api\s*키|비밀\s*키)\s*(?:는|은)?\s*(?:[a-z0-9][a-z0-9._-]{5,}|다음과\s*같|:)"
        ),
    ),
    (
        "hidden_tool:leak_format",
        re.compile(
            r"(?:hidden\s+tool|tool\s+list|숨겨진\s*도구|도구\s*목록)\s*(?:is|as\s+follows|:|는|은)"
        ),
    ),
    (
        "backend_policy:leak_format",
        re.compile(r"(?:backend\s+policy|백엔드\s*정책)\s*(?:is|as\s+follows|:|는|은)"),
    ),
)

_QUOTE_CHARS = str.maketrans(
    {
        "`": " ",
        '"': " ",
        "'": " ",
        "\u201c": " ",
        "\u201d": " ",
        "\u2018": " ",
        "\u2019": " ",
    }
)


def detect_prompt_injection_text(
    text: str | None, field_kind: str = "general"
) -> PromptSafetyResult:
    normalized = _normalize(text)
    if not normalized:
        return PromptSafetyResult(allowed=True)

    for target_category, target_match in _TARGET_PATTERNS:
        target = target_match.search(normalized)
        if target is None:
            continue
        for action_category, action_match in _REVEAL_PATTERNS:
            action = action_match.search(normalized)
            if action is None:
                continue
            if _is_safe_negated_statement(normalized, target.start(), action.start()):
                continue
            matched = _matched_span(normalized, target, action)
            return PromptSafetyResult(
                allowed=False,
                category=f"{target_category}:{action_category}",
                reason=f"{field_kind} contains an internal target plus privileged action",
                matched=matched,
            )

    return PromptSafetyResult(allowed=True)


def ensure_no_prompt_injection_text(
    text: str | None, field_name: str, field_kind: str = "general"
) -> None:
    result = detect_prompt_injection_text(text, field_kind=field_kind)
    if not result.allowed:
        raise PromptSafetyError(field_name, result)


def contains_prompt_injection_output(text: str | None) -> PromptSafetyResult:
    result = detect_prompt_injection_text(text, field_kind="output")
    if not result.allowed:
        return result

    normalized = _normalize(text)
    if not normalized:
        return PromptSafetyResult(allowed=True)

    for category, pattern in _OUTPUT_LEAK_PATTERNS:
        match = pattern.search(normalized)
        if match is not None:
            return PromptSafetyResult(
                allowed=False,
                category=category,
                reason="output appears to disclose internal prompt or secret material",
                matched=_matched_single_span(normalized, match),
            )

    return PromptSafetyResult(allowed=True)


def _normalize(text: str | None) -> str:
    if text is None:
        return ""
    normalized = unicodedata.normalize("NFKC", str(text))
    normalized = re.sub(r"```(?:\w+)?", " ", normalized)
    normalized = normalized.translate(_QUOTE_CHARS)
    normalized = normalized.lower()
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized.strip()


def _is_safe_negated_statement(text: str, target_index: int, action_index: int) -> bool:
    if not any(pattern.search(text) for pattern in _NEGATED_SAFE_PATTERNS):
        return False
    start = max(0, min(target_index, action_index) - 32)
    end = min(len(text), max(target_index, action_index) + 64)
    window = text[start:end]
    if any(pattern.search(window) for pattern in _NEGATED_SAFE_PATTERNS):
        return True
    return False


def _matched_span(
    text: str, first: re.Match[str], second: re.Match[str], *, padding: int = 32
) -> str:
    start = max(0, min(first.start(), second.start()) - padding)
    end = min(len(text), max(first.end(), second.end()) + padding)
    return text[start:end]


def _matched_single_span(text: str, match: re.Match[str], *, padding: int = 32) -> str:
    start = max(0, match.start() - padding)
    end = min(len(text), match.end() + padding)
    return text[start:end]

