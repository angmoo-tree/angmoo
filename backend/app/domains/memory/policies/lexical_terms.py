"""Existing projection tokenization; output and index generation are unchanged."""
import re
_WORD_PATTERN = re.compile(r"[\w]+", re.UNICODE)

def _lexical_terms(value: str, *, query_mode: bool) -> tuple[str, ...]:
    terms: list[str] = []
    for token in _WORD_PATTERN.findall(value):
        if _contains_cjk(token):
            cjk = "".join(character for character in token if _is_cjk(character))
            if len(cjk) == 1:
                terms.append(cjk)
            elif len(cjk) > 1:
                if not query_mode:
                    terms.append(cjk)
                terms.extend(cjk[index : index + 2] for index in range(len(cjk) - 1))
            non_cjk = "".join(
                character if not _is_cjk(character) else " " for character in token
            )
            terms.extend(_WORD_PATTERN.findall(non_cjk))
        else:
            terms.append(token)
    return tuple(dict.fromkeys(term for term in terms if term))


def _contains_cjk(value: str) -> bool:
    return any(_is_cjk(character) for character in value)


def _is_cjk(character: str) -> bool:
    codepoint = ord(character)
    return (
        0x3400 <= codepoint <= 0x9FFF
        or 0x3040 <= codepoint <= 0x30FF
        or 0xAC00 <= codepoint <= 0xD7AF
    )
