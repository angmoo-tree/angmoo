from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.core.config import Settings, settings


PUBLIC_MEDIA_DIRECTORIES = ("characters", "posts")


def mount_public_media(
    app: FastAPI,
    config: Settings = settings,
    *,
    prepare_directories: bool = True,
) -> None:
    for directory_name in PUBLIC_MEDIA_DIRECTORIES:
        directory = config.media_root_path / directory_name
        if prepare_directories:
            directory.mkdir(parents=True, exist_ok=True)
        app.mount(
            f"{config.media_url_path}/{directory_name}",
            StaticFiles(directory=directory, check_dir=prepare_directories),
            name=f"media-{directory_name}",
        )
