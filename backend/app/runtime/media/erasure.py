"""Post-commit cleanup, retried from actor tombstones and deleted asset rows."""
import logging
import re
from sqlalchemy import select
from app.domains.media.models import MediaAsset
from app.domains.world_characters.models import WorldCharacter


def cleanup(media):
    try:
        with media.sessions() as db:
            for asset in db.scalars(select(MediaAsset).where(MediaAsset.state == "deleted")):
                media.assets.path(asset).unlink(missing_ok=True)
            for actor in db.scalars(select(WorldCharacter).where(WorldCharacter.status == "left")):
                tombstone = actor.local_profile or {}
                work = tombstone.get("private_cleanup") if tombstone.get("deleted") else None
                if not work:
                    continue
                paths = []
                for category, directory, suffixes in (
                    ("interpretations", "received-interpretations", (".json", ".tmp")),
                    ("generation_jobs", "received-results", (".json", ".pixels", ".json.tmp", ".pixels.tmp")),
                ):
                    for identity in work.get(category, ()):
                        if not isinstance(identity, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", identity):
                            raise ValueError("media_erasure_identity_invalid")
                        root = media.assets.root.resolve()
                        path = root / directory / identity
                        for suffix in suffixes:
                            target = path.with_name(path.name + suffix)
                            if target.is_symlink() or root not in target.resolve().parents:
                                raise ValueError("media_erasure_path_invalid")
                            paths.append(target)
                for path in paths:
                    path.unlink(missing_ok=True)
                actor.local_profile = {"deleted": True}
            db.commit()
        return True
    except Exception as exc:
        # No content, key, path or exception message is logged. Rows retain work.
        logging.getLogger(__name__).warning("media_erasure_pending type=%s", type(exc).__name__)
        return False
