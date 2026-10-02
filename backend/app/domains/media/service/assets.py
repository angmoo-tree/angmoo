"""Owned attachment drafts and immutable pixels; caller owns commit/rollback."""
import hashlib
from datetime import datetime, timedelta, timezone
from io import BytesIO
from pathlib import Path
import re
from uuid import uuid4
from dataclasses import dataclass
from PIL import Image, ImageOps, ImageCms
from sqlalchemy.orm import Session
from sqlalchemy import select
from app.domains.media.contracts import InvalidProfileMediaError
from app.domains.media.models import MediaAsset
from app.domains.media.service.pixel_validation import validate_pixels
from app.core.image_bytes import ImageInspection


class AssetService:
    def __init__(self, root: Path, authorize_scope):
        self.root = root.resolve()
        self.authorize_scope = authorize_scope

    def path(self, asset: MediaAsset) -> Path:
        lexical = self.root / asset.storage_key
        if lexical.is_symlink() or lexical.parent.is_symlink():
            raise InvalidProfileMediaError("asset_path_invalid")
        resolved = lexical.resolve()
        if self.root not in resolved.parents:
            raise InvalidProfileMediaError("asset_path_invalid")
        return resolved

    def owned(self, db: Session, *, owner_id: str, asset_id: str, scope_kind: str | None = None, scope_id: str | None = None) -> MediaAsset:
        row = db.get(MediaAsset, asset_id)
        if row is None or row.owner_id != owner_id or row.state in {"deleted", "expired"}:
            raise InvalidProfileMediaError("asset_not_found")
        if (scope_kind is not None and row.scope_kind != scope_kind) or (scope_id is not None and row.scope_id != scope_id):
            raise InvalidProfileMediaError("asset_scope_mismatch")
        self.authorize_scope(db, owner_id, row.scope_kind, row.scope_id)
        if row.state == "draft" and row.expires_at is not None and row.expires_at.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
            raise InvalidProfileMediaError("asset_draft_expired")
        return row

    def read(self, db: Session, *, owner_id: str, asset_id: str, digest: str | None = None) -> tuple[MediaAsset, bytes]:
        asset = self.owned(db, owner_id=owner_id, asset_id=asset_id)
        try:
            content = self.path(asset).read_bytes()
        except OSError as exc:
            raise InvalidProfileMediaError("asset_file_missing") from exc
        if hashlib.sha256(content).hexdigest() != asset.content_hash or (digest is not None and asset.content_hash != digest):
            raise InvalidProfileMediaError("asset_content_changed")
        info = validate_pixels(asset.content_type, content, max_bytes=32 * 1024 * 1024)
        if (info.width, info.height, info.byte_size) != (asset.width, asset.height, asset.byte_size):
            raise InvalidProfileMediaError("asset_metadata_changed")
        return asset, content

    def upload(self, db: Session, *, owner_id: str, scope_kind: str, scope_id: str,
               content_type: str, content: bytes, draft: bool = True) -> MediaAsset:
        self.authorize_scope(db, owner_id, scope_kind, scope_id)
        limit = (10 if draft else 24) * 1024 * 1024
        if len(content) > limit:
            raise InvalidProfileMediaError("asset_upload_too_large")
        prepared = prepare_asset_image(content_type, content, max_bytes=limit)
        pixels, info = prepared.content, prepared.info
        asset = MediaAsset(id=uuid4().hex, owner_id=owner_id, scope_kind=scope_kind, scope_id=scope_id,
            storage_key=f"{uuid4().hex}.{info.extension}", content_type=info.content_type, content_hash=hashlib.sha256(pixels).hexdigest(),
            byte_size=len(pixels), width=info.width, height=info.height, revision=1,
            state="draft" if draft else "ready", expires_at=datetime.now(timezone.utc) + timedelta(days=1) if draft else None)
        self.root.mkdir(parents=True, exist_ok=True)
        path = self.path(asset)
        with path.open("xb") as output:
            output.write(pixels)
        try:
            db.add(asset)
            db.flush()
        except Exception:
            path.unlink(missing_ok=True)
            raise
        return asset

    def attach(self, db: Session, *, owner_id: str, asset_id: str, scope_kind: str, scope_id: str) -> MediaAsset:
        asset = self.owned(db, owner_id=owner_id, asset_id=asset_id, scope_kind=scope_kind, scope_id=scope_id)
        if asset.state != "draft":
            raise InvalidProfileMediaError("asset_already_attached")
        asset.state, asset.expires_at = "ready", None
        db.flush()
        return asset

    def expire_drafts(self, db, now):
        rows = list(db.scalars(select(MediaAsset).where(MediaAsset.state == "draft", MediaAsset.expires_at < now)))
        for row in rows:
            row.state = "expired"
        db.commit()
        for row in rows:
            self.path(row).unlink(missing_ok=True)
        # Only generated opaque filenames, older than the draft retention interval.
        referenced = set(db.scalars(select(MediaAsset.storage_key)))
        for path in self.root.iterdir() if self.root.exists() else ():
            if re.fullmatch(r"[0-9a-f]{32}\.(png|jpg|webp)", path.name) and path.name not in referenced and not path.is_symlink() and path.is_file() and now.timestamp() - path.stat().st_mtime > 86400:
                path.unlink(missing_ok=True)


@dataclass(frozen=True)
class PreparedAssetImage:
    content: bytes
    info: ImageInspection
    normalized: bool


def prepare_asset_image(content_type, content, *, max_bytes):
    """Keep format/bytes unless rotation or privacy metadata requires encoding.

    Every source retains the same privacy policy. Structural transparency and a
    valid ICC profile are display information; text, EXIF and XMP are stripped.
    """
    info = validate_pixels(content_type, content, max_bytes=max_bytes)
    with Image.open(BytesIO(content)) as image:
        image.load()
        icc = image.info.get("icc_profile")
        if icc:
            try:
                ImageCms.ImageCmsProfile(BytesIO(icc))
            except (OSError, ValueError, TypeError):
                icc = None
        structural = {"transparency", "icc_profile", "jfif", "jfif_version", "jfif_unit", "jfif_density", "dpi", "loop", "background", "duration", "timestamp"}
        needs_encoding = bool(image.getexif()) or bool(set(image.info) - structural) or ("icc_profile" in image.info and not icc)
        if not needs_encoding:
            return PreparedAssetImage(content, info, False)
        normalized = ImageOps.exif_transpose(image)
        normalized.load()
        # Preserve palette transparency when metadata cleanup requires encoding.
        if info.format == "WEBP" and normalized.mode not in {"RGB", "RGBA"}:
            normalized = normalized.convert("RGBA" if "transparency" in image.info or "A" in normalized.getbands() else "RGB")
        if info.format == "JPEG" and normalized.mode not in {"RGB", "L", "CMYK"}:
            normalized = normalized.convert("RGB")
        normalized.info.clear()
        options = {"icc_profile": icc} if icc else {}
        if info.format == "PNG" and "transparency" in image.info:
            options["transparency"] = image.info["transparency"]
        if info.format == "JPEG":
            options.update(quality=95, subsampling=0)
        elif info.format == "WEBP":
            options.update(lossless=True)
        output = BytesIO()
        normalized.save(output, info.format, **options)
        pixels = output.getvalue()
    if len(pixels) > 32 * 1024 * 1024:
        raise InvalidProfileMediaError("asset_normalized_size_exceeded")
    final = validate_pixels(info.content_type, pixels, max_bytes=max_bytes)
    return PreparedAssetImage(pixels, final, True)


def normalize_pixels(content_type, content, *, max_bytes):
    validate_pixels(content_type, content, max_bytes=max_bytes)
    with Image.open(BytesIO(content)) as image:
        image = ImageOps.exif_transpose(image)
        image.load()
        normalized = image.convert("RGBA" if "A" in image.getbands() else "RGB")
        buffer = BytesIO()
        normalized.save(buffer, "PNG")
        pixels = buffer.getvalue()
        width, height = normalized.size
    if len(pixels) > 32 * 1024 * 1024:
        raise InvalidProfileMediaError("asset_normalized_size_exceeded")
    return pixels, width, height
