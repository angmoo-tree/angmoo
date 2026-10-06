"""Composition boundary for World management concrete read/write collaborators."""
from fastapi import Depends
from app.database import get_db


def get_management_service(db=Depends(get_db)):
    from app.runtime.world_characters.management import management_service
    return management_service(db)


def profile_media_workflow():
    from app.runtime.world_characters.profile_media import upload_profile_media
    return upload_profile_media


def manual_activity_workflow():
    from app.runtime.world_characters.manual_activity import run_world_character_now
    from app.runtime.characters.management import build_manual_activity_workflows

    async def run(service, **kwargs):
        return await run_world_character_now(service, workflows=build_manual_activity_workflows(), **kwargs)

    return run
