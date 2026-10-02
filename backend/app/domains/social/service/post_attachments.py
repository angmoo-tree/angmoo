"""User-uploaded post images, attached in the same source-write transaction."""
from sqlalchemy import select
from app.domains.social.models.posts import PostMedia
from app.domains.social.contracts.writes import SocialWriteConflictError, SocialWriteForbiddenError
from app.domains.media.contracts import InvalidProfileMediaError


def media_view(row):
    return {"id": row.id, "post_id": row.post_id, "media_type": row.media_type,
        "asset_id": row.asset_id, "url": row.url, "alt_text": row.alt_text, "model": row.model,
        "prompt_hash": row.prompt_hash, "byte_size": row.byte_size, "created_at": row.created_at,
        "width": row.width, "height": row.height, "source_kind": row.source_kind}


class PostAttachments:
    def __init__(self, assets):
        self.assets = assets

    def attach(self, db, post, owner_id, asset_id):
        if db.scalar(select(PostMedia.id).where(PostMedia.post_id == post.id)):
            raise SocialWriteConflictError("post_already_has_image")
        try:
            asset = self.assets.attach(db, owner_id=owner_id, asset_id=asset_id,
                scope_kind="world", scope_id=post.world_id)
        except InvalidProfileMediaError as exc:
            raise SocialWriteForbiddenError(str(exc)) from exc
        db.add(PostMedia(post_id=post.id, asset_id=asset.id, source_kind="upload", url=f"/api/v1/media/assets/{asset.id}/content",
            alt_text="사용자가 첨부한 이미지", model=None, prompt_hash=None, byte_size=asset.byte_size,
            width=asset.width, height=asset.height, key_source="upload"))
        db.flush()
