"""Read-only identity/World/membership projection using the caller Session."""
from __future__ import annotations

import base64
import binascii
from datetime import datetime
import json
from typing import cast

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.domains.device_home.contracts import (
    WorldMembershipRole,
    WorldSurface,
    WorldSurfaceItem,
    WorldSurfacePage,
)

from app.domains.device_home.exceptions import InvalidWorldSurfaceCursorError
from app.domains.device_home.policies import launchability


LOCAL_INSTALLATION_KEY = "local-installation"


class SqlAlchemyWorldSurfaceRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def is_local_owner(self, user_id: str) -> bool:
        row = self._db.execute(
            text(
                """
                SELECT owner_user_id, bootstrap_state
                FROM installation_identities
                WHERE singleton_key = :installation_key
                """
            ),
            {"installation_key": LOCAL_INSTALLATION_KEY},
        ).mappings().one_or_none()
        return bool(
            row
            and row["bootstrap_state"] == "claimed"
            and row["owner_user_id"] == user_id
        )

    def get_world(
        self,
        *,
        owner_user_id: str,
        world_id: str,
    ) -> WorldSurfaceItem | None:
        row = self._db.execute(
            text(
                """
                SELECT
                    w.id AS world_id,
                    w.name,
                    w.tagline,
                    w.banner_media_id,
                    w.banner_alt_text,
                    w.status,
                    w.visibility,
                    w.readiness_status,
                    w.updated_at,
                    wm.role AS membership_role
                FROM worlds AS w
                JOIN world_memberships AS wm
                    ON wm.world_id = w.id
                    AND wm.user_id = :owner_user_id
                    AND wm.status = 'active'
                WHERE w.id = :world_id
                LIMIT 1
                """
            ),
            {
                "owner_user_id": owner_user_id,
                "world_id": world_id,
            },
        ).mappings().one_or_none()
        return _surface_item(row) if row is not None else None

    def list_worlds(
        self,
        *,
        owner_user_id: str,
        surface: WorldSurface,
        limit: int,
        cursor: str | None,
    ) -> WorldSurfacePage:
        cursor_updated_at, cursor_world_id = _decode_cursor(cursor)
        where = [
            "wm.user_id = :owner_user_id",
            "wm.status = 'active'",
        ]
        if surface == "device_home":
            where.extend(
                [
                    "w.status = 'published'",
                    "w.readiness_status = 'publish_ready'",
                    "w.visibility IN ('public', 'unlisted')",
                ]
            )
        else:
            where.append("wm.role IN ('owner', 'editor')")
        parameters: dict[str, object] = {
            "owner_user_id": owner_user_id,
            "fetch_limit": limit + 1,
        }
        if cursor_updated_at is not None and cursor_world_id is not None:
            where.append(
                "(w.updated_at < :cursor_updated_at OR "
                "(w.updated_at = :cursor_updated_at AND w.id > :cursor_world_id))"
            )
            parameters.update(
                {
                    "cursor_updated_at": cursor_updated_at,
                    "cursor_world_id": cursor_world_id,
                }
            )
        rows = self._db.execute(
            text(
                f"""
                SELECT
                    w.id AS world_id,
                    w.name,
                    w.tagline,
                    w.banner_media_id,
                    w.banner_alt_text,
                    w.status,
                    w.visibility,
                    w.readiness_status,
                    w.updated_at,
                    wm.role AS membership_role
                FROM worlds AS w
                JOIN world_memberships AS wm ON wm.world_id = w.id
                WHERE {' AND '.join(where)}
                ORDER BY w.updated_at DESC, w.id ASC
                LIMIT :fetch_limit
                """
            ),
            parameters,
        ).mappings().all()
        visible_rows = rows[:limit]
        items = tuple(_surface_item(row) for row in visible_rows)
        next_cursor = None
        if len(rows) > limit and visible_rows:
            last = visible_rows[-1]
            next_cursor = _encode_cursor(last["updated_at"], str(last["world_id"]))
        return WorldSurfacePage(
            surface=surface,
            items=items,
            next_cursor=next_cursor,
        )


def _surface_item(row) -> WorldSurfaceItem:
    can_launch, block_reason = launchability(
        status=str(row["status"]),
        visibility=str(row["visibility"]),
        readiness_status=str(row["readiness_status"]),
    )
    updated_at = row["updated_at"]
    if isinstance(updated_at, str):
        updated_at = datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
    return WorldSurfaceItem(
        world_id=str(row["world_id"]),
        name=str(row["name"]),
        tagline=str(row["tagline"]),
        banner_media_id=(
            str(row["banner_media_id"]) if row["banner_media_id"] else None
        ),
        banner_alt_text=str(row["banner_alt_text"]),
        status=str(row["status"]),
        visibility=str(row["visibility"]),
        readiness_status=str(row["readiness_status"]),
        membership_role=cast(WorldMembershipRole, str(row["membership_role"])),
        updated_at=updated_at,
        launchable=can_launch,
        launch_block_reason=block_reason,
    )


def _encode_cursor(updated_at: datetime | str, world_id: str) -> str:
    timestamp = updated_at.isoformat() if isinstance(updated_at, datetime) else updated_at
    payload = json.dumps(
        {"updated_at": timestamp, "world_id": world_id},
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")


def _decode_cursor(cursor: str | None) -> tuple[str | None, str | None]:
    if cursor is None:
        return None, None
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        value = json.loads(base64.urlsafe_b64decode(padded).decode("utf-8"))
        updated_at = value["updated_at"]
        world_id = value["world_id"]
        if not isinstance(updated_at, str) or not isinstance(world_id, str):
            raise TypeError
        datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
        if not world_id:
            raise ValueError
        return updated_at, world_id
    except (
        binascii.Error,
        json.JSONDecodeError,
        KeyError,
        TypeError,
        UnicodeDecodeError,
        ValueError,
    ) as exc:
        raise InvalidWorldSurfaceCursorError() from exc
