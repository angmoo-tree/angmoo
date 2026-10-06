"""Forward transition to independent actor settings, preserving historical work.

Only a uniquely bound actor key can be retained. Its original AAD is preserved
and authenticated by the runtime-injected interpreter before staging promotion.
No global/foreign-purpose key or cap is duplicated and no provider is called.
"""
from collections import Counter
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import UTC, datetime
from hashlib import sha256
import json
from pathlib import Path
from uuid import uuid4

from sqlalchemy import inspect, text

from app.runtime.migrations.sqlite_versions.contracts import SqliteMigrationDeltaError

NEW_TABLES = frozenset(("world_credentials", "world_credential_revisions", "world_image_policies", "world_image_attempts",
    "memory_subject_profiles", "memory_index_preparations", "memory_episode_restrictions"))
MUTABLE_IDENTITY_TABLES = NEW_TABLES | {"memory_batch_runs"}
_interpreter = ContextVar("world_activity_secret_interpreter", default=None)


@contextmanager
def secret_interpreter(callback):
    token = _interpreter.set(callback)
    try:
        yield
    finally:
        _interpreter.reset(token)


def _digest(connection, table, columns):
    rows = list(connection.exec_driver_sql(f'SELECT {",".join(columns)} FROM "{table}"'))
    return sha256(repr(sorted((tuple(row) for row in rows), key=repr)).encode()).hexdigest()


def capture_delta(connection):
    columns = tuple(column["name"] for column in inspect(connection).get_columns("memory_batch_runs"))
    return {"columns": columns, "digest": _digest(connection, "memory_batch_runs", columns)}


def verify_delta(connection, before):
    if _digest(connection, "memory_batch_runs", before["columns"]) != before["digest"]:
        raise SqliteMigrationDeltaError("world_activity_historical_job_changed")
    if "credential_revision" not in before["columns"] and connection.execute(text(
        "SELECT count(*) FROM memory_batch_runs WHERE credential_revision IS NOT NULL OR credential_id IS NOT NULL")).scalar_one():
        raise SqliteMigrationDeltaError("world_activity_historical_key_recaptured")
    if connection.execute(text("SELECT count(*) FROM world_image_policies WHERE provenance='legacy:unproven' AND (generation_limit IS NOT NULL OR vision_limit IS NOT NULL)")).scalar_one():
        raise SqliteMigrationDeltaError("world_activity_legacy_cap_invented")


def _generation_settings(connection, image, role):
    if not image:
        return {}
    try:
        old_profiles = json.loads(image["generation_profiles_json"])
        if not isinstance(old_profiles, dict):
            raise ValueError()
    except (ValueError, TypeError):
        raise SqliteMigrationDeltaError("world_activity_image_settings_invalid") from None
    profiles, active = {}, {}
    for name, profile in old_profiles.items():
        if not isinstance(profile, dict) or not isinstance(profile.get("options", {}), dict):
            raise SqliteMigrationDeltaError("world_activity_image_settings_invalid")
        canonical = name.rsplit(":", 1)[0]
        retained = {"options": profile.get("options", {}), "connection": profile.get("connection")}
        if canonical.startswith("novelai:"):
            profiles[name] = retained
        if canonical not in profiles or profile.get("active"):
            profiles[canonical] = retained
        if profile.get("active"):
            active = profile
    values = {"appearance": image["appearance_prompt"], "style": image["style_prompt"],
        "negative": image["negative_prompt"], "reference_enabled": bool(active.get("reference_enabled")),
        "reference_asset_id": image["reference_asset_id"], "profiles": profiles}
    if values["reference_asset_id"]:
        asset = connection.execute(text("SELECT * FROM media_assets WHERE id=:id"), {"id": values["reference_asset_id"]}).mappings().first()
        if asset and asset["owner_id"] == role["owner_id"] and asset["scope_kind"] == "character" and asset["scope_id"] == role["character_id"] and asset["state"] != "deleted":
            values["legacy_reference"] = {"character_id": role["character_id"], "asset_id": asset["id"],
                "asset_revision": asset["revision"], "asset_digest": asset["content_hash"]}
    return values


def _copy_proven_attempts(connection, roles):
    known = {role["id"]: role for role in roles}
    queries = (("image", "sns", """SELECT a.*, p.author_world_character_id AS actor FROM post_image_generation_attempts a
        JOIN post_image_generation_jobs j ON j.id=a.job_id JOIN posts p ON p.id=j.post_id"""),
        ("vision", "chat", """SELECT a.*, t.responding_world_character_id AS actor FROM image_interpretation_attempts a
        JOIN image_interpretations i ON i.id=a.interpretation_id JOIN message_threads t ON i.scope_key='thread:' || t.id
        WHERE i.owner_id=t.requester_id AND t.world_scope_status='resolved'"""))
    for purpose, lane, query in queries:
        for row in connection.execute(text(query)).mappings():
            role = known.get(row["actor"])
            if role is None or role["owner_id"] != row["owner_id"]:
                continue
            if purpose == "image" and row["character_id"] != role["character_id"]:
                continue
            request = f"legacy:{purpose}:{row['id']}"
            if connection.execute(text("SELECT id FROM world_image_attempts WHERE world_character_id=:actor AND purpose=:purpose AND request_key=:request"), {"actor": role["id"], "purpose": purpose, "request": request}).first():
                continue
            state = {"succeeded": "completed", "result_received": "completed", "outcome_unknown": "unknown"}.get(row["status"], row["status"])
            if state not in {"reserved", "submitted", "completed", "failed", "unknown", "released"}:
                state = "unknown"
            connection.execute(text("""INSERT INTO world_image_attempts
                (id,world_character_id,purpose,request_key,period_date,lane,state,credential_revision,created_at)
                VALUES (:id,:actor,:purpose,:request,:period,:lane,:state,0,:created)"""),
                {"id": sha256(request.encode()).hexdigest(), "actor": role["id"], "purpose": purpose, "request": request,
                 "period": row["quota_day"], "lane": lane, "state": state, "created": row["created_at"]})


def upgrade(connection):
    roles = [dict(row) for row in connection.execute(text("SELECT w.*,c.owner_id FROM world_characters w JOIN characters c ON c.id=w.character_id")).mappings()]
    counts = Counter(role["character_id"] for role in roles)
    keys = [dict(row) for row in connection.execute(text("SELECT * FROM llm_credentials WHERE character_id IS NOT NULL AND purpose='agent'")).mappings()]
    media = [dict(row) for row in connection.execute(text("SELECT * FROM media_credentials WHERE purpose='user_image' AND character_scope<>''")).mappings()]
    partners = [dict(row) for row in connection.execute(text("SELECT * FROM media_credentials WHERE purpose='comfy_partner_image' AND character_scope<>'' AND enabled AND encrypted_secret IS NOT NULL")).mappings()]
    proven = []
    for role in roles:
        if counts[role["character_id"]] != 1:
            continue
        own_keys = [key for key in keys if key["character_id"] == role["character_id"] and key["owner_id"] == role["owner_id"] and key["encrypted_api_key"] and key["enabled"]]
        for key in own_keys if len(own_keys) == 1 else ():
                proven.append((role, "sns", key["provider"], key["model"], key["thinking_level"],
                    key["encrypted_api_key"], key["key_fingerprint"], role["character_id"], "agent"))
        for key in media:
            if key["character_scope"] == role["character_id"] and key["owner_id"] == role["owner_id"] and key["encrypted_secret"] and key["enabled"]:
                image = connection.execute(text("SELECT generation_provider,generation_model FROM agent_image_generation_settings WHERE character_id=:id"), {"id": role["character_id"]}).mappings().first()
                if image and image["generation_provider"] == key["provider"]:
                    proven.append((role, "image", key["provider"], image["generation_model"] or "workflow", None,
                        key["encrypted_secret"], key["fingerprint"], key["character_scope"], "user_image"))
        # A local Comfy server may have only a partner credential. Its actor
        # must still be uniquely proved; do not borrow any global server key.
        partner = next((p for p in partners if p["owner_id"] == role["owner_id"] and p["character_scope"] == role["character_id"] and p["provider"] == "comfyui"), None)
        if partner and not any(p[0]["id"] == role["id"] and p[1] == "image" for p in proven):
            image = connection.execute(text("SELECT generation_provider,generation_model FROM agent_image_generation_settings WHERE character_id=:id"), {"id": role["character_id"]}).mappings().first()
            if image and image["generation_provider"] == "comfyui":
                proven.append((role, "image", "comfyui", image["generation_model"] or "workflow", None,
                    None, partner["fingerprint"], role["character_id"], "user_image"))
    callback = _interpreter.get()
    if proven and callback is None:
        raise SqliteMigrationDeltaError("world_activity_secret_interpreter_required")
    for role, _, provider, _, _, envelope, _, character_id, purpose in proven:
        if envelope is None:
            continue  # The partner-only envelope is authenticated below.
        try:
            callback(envelope, {"owner_id": role["owner_id"], "character_id": character_id, "provider": provider, "purpose": purpose})
        except Exception:
            raise SqliteMigrationDeltaError("world_activity_secret_authentication_failed") from None
    rebound = []
    for entry in proven:
        role, purpose, provider, model, thinking, envelope, fingerprint, character_id, aad_purpose = entry
        partner = next((p for p in partners if p["owner_id"] == role["owner_id"] and p["character_scope"] == role["character_id"] and p["provider"] == "comfyui"), None)
        if purpose == "image" and provider == "comfyui" and partner:
            if not hasattr(callback, "rebind_image_pair"):
                raise SqliteMigrationDeltaError("world_activity_secret_interpreter_required")
            try:
                envelope = callback.rebind_image_pair(envelope,
                    {"owner_id": role["owner_id"], "character_id": character_id, "provider": provider, "purpose": aad_purpose},
                    partner["encrypted_secret"], {"owner_id": role["owner_id"], "character_id": character_id, "provider": provider, "purpose": "comfy_partner_image"},
                    {"owner_id": role["owner_id"], "character_id": role["id"], "provider": provider, "purpose": "user_image"})
            except Exception:
                raise SqliteMigrationDeltaError("world_activity_secret_authentication_failed") from None
            character_id, aad_purpose = role["id"], "user_image"
        rebound.append((role, purpose, provider, model, thinking, envelope, fingerprint, character_id, aad_purpose))
    proven = rebound
    existing = set(inspect(connection).get_table_names())
    ddl = json.loads(Path(__file__).with_name("world_activity_v30_ddl.json").read_text(encoding="utf-8"))
    if not NEW_TABLES <= existing:
        if NEW_TABLES & existing:
            raise SqliteMigrationDeltaError("world_activity_partial_schema")
        for statement in ddl:
            connection.exec_driver_sql(statement)
    columns = {c["name"] for c in inspect(connection).get_columns("memory_batch_runs")}
    for name, sql_type in (("credential_id", "VARCHAR(64)"), ("credential_revision", "INTEGER")):
        if name not in columns:
            connection.exec_driver_sql(f"ALTER TABLE memory_batch_runs ADD COLUMN {name} {sql_type}")
    now = datetime.now(UTC).isoformat()
    for role, purpose, provider, model, thinking, envelope, fingerprint, character_id, aad_purpose in proven:
        if connection.execute(text("SELECT id FROM world_credentials WHERE world_character_id=:actor AND purpose=:purpose"), {"actor": role["id"], "purpose": purpose}).first():
            continue
        connection.execute(text("INSERT INTO world_credentials (id,owner_id,world_id,world_character_id,purpose,provider,model,thinking_level,encrypted_secret,fingerprint,revision,aad_character_id,aad_purpose) VALUES (:id,:owner,:world,:actor,:purpose,:provider,:model,:thinking,:secret,:fingerprint,1,:character,:aad)"),
            dict(id=uuid4().hex, owner=role["owner_id"], world=role["world_id"], actor=role["id"], purpose=purpose,
                provider=provider, model=model, thinking=thinking, secret=envelope, fingerprint=fingerprint, character=character_id, aad=aad_purpose))
    connection.execute(text("""INSERT INTO world_credential_revisions
        (credential_id,revision,provider,model,thinking_level,encrypted_secret,fingerprint,aad_character_id,aad_purpose)
        SELECT c.id,c.revision,c.provider,c.model,c.thinking_level,c.encrypted_secret,c.fingerprint,c.aad_character_id,c.aad_purpose
        FROM world_credentials c WHERE NOT EXISTS
        (SELECT 1 FROM world_credential_revisions h WHERE h.credential_id=c.id AND h.revision=c.revision)"""))
    for row in connection.execute(text("SELECT s.id,p.model_id,p.thinking_level,p.version FROM memory_scope_settings s JOIN memory_batch_profiles p ON p.owner_id=s.owner_id")).mappings():
        if not connection.execute(text("SELECT scope_setting_id FROM memory_subject_profiles WHERE scope_setting_id=:id"), {"id": row["id"]}).first():
            connection.execute(text("INSERT INTO memory_subject_profiles (scope_setting_id,model_id,thinking_level,version,updated_at) VALUES (:id,:model_id,:thinking_level,:version,:now)"), {**dict(row), "now": now})
    for role in roles:
        if connection.execute(text("SELECT world_character_id FROM world_image_policies WHERE world_character_id=:id"), {"id": role["id"]}).first():
            continue
        image = connection.execute(text("SELECT * FROM agent_image_generation_settings WHERE character_id=:id"), {"id": role["character_id"]}).mappings().first()
        cap = image["generation_daily_limit"] if image and counts[role["character_id"]] == 1 else None
        valid = type(cap) is int and 1 <= cap <= 10000
        # Saved ON/OFF is retained only with proven actor cap/key and configuration.
        settings = _generation_settings(connection, image, role) if counts[role["character_id"]] == 1 else {}
        connection.execute(text("INSERT INTO world_image_policies (world_character_id,generation_limit,vision_limit,generation_enabled,vision_enabled,generation_settings,revision,provenance) VALUES (:actor,:cap,NULL,:enabled,false,:settings,1,:provenance)"),
            {"actor": role["id"], "cap": cap if valid else None,
             "enabled": bool(valid and image and image["generation_auto_enabled"] and any(p[0]["id"] == role["id"] and p[1] == "image" for p in proven)),
             "settings": json.dumps(settings), "provenance": "legacy:proven-generation" if valid else "legacy:unproven"})
    _copy_proven_attempts(connection, roles)
