"""World/Character/Package reads on the activity caller's existing Session."""
from __future__ import annotations

from sqlalchemy import inspect, select
from sqlalchemy.engine.reflection import Inspector
from sqlalchemy.orm import Session

from app.domains.world_characters.models import CharacterActiveWorld, WorldCharacter
from app.domains.world_packages.models import WorldPackageImport
from app.domains.worlds.models import World


class SqlAlchemyActivityScopeReads:
    def __init__(self, db: Session):
        self.db = db
        self._inspector: Inspector | None = None

    def _table_exists(self, name: str) -> bool:
        if self._inspector is None:
            self._inspector = inspect(self.db.get_bind())
        return self._inspector.has_table(name)

    def has_active_world_table(self) -> bool:
        return self._table_exists(CharacterActiveWorld.__tablename__)

    def has_world_character_table(self) -> bool:
        return self._table_exists(WorldCharacter.__tablename__)

    def has_world_table(self) -> bool:
        return self._table_exists(World.__tablename__)

    def has_import_table(self) -> bool:
        return self._table_exists(WorldPackageImport.__tablename__)

    def get_active_world(self, character_id: str) -> CharacterActiveWorld | None:
        return self.db.get(CharacterActiveWorld, character_id)

    def get_world_character(self, world_character_id: str) -> WorldCharacter | None:
        return self.db.get(WorldCharacter, world_character_id)

    def get_world(self, world_id: str) -> World | None:
        return self.db.get(World, world_id)

    def get_import_id(self, world_id: str) -> str | None:
        return self.db.scalar(
            select(WorldPackageImport.import_id)
            .where(WorldPackageImport.imported_world_id == world_id)
            .limit(1)
        )

    def get_latest_imported_world_character(self, character_id: str) -> WorldCharacter | None:
        return self.db.scalar(
            select(WorldCharacter)
            .join(
                WorldPackageImport,
                WorldPackageImport.imported_world_id == WorldCharacter.world_id,
            )
            .where(WorldCharacter.character_id == character_id)
            .order_by(WorldCharacter.created_at.desc())
            .limit(1)
        )
