"""Frozen v28 origin/configuration transition. Existing tables remain byte-for-byte."""
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4
from sqlalchemy import text
from urllib.parse import urlsplit
from app.runtime.migrations.sqlite_versions.contracts import SqliteMigrationDeltaError

NEW_TABLES = frozenset(("character_import_snapshots", "character_import_origins", "character_draft_import_origins", "world_character_configurations"))
MUTABLE_IDENTITY_TABLES = NEW_TABLES | {"agent_slots", "agent_runs"}
PERSONA_FIELDS = ("personality", "speech_style", "worldview", "character_background", "topic_preferences", "safety_rules")
ACTIVITY_DEFAULTS = {"active_hours_start": "09:00", "active_hours_end": "02:00", "activity_interval_minutes": 60,
    "max_posts_per_day": 30, "max_comments_per_day": 30, "allow_post": True, "allow_reply": True,
    "allow_like": True, "allow_repost": True, "allow_follow": True, "allow_unfollow": True}


def _json(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str)


def _digest(value):
    return hashlib.sha256(_json(value).encode()).hexdigest()


def capture_delta(connection):
    tables = [row[0] for row in connection.exec_driver_sql("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'") if row[0] not in NEW_TABLES and row[0] != "angmoo_schema_version"]
    return {name: {"columns": [row[1] for row in connection.exec_driver_sql(f'PRAGMA table_info("{name}")')],
        "digest": _digest(sorted([tuple(row) for row in connection.exec_driver_sql(f'SELECT * FROM "{name}"')], key=repr))} for name in tables}


def verify_delta(connection, before):
    for name, saved in before.items():
        columns = ','.join(f'"{column}"' for column in saved["columns"])
        after = _digest(sorted([tuple(row) for row in connection.exec_driver_sql(f'SELECT {columns} FROM "{name}"')], key=repr))
        if saved["digest"] != after:
            raise SqliteMigrationDeltaError("world_configuration_original_changed")
    if connection.exec_driver_sql("SELECT count(*) FROM agent_slots WHERE admission_metadata IS NOT NULL").scalar_one() or connection.exec_driver_sql("SELECT count(*) FROM agent_runs WHERE input_snapshot IS NOT NULL").scalar_one():
        raise SqliteMigrationDeltaError("world_configuration_rewrote_admitted_input")
    if connection.exec_driver_sql("SELECT count(*) FROM characters c LEFT JOIN character_import_origins o ON o.character_id=c.id WHERE o.character_id IS NULL").scalar_one():
        raise SqliteMigrationDeltaError("world_configuration_origin_missing")
    if connection.exec_driver_sql("SELECT count(*) FROM world_characters w LEFT JOIN world_character_configurations c ON c.world_character_id=w.id WHERE c.world_character_id IS NULL").scalar_one():
        raise SqliteMigrationDeltaError("world_configuration_role_missing")


def _current_payload(character, activity, image):
    def public_media(value):
        # Frozen migration admission: never copy an embedded credential/token.
        if not value or not isinstance(value, str) or "\\" in value or any(ord(c) < 32 for c in value):
            return None
        parts = urlsplit(value)
        if parts.username or parts.password or parts.query or parts.fragment or ".." in parts.path.split("/"):
            return None
        if (not parts.scheme and not parts.netloc and parts.path.startswith("/media/")) or (parts.scheme == "https" and parts.hostname):
            return value
        return None
    profile = {"display_name": character["name"], "handle": character["handle"], "avatar_url": public_media(character["avatar_url"]),
        "banner_url": public_media(character["banner_url"]), "intro": character["one_liner"] or ""}
    settings = {name: character.get(name) or "" for name in PERSONA_FIELDS}
    settings.update({name: activity.get(name, default) for name, default in ACTIVITY_DEFAULTS.items()})
    settings.update(generation_model=None, image_model=image.get("generation_model"),
        image_style=image.get("style_prompt") or "", appearance_prompt=image.get("appearance_prompt") or "")
    return {"profile": profile, "settings": settings}


def backfill(connection):
    """Called only by a formal transition; no GET/copy path invokes this function."""
    if connection.dialect.name == "postgresql":
        # A single confirmed source revision while copying typed configuration.
        connection.exec_driver_sql("LOCK TABLE characters, agent_activity_settings, agent_image_generation_settings, llm_credentials, world_characters, agent_creation_drafts, character_registration_receipts IN SHARE ROW EXCLUSIVE MODE")
    characters = list(connection.execute(text("SELECT * FROM characters")).mappings())
    activity = {row["character_id"]: dict(row) for row in connection.execute(text("SELECT * FROM agent_activity_settings")).mappings()}
    images = {row["character_id"]: dict(row) for row in connection.execute(text("SELECT * FROM agent_image_generation_settings")).mappings()}
    models = {row["character_id"]: row["model"] for row in connection.execute(text("SELECT character_id,model FROM llm_credentials WHERE enabled=true AND character_id IS NOT NULL")).mappings()}
    origins = {row["character_id"]: row["snapshot_id"] for row in connection.execute(text("SELECT * FROM character_import_origins")).mappings()}
    receipts = {row["character_id"]: dict(row) for row in connection.execute(text("SELECT * FROM character_registration_receipts")).mappings()}
    drafts = {row["id"]: dict(row) for row in connection.execute(text("SELECT * FROM agent_creation_drafts")).mappings()}
    effective = {}
    captured = datetime.now(UTC).isoformat()
    for character in characters:
        cid = character["id"]
        current = _current_payload(character, activity.get(cid, {}), images.get(cid, {}))
        current["settings"]["generation_model"] = models.get(cid)
        effective[cid] = current
        if cid in origins:
            continue
        payload, kind, provenance = current, "legacy_transition", "v28:confirmed_source_configuration"
        receipt = receipts.get(cid)
        draft = drafts.get(receipt["draft_id"]) if receipt else None
        # The completed receipt proves the immutable creation input. Promoted
        # image filenames were random, so absent original media is the only
        # historical media case this transition can prove without guessing.
        if draft and draft["status"] == "completed" and draft["source_kind"] == "direct" and not draft.get("avatar_temp_url") and not draft.get("banner_temp_url"):
            initial = _current_payload(character, {}, {})
            initial["profile"].update(display_name=draft["name"].strip(), handle=draft.get("handle") or f"angmoo_{cid.replace('-', '')}",
                intro=draft.get("one_liner") or "", avatar_url=None, banner_url=None)
            initial["settings"].update({name: draft.get(name) or "" for name in PERSONA_FIELDS})
            payload, kind, provenance = initial, "restored_initial", f"completed_registration:{draft['id']}"
        sid = str(uuid4())
        connection.execute(text("INSERT INTO character_import_snapshots (id,source_character_id,kind,contract_version,source_revision,provenance,payload,digest,captured_at) VALUES (:id,:source,:kind,1,:revision,:provenance,:payload,:digest,:captured)"),
            {"id": sid, "source": cid, "kind": kind, "revision": f"registration:{draft['revision']}" if kind == "restored_initial" else f"transition:{character.get('updated_at') or character['created_at']}",
             "provenance": provenance, "payload": _json(payload), "digest": _digest(payload), "captured": captured})
        connection.execute(text("INSERT INTO character_import_origins (character_id,snapshot_id) VALUES (:character,:snapshot)"), {"character": cid, "snapshot": sid})
        origins[cid] = sid
    configured = set(connection.execute(text("SELECT world_character_id FROM world_character_configurations")).scalars())
    for role in connection.execute(text("SELECT * FROM world_characters")).mappings():
        if role["id"] in configured:
            continue
        payload = effective[role["character_id"]]
        profile = dict(payload["profile"])
        local = json.loads(role["local_profile"]) if isinstance(role["local_profile"], str) else role["local_profile"] or {}
        # Presence, not truthiness: an explicit blank intro/null photograph is
        # a saved World removal and cannot be revived from the source.
        for name in profile:
            if name in local:
                profile[name] = local[name]
        connection.execute(text("INSERT INTO world_character_configurations (world_character_id,snapshot_id,profile,settings,updated_at) VALUES (:role,:snapshot,:profile,:settings,:captured)"),
            {"role": role["id"], "snapshot": origins[role["character_id"]], "profile": _json(profile), "settings": _json(payload["settings"]), "captured": captured})


def upgrade(connection):
    connection.exec_driver_sql("ALTER TABLE agent_slots ADD COLUMN admission_metadata JSON")
    connection.exec_driver_sql("ALTER TABLE agent_runs ADD COLUMN input_snapshot JSON")
    ddl = json.loads(Path(__file__).with_name("world_configuration_v28_ddl.json").read_text(encoding="utf-8"))
    for table in ("character_import_snapshots", "character_import_origins", "character_draft_import_origins", "world_character_configurations"):
        connection.exec_driver_sql(ddl[table]["create"])
        for index in ddl[table]["indexes"]:
            connection.exec_driver_sql(index)
    backfill(connection)
