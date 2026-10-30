"""Validate text at the untrusted-result boundary without database I/O."""


def require_storage_text(value):
    if isinstance(value, str):
        if "\x00" in value or any(0xD800 <= ord(c) <= 0xDFFF for c in value):
            raise ValueError("relationship_review_storage_text_invalid")
    elif isinstance(value, dict):
        for key, child in value.items():
            require_storage_text(key)
            require_storage_text(child)
    elif isinstance(value, (list, tuple)):
        for child in value:
            require_storage_text(child)
