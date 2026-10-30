"""Bind reviewed domain-owned scope policies to canonical SQL tables.

This adapter cannot infer new deletion policy from newly added foreign keys.
Unknown schema changes require an explicit inventory update and regression.
"""
import json
from pathlib import Path
from sqlalchemy import MetaData, and_, or_, select, literal, func
from app.models import Base


OWNERS = ("routines", "world_characters", "relationships", "characters", "memory", "chat", "social", "media", "identity", "worlds", "world_packages")


class ErasureInventory:
    def __init__(self, metadata=None, *, legacy_snapshot_schema=False):
        self.tables = (Base.metadata if metadata is None else metadata).tables
        root = Path(__file__).resolve().parents[2] / "domains"
        self.rules = {}
        for owner in OWNERS:
            payload = json.loads((root / owner / "repository/world_erasure.json").read_text(encoding="utf-8"))
            if payload["owner"] != owner or payload["version"] != 1:
                raise ValueError("world_erasure_inventory_invalid")
            self.rules.update(payload["tables"])
        if legacy_snapshot_schema or (metadata is not None and metadata.info.get("angmoo_frozen_sqlite")):
            from app.runtime.persistence.experience_migration import TABLES
            for name in TABLES-set(self.tables):
                self.rules.pop(name,None)
        if not set(self.rules).issubset(self.tables):
            raise ValueError("world_erasure_metadata_incomplete")

    @classmethod
    def for_connection(cls, connection):
        """Reflect the migration's actual generation, never current ORM columns.

        Current application metadata is supplied explicitly by create_all.
        A forward migration may still be on an older schema generation here.
        Reviewed owner rules determine scope; reflection cannot expand policy.
        """
        metadata = MetaData()
        metadata.reflect(bind=connection)
        return cls(metadata, legacy_snapshot_schema=connection.dialect.name == "sqlite")

    def predicate(self, name, world_id, *, table=None):
        t = self.tables[name] if table is None else table
        rule = self.rules[name]
        if "world_column" in rule:
            return t.c[rule["world_column"]] == world_id
        if rule.get("special") == "run_world":
            return or_(func.json_extract(t.c.input_snapshot, "$._world_credential.world_id") == world_id,
                t.c.post_id.in_(select(self.tables["posts"].c.id).where(self.tables["posts"].c.world_id == world_id)))
        if rule.get("special") == "media_scope":
            threads, actors = self.tables["message_threads"], self.tables["world_characters"]
            return or_(and_(t.c.scope_kind == "thread", t.c.scope_id.in_(select(threads.c.id).where(threads.c.world_id == world_id))),
                and_(t.c.scope_kind == "world_character", t.c.scope_id.in_(select(actors.c.id).where(actors.c.world_id == world_id))),
                and_(t.c.scope_kind == "world", t.c.scope_id == world_id))
        # Owning memory scope wins over provenance references to a different World.
        joins = rule["joins"]
        if name.startswith("memory_"):
            preferred = [join for join in joins if join["target_table"] == "memory_scope_settings"]
            if name == "memory_item_evidence":
                preferred = [join for join in joins if join["target_table"] == "memory_items"]
            joins = preferred or joins
        terms = []
        for join in joins:
            target = self.tables[join["target_table"]].alias()
            terms.append(select(literal(1)).select_from(target).where(
                self.predicate(join["target_table"], world_id, table=target),
                *[t.c[src] == target.c[dst] for src, dst in zip(join["columns"], join["target_columns"], strict=True)]).correlate(t).exists())
        return or_(*terms)
