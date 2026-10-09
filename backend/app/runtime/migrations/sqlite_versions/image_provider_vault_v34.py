"""Forward provider vault and authenticated retirement of Comfy server keys."""
import hashlib
import json
from pathlib import Path
from uuid import uuid4
from sqlalchemy import inspect, text
from .contracts import SqliteMigrationDeltaError
from .world_activity_v30 import _interpreter

MUTABLE_IDENTITY_TABLES = frozenset({"world_credentials", "world_credential_revisions", "media_credentials", "world_image_provider_credentials"})


def capture_delta(connection):
    result = {}
    for table in sorted(MUTABLE_IDENTITY_TABLES - {"world_image_provider_credentials"}):
        columns = [c["name"] for c in inspect(connection).get_columns(table) if c["name"] not in {"encrypted_secret", "fingerprint", "enabled", "revision"}]
        fields = ",".join(f'"{name}"' for name in columns)
        rows = tuple(sorted((tuple(row) for row in connection.exec_driver_sql(f"SELECT {fields} FROM {table}")), key=repr))
        result[table] = hashlib.sha256(repr(rows).encode()).hexdigest()
    # Retirement may change only ComfyUI server material. Partner-only legacy
    # credentials and every external provider envelope must remain byte-identical.
    for name, query in {
        "protected_current": "SELECT * FROM world_credentials WHERE purpose != 'image' OR provider != 'comfyui'",
        "protected_history": "SELECT h.* FROM world_credential_revisions h JOIN world_credentials c ON c.id=h.credential_id WHERE c.purpose != 'image' OR h.provider != 'comfyui'",
        "protected_media": "SELECT * FROM media_credentials WHERE NOT (provider='comfyui' AND purpose='user_image')",
    }.items():
        rows = tuple(sorted((tuple(row) for row in connection.exec_driver_sql(query)), key=repr))
        result[name] = hashlib.sha256(repr(rows).encode()).hexdigest()
    return result


def verify_delta(connection, before):
    if capture_delta(connection) != before:
        raise SqliteMigrationDeltaError("image_vault_identity_changed")
    if connection.exec_driver_sql("SELECT count(*) FROM media_credentials WHERE provider='comfyui' AND purpose='user_image' AND (encrypted_secret IS NOT NULL OR fingerprint IS NOT NULL OR enabled)").scalar_one():
        raise SqliteMigrationDeltaError("comfy_server_key_retirement_failed")


def upgrade(connection, *, interpreter=None):
    callback = interpreter or _interpreter.get()
    current = [dict(r) for r in connection.execute(text("SELECT * FROM world_credentials WHERE purpose='image'")).mappings()]
    history = [dict(r) for r in connection.execute(text("SELECT h.*,c.owner_id,c.world_id,c.world_character_id FROM world_credential_revisions h JOIN world_credentials c ON c.id=h.credential_id WHERE c.purpose='image'")).mappings()]
    legacy = [dict(r) for r in connection.execute(text("SELECT * FROM media_credentials WHERE provider='comfyui' AND purpose='user_image'")).mappings()]
    transformed = []
    # Authenticate the entire selected transition before any DDL/data mutation.
    try:
        for row in current + history:
            provider = row["provider"]
            if provider not in {"novelai", "nanogpt", "openrouter", "comfyui"}:
                raise ValueError("image_provider_invalid")
            scope = {"owner_id": row["owner_id"], "character_id": row["aad_character_id"], "provider": provider, "purpose": row["aad_purpose"]}
            target = {**scope, "character_id": row["world_character_id"], "purpose": "comfy_partner_image" if provider == "comfyui" else "user_image"}
            material = (None, None, None) if not row["encrypted_secret"] else callback.image_provider_material(row["encrypted_secret"], scope, target, comfy=provider == "comfyui")
            transformed.append((row, material))
        for row in legacy:
            if row["encrypted_secret"]:
                callback(row["encrypted_secret"], {"owner_id": row["owner_id"], "character_id": row["character_scope"], "provider": "comfyui", "purpose": "user_image"})
    except Exception:
        raise SqliteMigrationDeltaError("image_vault_secret_authentication_failed") from None
    if "world_image_provider_credentials" not in inspect(connection).get_table_names():
        for statement in json.loads(Path(__file__).with_name("image_provider_vault_v34_ddl.json").read_text(encoding="utf-8")):
            connection.exec_driver_sql(statement)
    newest = {}
    for row, (cleaned, fingerprint, vault) in transformed:
        if row["provider"] == "comfyui":
            table, key = ("world_credential_revisions", "credential_id") if "credential_id" in row else ("world_credentials", "id")
            connection.execute(text(f"UPDATE {table} SET encrypted_secret=:secret,fingerprint=:fingerprint WHERE {key}=:id AND revision=:revision"),
                {"secret": cleaned, "fingerprint": fingerprint, "id": row[key], "revision": row["revision"]})
        vault_key = (row["owner_id"], row["world_id"], row["world_character_id"], row["provider"])
        if vault_key not in newest or row["revision"] > newest[vault_key][0]["revision"]:
            newest[vault_key] = (row, fingerprint, vault)
    for (owner, world, actor, provider), (row, fingerprint, vault) in newest.items():
        purpose = "comfy_partner_image" if provider == "comfyui" else "user_image"
        exists = connection.execute(text("SELECT id FROM world_image_provider_credentials WHERE owner_id=:owner AND world_id=:world AND world_character_id=:actor AND provider=:provider AND purpose=:purpose"),
            {"owner": owner, "world": world, "actor": actor, "provider": provider, "purpose": purpose}).first()
        if not exists:
            connection.execute(text("INSERT INTO world_image_provider_credentials (id,owner_id,world_id,world_character_id,provider,purpose,encrypted_secret,fingerprint,revision,enabled,tombstone,aad_character_id,aad_purpose) VALUES (:id,:owner,:world,:actor,:provider,:purpose,:secret,:fingerprint,1,:enabled,:tombstone,:actor,:purpose)"),
                {"id": uuid4().hex, "owner": owner, "world": world, "actor": actor, "provider": provider, "purpose": purpose,
                 "secret": vault, "fingerprint": fingerprint, "enabled": bool(vault), "tombstone": not bool(vault)})
    connection.execute(text("UPDATE media_credentials SET encrypted_secret=NULL,fingerprint=NULL,enabled=false,revision=revision+1 WHERE provider='comfyui' AND purpose='user_image' AND (encrypted_secret IS NOT NULL OR fingerprint IS NOT NULL OR enabled)"))
