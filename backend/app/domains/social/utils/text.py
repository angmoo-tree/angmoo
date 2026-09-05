"""Small Social formatting helpers without persistence or policy decisions."""

import re

_MULTIPLE_NEWLINES_RE = re.compile(r"\n{3,}")


def sanitize_visible_post_title(value: str) -> str:
    text = str(value or "")
    for marker in ("\\r\\n", "\\n", "\\r", "\\t"):
        text = text.replace(marker, " ")
    text = text.replace("\r\n", " ").replace("\r", " ").replace("\n", " ").replace("\t", " ")
    return " ".join(text.split())

def sanitize_visible_post_body(value: str) -> str:
    text = str(value or "")
    text = (
        text.replace("\\r\\n", "\n")
        .replace("\\n", "\n")
        .replace("\\r", "\n")
        .replace("\\t", " ")
    )
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\t", " ")
    text = "\n".join(line.rstrip() for line in text.split("\n"))
    return _MULTIPLE_NEWLINES_RE.sub("\n\n", text).strip()
