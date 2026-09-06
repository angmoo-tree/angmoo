import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import event
from sqlalchemy.orm import object_session

from app.domains.characters.models import Character
from app.domains.social.contracts.image_generation import PreparedPostImage
from app.domains.social.models.posts import Post, PostImageGenerationJob
from app.domains.social.repository.media import create_post_image_generation_job
from app.domains.social.service.image_jobs import mark_stale_post_image_generation_jobs_failed
from app.runtime.social import image_job_worker as worker
from social.test_l4_social_write_uow import _session_factory


@pytest.mark.parametrize("removed,expected", [(None, "skipped"), ("character", "character_missing"), ("post", "post_missing")])
def test_image_worker_claims_then_validates_in_same_session(monkeypatch, tmp_path, removed, expected):
    factory = _session_factory(tmp_path)
    db = factory()
    job = create_post_image_generation_job(
        db, post_id="social-uow-target-post", user_id="social-uow-owner",
        character_id="social-uow-autonomous-character", source="local_api",
        status="queued", image_model="zimage", image_prompt="scene",
    )
    job_id = job.id
    if removed == "character":
        db.get(Character, job.character_id).deleted_at = datetime.now(UTC)
    elif removed == "post":
        db.get(Post, job.post_id).deleted_at = datetime.now(UTC)
    db.commit()
    commits, calls = [], []
    event.listen(db, "before_commit", lambda *_: commits.append("commit"))
    original_character = worker.get_character

    def character(session, character_id):
        assert session is db
        assert commits == ["commit"]  # the claim is committed before validation/provider work
        assert session.get(PostImageGenerationJob, job_id).status == "processing"
        calls.append("character")
        return original_character(session, character_id)

    async def prepare(**kwargs):
        assert kwargs["db"] is db
        assert object_session(kwargs["character"]) is db
        assert kwargs["job_id"] == job_id
        assert kwargs["run_started_at"] == job.started_at
        calls.append("prepare")
        return PreparedPostImage(attempt={"status": "skipped", "skip_reason": "disabled"})

    def attach(**kwargs):
        assert kwargs["db"] is db
        assert kwargs["post_id"] == job.post_id
        calls.append("attach")
        return kwargs["prepared"].attempt

    monkeypatch.setattr(worker, "SessionLocal", lambda: db)
    monkeypatch.setattr(worker, "get_character", character)
    monkeypatch.setattr(worker.post_image_generation, "prepare_local_api_post_image", prepare)
    monkeypatch.setattr(worker.image_attachment, "attach_prepared_post_image", attach)
    assert asyncio.run(worker.process_one_post_image_job()) is True
    assert commits == ["commit", "commit"]
    assert calls == (["character", "prepare", "attach"] if removed is None else ["character"])
    with factory() as observer:
        completed = observer.get(PostImageGenerationJob, job_id)
        assert completed.attempt_count == 1
        assert completed.finished_at is not None
        if removed is None:
            assert completed.status == expected and completed.skip_reason == "disabled"
        else:
            assert completed.status == "failed" and completed.failure_class == expected


def test_stale_image_failure_keeps_strict_cutoff_and_conditional_commit(tmp_path):
    factory = _session_factory(tmp_path)
    with factory() as db:
        job = create_post_image_generation_job(
            db, post_id="social-uow-target-post", user_id="social-uow-owner",
            character_id="social-uow-autonomous-character", source="local_api",
            status="processing", image_model="zimage", image_prompt="scene",
        )
        cutoff = datetime.now(UTC)
        job.started_at = cutoff
        db.commit()
        commits = []
        event.listen(db, "before_commit", lambda *_: commits.append("commit"))
        assert mark_stale_post_image_generation_jobs_failed(db, stale_before=cutoff) == 0
        assert commits == []
        assert mark_stale_post_image_generation_jobs_failed(db, stale_before=cutoff + timedelta(microseconds=1)) == 1
        assert job.status == "failed" and job.failure_class == "stale_processing"
        assert commits == ["commit"]
