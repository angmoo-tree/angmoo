from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

PollinationsFreeImageModel = Literal["flux", "zimage", "sana", "replicate-zimage-turbo-lora"]


PollinationsImageRouteMode = Literal["direct", "lambda"]


SettingSource = Literal["db", "env", "default"]


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
