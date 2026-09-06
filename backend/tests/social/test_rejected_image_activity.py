from datetime import UTC, datetime

from sqlalchemy import select

from app.domains.characters.models import AgentImageGenerationSetting, Character
from app.domains.routines.models.resident import AgentActivityLog
from app.domains.social.models.posts import PostImageGenerationJob
from app.runtime.social import image_generation
from social.test_l4_social_write_uow import _session_factory


def test_unsafe_local_image_request_persists_rejection_and_skipped_job_without_provider(monkeypatch, tmp_path):
    factory = _session_factory(tmp_path)

    def forbidden(*_args, **_kwargs):
        raise AssertionError("rejected image request must not call a provider")

    monkeypatch.setattr(image_generation.image_provider, "generate_image", forbidden)
    monkeypatch.setattr(image_generation, "generate_json", forbidden)
    with factory() as db:
        db.add(AgentImageGenerationSetting(
            character_id="social-uow-autonomous-character", image_key_mode="user",
            image_generation_enabled=True, max_images_per_day=10,
            pollinations_image_model="replicate-zimage-turbo-lora",
            encrypted_replicate_api_token="fixture", visual_identity_prompt="small blue bird",
            visual_identity_source_hash=None,
        ))
        db.commit()
        result = image_generation.create_local_api_post_image_request(
            db=db, user_id="social-uow-owner", local_key_prefix="test-prefix",
            character=db.get(Character, "social-uow-autonomous-character"),
            post_id="social-uow-target-post",
            image_prompt="bedroom scene with seductive pose and revealing clothes",
            requested_at=datetime.now(UTC),
        )
        assert result.status == "skipped"
        assert result.skip_reason == "unsafe_prompt"
        job_id = result.job_id

    with factory() as observer:
        logs = list(observer.scalars(select(AgentActivityLog).where(
            AgentActivityLog.action_type == "local_api_image_rejected",
        )))
        assert len(logs) == 1
        assert logs[0].character_id == "social-uow-autonomous-character"
        assert logs[0].target_post_id == "social-uow-target-post"
        assert logs[0].reason == "unsafe_prompt"
        assert logs[0].result == "skip_reason=unsafe_prompt; token_prefix=test-prefix"
        jobs = list(observer.scalars(select(PostImageGenerationJob)))
        assert len(jobs) == 1
        assert jobs[0].id == job_id
        assert jobs[0].status == "skipped"
        assert jobs[0].skip_reason == "unsafe_prompt"
