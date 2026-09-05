from urllib.parse import urlsplit


def validate_profile_media_reference(value: str | None) -> str | None:
    if value is None:
        return None
    trimmed = value.strip()
    if not trimmed:
        return ""
    parsed = urlsplit(trimmed)
    if (
        parsed.scheme
        or parsed.netloc
        or trimmed.startswith("//")
        or not parsed.path.startswith("/media/")
    ):
        raise ValueError("Profile media must use an Angmoo-managed media path.")
    return trimmed
