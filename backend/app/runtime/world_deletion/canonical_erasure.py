"""Scoped canonical/file erasure, composed from frozen owner inventories.

Every page is journalled before its parents disappear. Only exact row/file
identities in that journal are purged. Account/Character erasure is not reused.
"""
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit
from sqlalchemy import and_, or_, delete, select, update, func, cast, String
from sqlalchemy.exc import IntegrityError
from app.core.ids import uuid7_string
from app.domains.worlds.models import World
from app.domains.worlds.models_deletion import WorldDeletionCleanupItem as Item
from app.domains.characters.service.import_snapshots import retained_import_media_urls
from app.runtime.world_deletion.inventory import ErasureInventory
from app.runtime.world_deletion.media_references import (
    DIRECT_REFERENCES, candidate_match, profile_image_urls, validate_reference_contract,
)


def stop_admission(db, world_id):
    from app.domains.world_characters.models import WorldCharacter
    db.execute(update(WorldCharacter).where(WorldCharacter.world_id == world_id).values(autonomous_enabled=False))
    from app.domains.routines.models import AgentSlot, AgentRun
    from app.domains.routines.constants import SLOT_STATUS_IDLE
    active_runs = select(AgentRun.id).where(AgentRun.status.in_(("running", "pending")))
    db.execute(update(AgentSlot).where(func.json_extract(AgentSlot.admission_metadata, "$._world_credential.world_id") == world_id,
        or_(AgentSlot.locked_by_run_id.is_(None), AgentSlot.locked_by_run_id.not_in(active_runs))).values(
        status=SLOT_STATUS_IDLE, locked_by_run_id=None, lease_expires_at=None, admission_metadata=None,
        assigned_character_id=None, assigned_credential_id=None, assigned_user_id=None, last_error=None))


class ScopedWorldErasure:
    def __init__(self, media_root, *, index_cleanup, graph_cleanup, checkpoint_cleanup=None):
        self.inventory = ErasureInventory()
        validate_reference_contract(self.inventory.tables)
        self.media_root = Path(media_root).resolve()
        self.index_cleanup, self.graph_cleanup = index_cleanup, graph_cleanup
        self.checkpoint_cleanup = checkpoint_cleanup
        self.order = tuple(sorted(self.inventory.rules))

    def close_result_admission(self, world_id):
        from app.runtime.received_results import close_world_results
        close_world_results(world_id, media_root=self.media_root)

    def _journal(self, db, request, kind, reference):
        encoded = json.dumps(reference, sort_keys=True, separators=(",", ":"), default=str)
        key = hashlib.sha256(encoded.encode()).hexdigest()
        if db.scalar(select(Item.id).where(Item.request_id == request.id, Item.kind == kind, Item.item_key == key)) is None:
            db.add(Item(id=uuid7_string(), request_id=request.id, kind=kind, item_key=key, reference=json.loads(encoded)))
            # Production sessions disable autoflush. A repeated reference in
            # this page must observe its first journal entry before insertion.
            db.flush()

    def _file(self, db, request, path):
        if path:
            # A replay must not replace the original identity with a newer file
            # occupying the same path. Old path-only journals remain retained.
            if db.scalar(select(Item.id).where(Item.request_id == request.id, Item.kind == "file",
                func.json_extract(Item.reference, "$.path") == path)) is not None:
                return
            from app.runtime.world_deletion.cleanup_effects import file_identity
            self._journal(db, request, "file", {"path": path, "generation": file_identity(self._safe_path(path))})

    def drain(self, db, world_id):
        from app.domains.chat.contracts.generation_lifecycle import ResponseRequestState, TERMINAL_STATES
        chat_active = tuple(state.value for state in ResponseRequestState if state not in TERMINAL_STATES and state.value != "accepted")
        for name, statuses in (("agent_runs", ("running", "pending")), ("chat_response_requests", chat_active),
            ("image_interpretations", ("running",)), ("post_image_generation_jobs", ("running",)),
            ("memory_batch_runs", ("running",)), ("memory_situation_runs", ("running",)),
            ("activity_graph_runs", ("running",)), ("activity_preparation_jobs", ("running",)),
            ("social_recommendation_preparations", ("running",)), ("world_character_setup_attempts", ("running",)),
            ("activity_beats", ("claimed",)), ("activity_event_consumptions", ("claimed",))):
            t = self.inventory.tables[name]
            field = t.c.get("status") if "status" in t.c else t.c.get("state")
            if field is not None and db.scalar(select(func.count()).select_from(t).where(
                self.inventory.predicate(name, world_id), field.in_(statuses))):
                return False
        # A timeout alone is not proof that an admitted public write settled.
        t = self.inventory.tables["agent_public_action_executions"]
        if "status" in t.c and db.scalar(select(func.count()).select_from(t).where(t.c.world_id == world_id,
            t.c.status.not_in(("succeeded", "failed", "skipped", "cancelled")))):
            return False
        return True

    def collect(self, db, request, limit):
        if request.cursor == 0:
            world = db.get(World, request.world_id)
            for url in (world.icon_media_id, world.banner_media_id):
                if url:
                    self._file(db, request, self._relative_url(url))
            self._journal(db, request, "graph", {"world_id": request.world_id})
            directory = self._safe_path("worlds/" + request.world_id)
            try:
                entries = directory.iterdir()
                added = 0
                for path in entries:
                    self._safe_path(path.relative_to(self.media_root).as_posix())
                    if not path.is_file():
                        raise ValueError("world_erasure_file_layout_unknown")
                    relative = path.relative_to(self.media_root).as_posix()
                    if not db.scalar(select(Item.id).where(Item.request_id == request.id, Item.kind == "file",
                        func.json_extract(Item.reference, "$.path") == relative)):
                        self._file(db, request, relative)
                        db.flush()
                        added += 1
                        if added == limit:
                            return False
            except FileNotFoundError:
                pass
        if request.cursor >= len(self.order):
            return True
        name = self.order[request.cursor]
        table = self.inventory.tables[name]
        # Idempotent pages use an exact PK anti-join, not offsets on shrinking data.
        recorded = select(Item.id).where(Item.request_id == request.id, Item.kind == "row",
            func.json_extract(Item.reference, "$.table") == name,
            *[func.json_extract(Item.reference, f"$.pk.{c.name}") == (cast(c,String) if db.get_bind().dialect.name=="postgresql" else c) for c in table.primary_key]).correlate(table).exists()
        rows = db.execute(select(table).where(self.inventory.predicate(name, request.world_id), ~recorded)
            .order_by(*table.primary_key).limit(limit)).mappings().all()
        for row in rows:
            self._journal(db, request, "row", {"table": name, "pk": {c.name: row[c.name] for c in table.primary_key}})
            if name == "memory_items":
                self._journal(db, request, "memory_index", {"item_id": row["id"]})
            if name == "activity_graph_runs":
                self._journal(db, request, "checkpoint", {"activity_id": row["activity_id"]})
            if name == "media_assets":
                self._file(db, request, "private-image-assets/" + row["storage_key"])
            for column in ("url", "media_url", "avatar_temp_url", "banner_temp_url"):
                if column in row and row[column]:
                    self._file(db, request, self._relative_url(row[column]))
            if name == "world_characters":
                self._journal(db, request, "origin", {"character_id": row["character_id"]})
                profile = row["local_profile"] or {}
                for column in ("avatar_url", "banner_url"):
                    self._file(db, request, self._relative_url(profile.get(column)))
            if name == "world_character_configurations":
                for column in ("avatar_url", "banner_url"):
                    self._file(db, request, self._relative_url((row["profile"] or {}).get(column)))
            if name == "image_interpretations":
                for suffix in (".json", ".tmp"):
                    self._file(db, request, f"private-image-assets/received-interpretations/{row['id']}{suffix}")
            if name == "post_image_generation_jobs":
                for suffix in (".json", ".pixels", ".json.tmp", ".pixels.tmp"):
                    self._file(db, request, f"private-image-assets/received-results/{row['id']}{suffix}")
        db.flush()
        if self.inventory.rules[name].get("preserve_lineage"):
            db.execute(update(Item).where(Item.request_id == request.id, Item.kind == "row",
                func.json_extract(Item.reference, "$.table") == name).values(state="retained"))
        if len(rows) < limit:
            request.cursor += 1
        return False

    def _relative_url(self, url):
        if not url:
            return None
        parts = urlsplit(url)
        if parts.netloc and parts.hostname not in {"localhost", "127.0.0.1", "::1"}:
            return None
        # External/Downloads/exported package paths are outside managed cleanup.
        return parts.path[len("/media/"):] if parts.path.startswith("/media/") else None

    def _pk(self, table, reference):
        from datetime import date
        clauses = []
        for key, value in reference["pk"].items():
            kind = table.c[key].type.python_type
            if kind in {date, datetime} and isinstance(value, str):
                value = kind.fromisoformat(value)
            clauses.append(table.c[key] == value)
        return and_(*clauses)

    def purge(self, db, request, limit):
        pending = list(db.scalars(select(Item).where(Item.request_id == request.id, Item.kind == "row", Item.state == "pending").limit(limit)))
        if not pending:
            self._finish_roots(db, request.world_id)
            return True
        progress = False
        # Reverse FK order is only a preference; exact FK enforcement is kept.
        ranks = {t.name: index for index, t in enumerate(self.inventory.tables.values())}
        pending.sort(key=lambda item: ranks[item.reference["table"]], reverse=True)
        for item in pending:
            table = self.inventory.tables[item.reference["table"]]
            try:
                with db.begin_nested():
                    self._prepare_row(db, table, item.reference)
                    db.execute(delete(table).where(self._pk(table, item.reference)))
                item.state = "done"
                progress = True
            except IntegrityError:
                try:
                    with db.begin_nested():
                        self._unlink_owned_references(db, table, item.reference, request.world_id)
                        db.execute(delete(table).where(self._pk(table, item.reference)))
                    item.state = "done"
                    progress = True
                except IntegrityError:
                    continue  # A child outside this page is erased in a later pass.
        if not progress:
            # Iterate the full pending table inventory in bounded pages rather
            # than repeatedly selecting the same obstructed parent page.
            request.cursor += limit
            later = db.scalars(select(Item).where(Item.request_id == request.id, Item.kind == "row", Item.state == "pending")
                .offset(request.cursor).limit(limit)).all()
            if not later:
                raise ValueError("world_erasure_dependency_unsettled")
            for item in later:
                table = self.inventory.tables[item.reference["table"]]
                try:
                    with db.begin_nested():
                        self._prepare_row(db, table, item.reference)
                        db.execute(delete(table).where(self._pk(table, item.reference)))
                    item.state = "done"
                    progress = True
                except IntegrityError:
                    try:
                        with db.begin_nested():
                            self._unlink_owned_references(db, table, item.reference, request.world_id)
                            db.execute(delete(table).where(self._pk(table, item.reference)))
                        item.state = "done"
                        progress = True
                    except IntegrityError:
                        continue
            if progress:
                request.cursor = 0
        else:
            request.cursor = 0
        return False

    def _unlink_owned_references(self, db, table, reference, world_id):
        """Break nullable target-owned FK cycles without disabling FK checks."""
        for fk in table.foreign_key_constraints:
            if fk.referred_table.name not in self.inventory.rules or not all(element.parent.nullable for element in fk.elements):
                continue
            target = fk.referred_table
            parent = select(*[element.column for element in fk.elements]).where(
                self.inventory.predicate(target.name, world_id))
            from sqlalchemy import tuple_
            db.execute(update(table).where(self._pk(table, reference),
                tuple_(*[element.parent for element in fk.elements]).in_(parent))
                .values(**{element.parent.name: None for element in fk.elements}))
    def _prepare_row(self, db, table, reference):
        if table.name == "agent_creation_drafts":
            # The registered card source belongs to the retained original, not
            # to the obsolete creation workspace. Unregistered cards are scoped
            # separately by the owning Characters cleanup policy.
            source = self.inventory.tables["character_card_sources"]
            db.execute(update(source).where(source.c.draft_id == reference["pk"]["id"],
                source.c.character_id.is_not(None)).values(draft_id=None))
            db.execute(delete(source).where(source.c.draft_id == reference["pk"]["id"], source.c.character_id.is_(None)))
        if table.name == "agent_runs":
            from app.domains.routines.constants import SLOT_STATUS_IDLE
            slots = self.inventory.tables["agent_slots"]
            db.execute(update(slots).where(slots.c.locked_by_run_id == reference["pk"]["id"]).values(
                locked_by_run_id=None, lease_expires_at=None, status=SLOT_STATUS_IDLE, assigned_credential_id=None,
                assigned_character_id=None, assigned_user_id=None, admission_metadata=None))

    def _finish_roots(self, db, world_id):
        # Preserve package lineage and immutable IDs without retaining definitions.
        world = db.get(World, world_id)
        world.slug = "deleted-" + world.id
        world.name = world.tagline = world.setting_description = world.daily_life_description = ""
        world.additional_generation_guidance = world.banner_alt_text = ""
        world.genre_tags = world.tone_tags = []
        world.icon_media_id = world.banner_media_id = None
        world.visibility, world.join_policy, world.status, world.readiness_status = "private", "private", "archived", "not_ready"
        world.contract_hash = "0" * 64
        world.timezone, world.language = "UTC", "und"
        if not world.create_idempotency_key.startswith("erased:"):
            world.create_idempotency_key = "erased:" + hashlib.sha256(world.create_idempotency_key.encode()).hexdigest()
        world.archived_at = datetime.now(UTC)

    def _safe_path(self, relative):
        if not relative or Path(relative).is_absolute() or ".." in Path(relative).parts:
            raise ValueError("world_erasure_path_invalid")
        lexical = self.media_root / relative
        for node in (lexical, *lexical.parents):
            if node == self.media_root:
                break
            if node.is_symlink() or node.is_junction():
                raise ValueError("world_erasure_path_link")
        path = lexical.resolve()
        if self.media_root not in path.parents:
            raise ValueError("world_erasure_path_outside_root")
        return path

    def _protected_files(self, db, request, candidates):
        """Keep exact managed files still referenced outside the erased scope."""
        if not candidates:
            return set()
        protected = {self._relative_url(url) for url in retained_import_media_urls(db, excluding_character_id="", candidate_paths=candidates)}
        affected = select(func.json_extract(Item.reference, "$.character_id")).where(
            Item.request_id == request.id, Item.kind == "origin")
        actors = self.inventory.tables["world_characters"]
        for name, fields in DIRECT_REFERENCES.items():
            table = self.inventory.tables[name]
            columns = [table.c[field] for field in fields]
            if columns:
                query = select(*columns).where(or_(*(candidate_match(column, candidates) for column in columns)))
                if table.name == "characters":
                    # Its mutable display cache is restored from the immutable
                    # origin later; it cannot retain the deleted World's edits.
                    query = query.where(or_(table.c.id.not_in(affected), table.c.id.in_(select(actors.c.character_id))))
                for urls in db.execute(query):
                    protected.update(self._relative_url(url) for url in urls if url)
        protected.update(self._relative_url(url) for url in profile_image_urls(db, self.inventory.tables, candidates))
        return protected.intersection(candidates)

    def verify(self, db, request):
        if db.scalar(select(func.count()).select_from(Item).where(Item.request_id == request.id, Item.state == "pending")):
            return False
        for name in self.order:
            if self.inventory.rules[name].get("preserve_lineage"):
                continue
            if db.scalar(select(func.count()).select_from(self.inventory.tables[name]).where(self.inventory.predicate(name, request.world_id))):
                raise ValueError("world_erasure_scope_not_empty")
        world = db.get(World, request.world_id)
        if any(getattr(world, key) for key in ("name", "tagline", "setting_description", "daily_life_description",
            "additional_generation_guidance", "banner_alt_text", "genre_tags", "tone_tags", "icon_media_id", "banner_media_id")):
            raise ValueError("world_erasure_root_not_scrubbed")
        return True
