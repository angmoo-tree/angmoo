import re


_HASHTAG_RE = re.compile(
    r"(?P<prefix>^|[\s\(\[\{<\"'.,!?;:~|/\\])"
    r"(?:#[0-9A-Za-z_\u3131-\u318e\uac00-\ud7a3]+)+"
)
_REPEATED_DECORATION_RE = re.compile(r"([!?~])\1+")
_HORIZONTAL_SPACE_RE = re.compile(r"[ \t\f\v]+")


def neutralize_context_text(value: str | None) -> str:
    """Strip surface-style cues from text before it is shown to the LLM."""
    if not value:
        return ""

    text = _HASHTAG_RE.sub(r"\g<prefix>", value)
    text = "".join(char for char in text if not _is_surface_style_symbol(char))
    text = _REPEATED_DECORATION_RE.sub(r"\1", text)
    text = _HORIZONTAL_SPACE_RE.sub(" ", text)
    text = re.sub(r" *\n *", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _is_surface_style_symbol(char: str) -> bool:
    codepoint = ord(char)
    if codepoint in {0x200D, 0x20E3}:
        return True
    return any(
        start <= codepoint <= end
        for start, end in (
            (0x1F000, 0x1FAFF),  # emoji and pictographs
            (0x2600, 0x27BF),  # miscellaneous symbols and dingbats
            (0xFE00, 0xFE0F),  # variation selectors
            (0xE0100, 0xE01EF),  # supplemental variation selectors
        )
    )
