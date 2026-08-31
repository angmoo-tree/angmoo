"""Shared stable profile reference used by public HTTP contracts."""

from typing import Literal

from pydantic import BaseModel


class ProfileRef(BaseModel):
    profile_type: Literal["user", "character"]
    id: str
    display_name: str
    handle: str | None = None
    avatar_url: str | None = None
    banner_url: str | None = None


__all__ = ["ProfileRef"]
