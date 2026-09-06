import asyncio
from types import SimpleNamespace

import pytest
from sqlalchemy import event
from sqlalchemy.orm import object_session

from app.domains.characters.models import Character
from app.models.agent_settings import AgentImageGenerationSetting
from app.runtime.social import image_generation as post_image_generation
from social.test_l4_social_write_uow import _session_factory


@pytest.mark.parametrize("rejected_payload", [
    {"usable_identity": False, "identity_prompt": "other bird"},
    {"usable_identity": True, "identity_prompt": " "},
    {"usable_identity": True, "identity_prompt": "x" * 1201},
], ids=["unusable", "empty", "invalid"])
def test_visual_identity_cache_and_rejection_preserve_same_session_write(
    monkeypatch, tmp_path, rejected_payload,
):
    factory = _session_factory(tmp_path)
    with factory() as db:
        setting = AgentImageGenerationSetting(
            character_id="social-uow-autonomous-character",
            visual_identity_prompt=None, visual_identity_source_hash=None,
        )
        db.add(setting)
        db.commit()
        character = db.get(Character, setting.character_id)
        credential, tracker = SimpleNamespace(), object()
        reference = post_image_generation._ReferenceImage(
            source="seed", url="/media/seed.webp", source_hash="first-hash",
            llm_part=object(), public_url=None,
        )
        commits, calls = [], []
        event.listen(db, "before_commit", lambda *_: commits.append("commit"))
        payload = {"usable_identity": True, "identity_prompt": "  small blue bird  "}

        async def generate(**kwargs):
            assert kwargs["character"] is character
            assert kwargs["credential"] is credential and kwargs["tracker"] is tracker
            assert kwargs["reference"] is reference
            assert object_session(setting) is db
            calls.append(reference.source_hash)
            return payload

        monkeypatch.setattr(post_image_generation, "_generate_visual_identity_payload", generate)
        args = dict(db=db, setting=setting, character=character, credential=credential,
                    reference=reference, tracker=tracker, run_id="fixture-run",
                    on_rate_limit_wait=None)
        assert asyncio.run(post_image_generation._ensure_visual_identity(**args)) == "small blue bird"
        assert setting.visual_identity_prompt == "small blue bird"
        assert setting.visual_identity_source_hash == "first-hash"
        assert object_session(setting) is db
        assert commits == ["commit"] and calls == ["first-hash"]
        with factory() as observer:
            persisted = observer.get(AgentImageGenerationSetting, setting.character_id)
            assert persisted.visual_identity_prompt == "small blue bird"
            assert persisted.visual_identity_source_hash == "first-hash"

        assert asyncio.run(post_image_generation._ensure_visual_identity(**args)) == "small blue bird"
        assert commits == ["commit"] and calls == ["first-hash"]

        reference = post_image_generation._ReferenceImage(
            source="seed", url="/media/other.webp", source_hash="second-hash",
            llm_part=object(), public_url=None,
        )
        payload = rejected_payload
        assert asyncio.run(post_image_generation._ensure_visual_identity(**{**args, "reference": reference})) is None
        assert setting.visual_identity_prompt == "small blue bird"
        assert setting.visual_identity_source_hash == "first-hash"
        assert commits == ["commit"] and calls == ["first-hash", "second-hash"]
        assert not db.is_modified(setting)
