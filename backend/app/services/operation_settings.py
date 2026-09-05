from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from sqlalchemy.orm import Session

from app import models
from app.config import settings


PollinationsFreeImageModel = Literal["flux", "zimage", "sana", "replicate-zimage-turbo-lora"]
PollinationsImageRouteMode = Literal["direct", "lambda"]
SettingSource = Literal["db", "env", "default"]

POLLINATIONS_FREE_IMAGE_MODEL_KEY = "pollinations_free_image_model"
DEFAULT_POLLINATIONS_FREE_IMAGE_MODEL: PollinationsFreeImageModel = "flux"
POLLINATIONS_FREE_IMAGE_MODEL_LABELS: dict[PollinationsFreeImageModel, str] = {
    "flux": "Pollinations · Flux Schnell",
    "zimage": "Pollinations · Z-Image Turbo",
    "sana": "Pollinations · Sana Sprint 1.6B",
    "replicate-zimage-turbo-lora": "Replicate · Z-Image Turbo LoRA",
}
POLLINATIONS_IMAGE_ROUTE_MODE_KEY = "pollinations_image_route_mode"
DEFAULT_POLLINATIONS_IMAGE_ROUTE_MODE: PollinationsImageRouteMode = "direct"
POLLINATIONS_IMAGE_ROUTE_MODE_LABELS: dict[PollinationsImageRouteMode, str] = {
    "lambda": "Lambda relay",
    "direct": "Direct",
}
POLLINATIONS_PROFILE_IMAGE_MODEL_KEY = "pollinations_profile_image_model"
DEFAULT_POLLINATIONS_PROFILE_IMAGE_MODEL: PollinationsFreeImageModel = "zimage"
POLLINATIONS_PROFILE_IMAGE_ROUTE_MODE_KEY = "pollinations_profile_image_route_mode"
DEFAULT_POLLINATIONS_PROFILE_IMAGE_ROUTE_MODE: PollinationsImageRouteMode = "lambda"


@dataclass(frozen=True)
class PollinationsFreeImageModelSetting:
    model: PollinationsFreeImageModel
    updated_by_user_id: str | None
    updated_at: datetime | None


@dataclass(frozen=True)
class PollinationsImageRouteModeSetting:
    mode: PollinationsImageRouteMode
    source: SettingSource
    updated_by_user_id: str | None
    updated_at: datetime | None


@dataclass(frozen=True)
class PollinationsProfileImageModelSetting:
    model: PollinationsFreeImageModel
    source: SettingSource
    updated_by_user_id: str | None
    updated_at: datetime | None


@dataclass(frozen=True)
class PollinationsProfileImageRouteModeSetting:
    mode: PollinationsImageRouteMode
    source: SettingSource
    updated_by_user_id: str | None
    updated_at: datetime | None


def normalize_pollinations_free_image_model(
    value: str | None,
) -> PollinationsFreeImageModel | None:
    normalized = (value or "").strip()
    if normalized in POLLINATIONS_FREE_IMAGE_MODEL_LABELS:
        return normalized  # type: ignore[return-value]
    return None


def normalize_pollinations_image_route_mode(
    value: str | None,
) -> PollinationsImageRouteMode | None:
    normalized = (value or "").strip().lower()
    if normalized in POLLINATIONS_IMAGE_ROUTE_MODE_LABELS:
        return normalized  # type: ignore[return-value]
    return None


def get_pollinations_free_image_model(db: Session | None = None) -> PollinationsFreeImageModel:
    return get_pollinations_free_image_model_setting(db).model


def get_pollinations_free_image_model_setting(
    db: Session | None = None,
) -> PollinationsFreeImageModelSetting:
    if db is not None and hasattr(db, "get"):
        row = db.get(models.SiteOperationSetting, POLLINATIONS_FREE_IMAGE_MODEL_KEY)
        model = normalize_pollinations_free_image_model(row.value if row is not None else None)
        if model is not None:
            return PollinationsFreeImageModelSetting(
                model=model,
                updated_by_user_id=row.updated_by_user_id,
                updated_at=row.updated_at,
            )

    env_model = normalize_pollinations_free_image_model(
        settings.pollinations_service_image_model
    )
    return PollinationsFreeImageModelSetting(
        model=env_model or DEFAULT_POLLINATIONS_FREE_IMAGE_MODEL,
        updated_by_user_id=None,
        updated_at=None,
    )


def get_pollinations_image_route_mode(
    db: Session | None = None,
) -> PollinationsImageRouteMode:
    return get_pollinations_image_route_mode_setting(db).mode


def get_pollinations_image_route_mode_setting(
    db: Session | None = None,
) -> PollinationsImageRouteModeSetting:
    if db is not None and hasattr(db, "get"):
        row = db.get(models.SiteOperationSetting, POLLINATIONS_IMAGE_ROUTE_MODE_KEY)
        mode = normalize_pollinations_image_route_mode(row.value if row is not None else None)
        if mode is not None:
            return PollinationsImageRouteModeSetting(
                mode=mode,
                source="db",
                updated_by_user_id=row.updated_by_user_id,
                updated_at=row.updated_at,
            )

    env_mode = normalize_pollinations_image_route_mode(settings.POLLINATIONS_IMAGE_ROUTE_MODE)
    if env_mode is not None:
        return PollinationsImageRouteModeSetting(
            mode=env_mode,
            source="env",
            updated_by_user_id=None,
            updated_at=None,
        )
    return PollinationsImageRouteModeSetting(
        mode=DEFAULT_POLLINATIONS_IMAGE_ROUTE_MODE,
        source="default",
        updated_by_user_id=None,
        updated_at=None,
    )


def get_pollinations_profile_image_model(
    db: Session | None = None,
) -> PollinationsFreeImageModel:
    return get_pollinations_profile_image_model_setting(db).model


def get_pollinations_profile_image_model_setting(
    db: Session | None = None,
) -> PollinationsProfileImageModelSetting:
    if db is not None and hasattr(db, "get"):
        row = db.get(models.SiteOperationSetting, POLLINATIONS_PROFILE_IMAGE_MODEL_KEY)
        model = normalize_pollinations_free_image_model(row.value if row is not None else None)
        if model is not None:
            return PollinationsProfileImageModelSetting(
                model=model,
                source="db",
                updated_by_user_id=row.updated_by_user_id,
                updated_at=row.updated_at,
            )

    env_model = normalize_pollinations_free_image_model(
        settings.pollinations_profile_image_model
    )
    if env_model is not None:
        return PollinationsProfileImageModelSetting(
            model=env_model,
            source="env",
            updated_by_user_id=None,
            updated_at=None,
        )
    return PollinationsProfileImageModelSetting(
        model=DEFAULT_POLLINATIONS_PROFILE_IMAGE_MODEL,
        source="default",
        updated_by_user_id=None,
        updated_at=None,
    )


def get_pollinations_profile_image_route_mode(
    db: Session | None = None,
) -> PollinationsImageRouteMode:
    return get_pollinations_profile_image_route_mode_setting(db).mode


def get_pollinations_profile_image_route_mode_setting(
    db: Session | None = None,
) -> PollinationsProfileImageRouteModeSetting:
    if db is not None and hasattr(db, "get"):
        row = db.get(models.SiteOperationSetting, POLLINATIONS_PROFILE_IMAGE_ROUTE_MODE_KEY)
        mode = normalize_pollinations_image_route_mode(row.value if row is not None else None)
        if mode is not None:
            return PollinationsProfileImageRouteModeSetting(
                mode=mode,
                source="db",
                updated_by_user_id=row.updated_by_user_id,
                updated_at=row.updated_at,
            )

    env_mode = normalize_pollinations_image_route_mode(
        settings.pollinations_profile_image_route_mode
    )
    if env_mode is not None:
        return PollinationsProfileImageRouteModeSetting(
            mode=env_mode,
            source="env",
            updated_by_user_id=None,
            updated_at=None,
        )
    return PollinationsProfileImageRouteModeSetting(
        mode=DEFAULT_POLLINATIONS_PROFILE_IMAGE_ROUTE_MODE,
        source="default",
        updated_by_user_id=None,
        updated_at=None,
    )


def pollinations_free_image_model_options() -> list[dict[str, str]]:
    return [
        {"model": model, "label": label}
        for model, label in POLLINATIONS_FREE_IMAGE_MODEL_LABELS.items()
    ]


def pollinations_free_image_model_label(model: str) -> str:
    normalized = normalize_pollinations_free_image_model(model)
    if normalized is None:
        return model
    return POLLINATIONS_FREE_IMAGE_MODEL_LABELS[normalized]


def pollinations_image_route_mode_options() -> list[dict[str, str]]:
    return [
        {"mode": mode, "label": label}
        for mode, label in POLLINATIONS_IMAGE_ROUTE_MODE_LABELS.items()
    ]


def pollinations_image_route_mode_label(mode: str) -> str:
    normalized = normalize_pollinations_image_route_mode(mode)
    if normalized is None:
        return mode
    return POLLINATIONS_IMAGE_ROUTE_MODE_LABELS[normalized]
