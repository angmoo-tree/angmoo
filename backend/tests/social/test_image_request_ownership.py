from app.domains.social.service import image_identity
from datetime import UTC, datetime

from sqlalchemy import event, select
from sqlalchemy.orm import object_session

from app.domains.characters.models import Character
from app.domains.social.models.posts import Post, PostImageGenerationJob
from app.domains.social.schemas.community import BotImageRequestRead
from app.models.agent_settings import AgentImageGenerationSetting
from app.runtime.social import image_generation as post_image_generation
from test_l4_social_write_uow import _session_factory


def test_local_image_request_uses_same_setting_and_counts_queued_jobs_without_ai(monkeypatch, tmp_path):
    factory = _session_factory(tmp_path)
    with factory() as db:
        setting = AgentImageGenerationSetting(
            character_id="social-uow-autonomous-character", image_key_mode="user",
            image_generation_enabled=True, max_images_per_day=1,
            pollinations_image_model="replicate-zimage-turbo-lora",
            encrypted_replicate_api_token="fixture", visual_identity_prompt="small blue bird",
            visual_identity_source_hash=None,
        )
        db.add(setting)
        db.add(Post(
            id="social-uow-second-post", author_user_id="social-uow-owner",
            author_character_id="social-uow-autonomous-character", world_id="social-uow-world",
            author_world_character_id="social-uow-autonomous-actor", post_type="post",
            visibility="public", author_name="Mango", title="Second", body="Second image scene",
        ))
        db.commit()
        character = db.get(Character, setting.character_id)
        reads, commits = [], []
        original = post_image_generation.agent_crud.get_image_generation_setting

        def get_setting(session, character_id):
            assert session is db
            result = original(session, character_id)
            assert result is setting and object_session(result) is db
            reads.append(character_id)
            return result

        def forbidden(**_kwargs):
            raise AssertionError("request admission must not call LLM or image provider")

        monkeypatch.setattr(post_image_generation.agent_crud, "get_image_generation_setting", get_setting)
        monkeypatch.setattr(image_identity, "_ensure_visual_identity", forbidden)
        monkeypatch.setattr(image_identity, "_refine_image_prompt", forbidden)
        monkeypatch.setattr(post_image_generation.image_provider, "generate_image", forbidden)
        event.listen(db, "before_commit", lambda *_: commits.append("commit"))
        args = dict(db=db, user_id="social-uow-owner", local_key_prefix="fixture",
                    character=character, post_id="social-uow-target-post",
                    image_prompt="a bird walking in the park", requested_at=datetime.now(UTC))
        first = post_image_generation.create_local_api_post_image_request(**args)
        assert isinstance(first, BotImageRequestRead) and first.status == "queued"
        second = post_image_generation.create_local_api_post_image_request(**{**args, "post_id": "social-uow-second-post"})
        assert second.status == "skipped" and second.skip_reason == "limit_exceeded"
        assert reads == [character.id, character.id]
        assert commits == ["commit", "commit"]
        jobs = list(db.scalars(select(PostImageGenerationJob).order_by(PostImageGenerationJob.id)))
        assert [(job.status, job.skip_reason) for job in jobs] == [("queued", None), ("skipped", "limit_exceeded")]
        assert first.job_id == jobs[0].id and second.job_id == jobs[1].id
