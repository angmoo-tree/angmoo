"""Reviewed SQLite change producers, including bulk writes and FK cascades.

Only bounded identity/epoch writes occur here. Expansion and validation belong
to the consumer. DELETE uses OLD before a parent can disappear from joins.
"""
import json
from pathlib import Path
from sqlalchemy import inspect


def catalog():
    return json.loads(Path(__file__).with_suffix(".json").read_text(encoding="utf-8"))


def statements():
    result = []
    for entry in catalog():
        table = entry["table"]
        for operation in ("INSERT", "UPDATE", "DELETE"):
            rows = ("OLD", "NEW") if operation == "UPDATE" else (("OLD",) if operation == "DELETE" else ("NEW",))
            condition = " OR ".join(f'OLD."{column}" IS NOT NEW."{column}"' for column in entry["columns"])
            when = f" WHEN {condition}" if operation == "UPDATE" else ""
            body = []
            for row in rows:
                key, epoch = (entry[name].format(row=row) for name in ("key", "epoch"))
                body.append(f"INSERT INTO memory_vector_validation_revisions(scope_key,revision) SELECT {epoch},1 WHERE {epoch} IS NOT NULL ON CONFLICT(scope_key) DO UPDATE SET revision=revision+1;")
                body.append(f"INSERT INTO memory_vector_changes(source_kind,source_key) SELECT '{entry['kind']}',CAST({key} AS TEXT) WHERE {key} IS NOT NULL;")
                # Reverse collections must signal inserts as well as existing rows.
                if table in {"social_event_evidence", "social_action_subjective_contexts"}:
                    body.append(f"INSERT INTO memory_vector_changes(source_kind,source_key) SELECT 'posts',{row}.source_post_id WHERE {row}.source_post_id IS NOT NULL;")
                if table == "social_events":
                    body.append(f"INSERT INTO memory_vector_changes(source_kind,source_key) SELECT 'posts',source_post_id FROM social_event_evidence WHERE social_event_id={row}.id AND source_post_id IS NOT NULL;")
                    body.append(f"INSERT INTO memory_vector_changes(source_kind,source_key) SELECT 'post_likes',source_object_id FROM social_event_evidence WHERE social_event_id={row}.id AND source_object_type='post_like';")
                if table == "social_event_evidence":
                    body.append(f"INSERT INTO memory_vector_changes(source_kind,source_key) SELECT 'post_likes',{row}.source_object_id WHERE {row}.source_object_type='post_like';")
                if table == "world_character_feed_observations":
                    body.append(f"INSERT INTO memory_vector_changes(source_kind,source_key) SELECT 'social_events',social_event_id FROM social_event_evidence WHERE source_post_id={row}.post_id;")
                if table == "memory_items":
                    body.append(f"INSERT INTO memory_vector_changes(source_kind,source_key) SELECT 'memory',{row}.superseded_by_id WHERE {row}.superseded_by_id IS NOT NULL;")
                if table in {"world_credentials", "world_credential_revisions"}:
                    body.append(f"INSERT INTO memory_vector_changes(source_kind,source_key) SELECT 'world',substr({epoch},7) WHERE {epoch} IS NOT NULL;")
                if table == "llm_credentials":
                    body.append(f"INSERT INTO memory_vector_changes(source_kind,source_key) SELECT 'users',{row}.owner_id;")
            timing = "AFTER" if operation == "INSERT" else "BEFORE"
            result.append(f'CREATE TRIGGER IF NOT EXISTS "memory_vector_{table}_{operation.lower()}" {timing} {operation} ON "{table}"{when} BEGIN {" ".join(body)} END')
    return tuple(result)


def install(connection):
    if connection.dialect.name != "sqlite" or "memory_vector_changes" not in inspect(connection).get_table_names():
        return
    for statement in statements():
        connection.exec_driver_sql(statement)
