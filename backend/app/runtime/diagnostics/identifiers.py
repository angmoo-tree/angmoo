"""Allowlisted diagnostic identifiers; never accept free-form user content."""
import re
from typing import Any

_CODE = re.compile(r"[A-Za-z0-9_./:@-]{1,160}\Z")

def code(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text if _CODE.fullmatch(text) else None



def identifier(value: Any) -> str | None:
    """IDs are backend supplied; arbitrary prose is never copied as an ID."""
    return code(value)
