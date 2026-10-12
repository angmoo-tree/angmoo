"""Current World image references, using the same access policy as World reads."""
from pathlib import Path
import re

from sqlalchemy.orm import Session

from app.config import settings
from app.domains.media.contracts import InvalidProfileMediaError
from app.domains.worlds.exceptions import WorldNotFoundError
from app.domains.worlds.service.creator import UserIdentity, require_world_read_access
from app.integrations.media.files import resolve_private_media_file

_WORLD_ID = re.compile(r"[A-Za-z0-9_-]+")
_IMAGE_NAME = re.compile(r"[A-Za-z0-9_-][A-Za-z0-9._-]{0,150}\.(?:webp|png|jpe?g)")


def read_world_media(
    db: Session, *, world_id: str, filename: str, user: UserIdentity | None,
) -> tuple[Path, str]:
    world = require_world_read_access(db, world_id=world_id, user=user)
    if not _WORLD_ID.fullmatch(world.id) or not _IMAGE_NAME.fullmatch(filename):
        raise WorldNotFoundError(world_id)
    reference = f"{settings.media_url_path}/worlds/{world.id}/{filename}"
    if reference not in (world.icon_media_id, world.banner_media_id):
        raise WorldNotFoundError(world_id)
    # The shared resolver checks child paths; also reject links at the owning
    # World directory and its parents before resolving a persisted reference.
    root = settings.media_root_path
    current = root / "worlds" / world.id
    try:
        while current != root:
            if current.is_symlink():
                raise InvalidProfileMediaError("World media symlinks are not allowed")
            current = current.parent
        return resolve_private_media_file(reference, expected_directory=f"worlds/{world.id}")
    except (InvalidProfileMediaError, OSError, ValueError) as exc:
        raise WorldNotFoundError(world_id) from exc
