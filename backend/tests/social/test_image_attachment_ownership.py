from datetime import UTC, datetime

import pytest
from sqlalchemy import event, func, select

from app.domains.social.contracts.image_generation import PreparedPostImage
from app.domains.social.models.posts import PostImageQuotaReservation, PostMedia
from app.domains.social.repository.media import create_post_image_quota_reservation
from app.domains.social.service import image_attachment
from test_l4_social_write_uow import _session_factory


@pytest.mark.parametrize("storage_fails", [False, True])
def test_attachment_keeps_media_commit_then_quota_finalization(monkeypatch, tmp_path, storage_fails):
    factory = _session_factory(tmp_path)
    with factory() as db:
        reservation = create_post_image_quota_reservation(
            db, user_id="social-uow-owner", character_id="social-uow-autonomous-character",
            quota_date=datetime.now(UTC).date(), source="resident", status="reserved",
        )
        db.commit()
        commits, saves = [], []
        event.listen(db, "before_commit", lambda *_: commits.append("commit"))

        def save(**kwargs):
            saves.append(kwargs)
            assert commits == []
            if storage_fails:
                raise OSError("fixture storage failure")
            return {"url": "/media/posts/example.webp", "byte_size": 10, "width": 1024, "height": 768}

        monkeypatch.setattr(image_attachment.profile_media, "save_generated_post_image_bytes", save)
        prepared = PreparedPostImage(
            attempt={"status": "ready", "provider": "pollinations"}, content_type="image/png",
            content=b"fixture-image", alt_text="image", prompt_hash="a" * 64, model="zimage",
            key_source="service", quota_reservation_id=reservation.id,
        )
        result = image_attachment.attach_prepared_post_image(
            db=db, post_id="social-uow-target-post", prepared=prepared,
        )
        assert saves == [{
            "post_id": "social-uow-target-post", "content_type": "image/png", "content": b"fixture-image",
            "target_size": (1024, 768), "max_bytes": 900_000, "quality_steps": (78, 70, 62),
        }]
        stored = db.get(PostImageQuotaReservation, reservation.id)
        assert stored.post_id == "social-uow-target-post" and stored.finalized_at is not None
        if storage_fails:
            assert result["status"] == "failed" and result["failure_class"] == "OSError"
            assert stored.status == "failed"
            assert db.scalar(select(func.count(PostMedia.id))) == 0
            assert commits == ["commit"]
        else:
            assert result["status"] == "attached" and result["media_url"] == "/media/posts/example.webp"
            assert stored.status == "attached"
            assert db.scalar(select(func.count(PostMedia.id))) == 1
            assert commits == ["commit", "commit"]
