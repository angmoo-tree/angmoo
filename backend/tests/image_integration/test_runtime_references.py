import asyncio
from datetime import datetime, timedelta, timezone
import hashlib
from types import SimpleNamespace
import pytest
from sqlalchemy import select
from app.domains.characters.models import Character, AgentImageGenerationSetting, CharacterCardSource, AgentCreationDraft
from app.domains.media.models import MediaAsset
from app.domains.media.generation_contracts import ImagePreparationError
from image_integration.test_generation_lifecycle import configured, admit, OWNER, CHARACTER
from image_integration.test_providers import png


def test_reference_priority_card_pixels_override_profile_and_missing(tmp_path):
    sessions, media, _ = configured(tmp_path)
    media.settings.media_url_path="/media"
    with sessions() as db:
        character=db.get(Character,CHARACTER);setting=db.get(AgentImageGenerationSetting,CHARACTER)
        character.avatar_url="/media/characters/profile.png"
        path=media.settings.media_root_path/"characters/profile.png";path.parent.mkdir(parents=True);path.write_bytes(png())
        assert media._reference(db,OWNER,character,setting,True).source=="profile"
        source=png()
        db.add(AgentCreationDraft(id="image-card-draft",user_id=OWNER,model="synthetic",expires_at=datetime.now(timezone.utc)+timedelta(days=1)))
        db.flush()
        card=CharacterCardSource(id="image-card",owner_id=OWNER,draft_id="image-card-draft",character_id=CHARACTER,
            source_bytes=source,source_sha256=hashlib.sha256(source).hexdigest(),source_format="png",parser_version="synthetic",card_version=2)
        db.add(card);db.flush()
        reference=media._reference(db,OWNER,character,setting,True)
        assert reference.source=="card" and reference.revision==1
        asset=media.assets.upload(db,owner_id=OWNER,scope_kind="character",scope_id=CHARACTER,content_type="image/png",content=png(),draft=False)
        setting.reference_asset_id=asset.id
        assert media._reference(db,OWNER,character,setting,True).source=="override"
        media.assets.path(asset).write_bytes(b"corrupt selected pixels")
        with pytest.raises(Exception,match="content_changed"):
            media._reference(db,OWNER,character,setting,True)
        setting.reference_asset_id=None;db.delete(card);db.flush()
        character.avatar_url=None
        assert media._reference(db,OWNER,character,setting,True).reason=="source_missing"


def test_reference_revision_changed_after_admission_prevents_physical_request(tmp_path):
    sessions, media, fake=configured(tmp_path)
    with sessions() as db:
        setting=db.get(AgentImageGenerationSetting,CHARACTER)
        asset=media.assets.upload(db,owner_id=OWNER,scope_kind="character",scope_id=CHARACTER,content_type="image/png",content=png(),draft=False)
        setting.reference_asset_id=asset.id;db.commit();identity=asset.id
    job=admit(sessions,media)
    with sessions() as db:
        db.get(MediaAsset,identity).revision+=1;db.commit()
    asyncio.run(media.worker.process(job))
    assert fake.calls==0


def test_lifespan_maintenance_start_stop_is_idempotent_and_unregisters(tmp_path):
    from app.runtime.media import binding
    _, media, _=configured(tmp_path)
    async def run():
        await media.start();task=media._maintenance_task
        await media.start();assert media._maintenance_task is task
        await media.stop();assert task.done() and media._maintenance_task is None
        await media.stop()
        assert binding.current() is None
    asyncio.run(run())
