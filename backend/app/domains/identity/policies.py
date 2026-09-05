from app.domains.identity.exceptions import LocalOwnerProfileInvalidError


def normalize_local_display_name(value: str | None) -> tuple[str, str]:
    display_name = " ".join((value or "").strip().split())
    if not display_name or len(display_name) > 80:
        raise LocalOwnerProfileInvalidError("invalid local owner display name")
    return display_name, display_name.casefold()


def normalize_local_label(value: str | None) -> str | None:
    label = " ".join((value or "").strip().split())
    if not label:
        return None
    if len(label) > 80:
        raise LocalOwnerProfileInvalidError("invalid local installation label")
    return label
