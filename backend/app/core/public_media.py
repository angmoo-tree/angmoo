from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.core.config import settings


PUBLIC_MEDIA_DIRECTORIES = ("characters", "posts")


def mount_public_media(app: FastAPI) -> None:
    for directory_name in PUBLIC_MEDIA_DIRECTORIES:
        directory = settings.media_root_path / directory_name
        directory.mkdir(parents=True, exist_ok=True)
        app.mount(
            f"{settings.media_url_path}/{directory_name}",
            StaticFiles(directory=directory),
            name=f"media-{directory_name}",
        )
