from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.core.config import Settings, settings


PUBLIC_MEDIA_DIRECTORIES = ("characters", "posts")


def mount_public_media(app: FastAPI, config: Settings = settings) -> None:
    for directory_name in PUBLIC_MEDIA_DIRECTORIES:
        directory = config.media_root_path / directory_name
        directory.mkdir(parents=True, exist_ok=True)
        app.mount(
            f"{config.media_url_path}/{directory_name}",
            StaticFiles(directory=directory),
            name=f"media-{directory_name}",
        )
