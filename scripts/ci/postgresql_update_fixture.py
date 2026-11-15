"""Provider-free synthetic fixture inside an isolated qualification backend.

Normal local-owner admission and character creation run through HTTP. Small
explicit ORM specimens then cover stored Chat, memory and relationship data;
they are persistence checks, not evidence of AI generation or relevance.
Only counts and digests leave this process. Never use on an existing home.
"""
import argparse
import hashlib
import http.cookiejar
import json
import os
from pathlib import Path
import urllib.request

from sqlalchemy import select, text
from app.database import create_database_engine, create_session_factory
from app.models import Base
from app.runtime.persistence.postgresql_schema import metadata
from app.runtime.postgresql_installation import read_dsn
from app.runtime.product_identity import runtime_identity

MARKER = "qualification-015"
TABLES = ("users", "worlds", "world_characters", "posts", "message_threads",
          "message_messages", "memory_items", "relationship_states")


def seed(factory):
    origin = os.environ["ANGMOO_FRONTEND_ORIGIN"]
    headers = {"Origin": origin, "Host": origin.split("//", 1)[1],
               "X-Angmoo-Frontend-Origin": origin, "Sec-Fetch-Site": "same-origin",
               "Content-Type": "application/json"}
    client = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))

    def request(method, path, body=None):
        data = json.dumps(body).encode() if body is not None else b"" if method == "POST" else None
        with client.open(urllib.request.Request("http://127.0.0.1:8080/api/v1" + path,
                method=method, headers=headers, data=data), timeout=30) as response:
            return json.load(response)

    status = request("GET", "/auth/local/bootstrap")
    assert status["state"] == "unclaimed", "fixture_requires_empty_installation"
    request("POST", "/auth/local/bootstrap/challenge")
    claimed = request("POST", "/auth/local/bootstrap/prepare", {
        "protocol": 2, "installation_id": status["installation_id"],
        "client_instance_id": MARKER, "expected_generation": 0, "preferred_language": "en-US"})
    owner = claimed["user"]["id"]
    request("POST", "/auth/local/environment", {"client_id": MARKER,
        "expected_revision": 0, "sequence": 1, "preferred_language": "en-US", "timezone": "UTC"})
    for name in ("Mango", "Willow"):
        draft = request("POST", "/agents/drafts", {"execution_mode": "llm"})
        draft = request("PATCH", "/agents/drafts/" + draft["id"], {
            "revision": draft["revision"], "name": name, "handle": "qualification_" + name.lower(),
            "worldview": "Friends share daily gardening discoveries.",
            "topic_preferences": "Gardening, cooking, and neighborhood walks."})
        created = request("POST", "/agents/drafts/" + draft["id"] + "/complete", {"revision": draft["revision"]})
        assert created.get("credential") is None and created["settings"]["auto_enabled"] is False
    classes = {mapper.local_table.name: mapper.class_ for mapper in Base.registry.mappers}
    with factory() as db:
        actors = db.execute(select(classes["world_characters"]).order_by(classes["world_characters"].id)).scalars().all()
        pairs = [(a, b) for a in actors for b in actors if a.id != b.id and a.world_id == b.world_id]
        assert pairs, "fixture_requires_two_characters_in_one_world"
        actor, other = pairs[0]
        db.add(classes["posts"](id=MARKER + "-post", author_user_id=owner,
            author_character_id=actor.character_id, author_world_character_id=actor.id,
            world_id=actor.world_id, author_name="Mango", title="Garden visit",
            body="Willow brought basil seeds. 바질 씨앗을 보관합니다."))
        db.add(classes["message_threads"](id=MARKER + "-thread", requester_id=owner,
            character_id=other.character_id, world_id=actor.world_id, world_scope_status="resolved",
            requester_world_character_id=actor.id, responding_world_character_id=other.id))
        db.flush()
        db.add(classes["message_messages"](thread_id=MARKER + "-thread", role="user",
            content="Remember our basil garden. 바질 정원 🪴", status="ok"))
        db.add(classes["memory_items"](id=MARKER + "-memory", owner_id=owner,
            world_id=actor.world_id, subject_world_character_id=actor.id,
            counterpart_world_character_id=other.id, memory_kind="AUTOBIOGRAPHICAL_EVENT",
            summary="Willow brought basil seeds. 바질 씨앗을 보관합니다.", confidence=1.0, salience=0.6))
        db.add(classes["relationship_states"](id=MARKER + "-relationship", world_id=actor.world_id,
            actor_world_character_id=actor.id, target_world_character_id=other.id,
            familiarity=10, affinity=5, perception="A thoughtful gardening friend. 친절한 친구."))
        db.commit()
    Path("/var/lib/angmoo/media/qualification-015.txt").write_text("Basil / 바질 🪴", encoding="utf-8")


def probe(engine):
    result = {}
    with engine.connect() as db:
        for name in TABLES:
            rows = db.execute(text("SELECT to_jsonb(t)::text FROM " + name + " AS t ORDER BY id")).scalars().all()
            assert rows, "fixture_table_empty:" + name
            result[name] = {"count": len(rows), "sha256": hashlib.sha256("\n".join(rows).encode()).hexdigest()}
        result["write_marker"] = db.execute(text("SELECT value FROM site_operation_settings WHERE key=:key"), {"key": MARKER}).scalar_one_or_none()
    for name in ("secrets/app-secret", "media/qualification-015.txt"):
        path = Path("/var/lib/angmoo") / name
        if name.startswith("secrets/") and not path.exists():
            # The runtime owns the actual APP_SECRET filename; cover every
            # secret below rather than choosing a fallback credential.
            continue
        result[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    result["secrets"] = {str(p.relative_to("/var/lib/angmoo/secrets")): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(Path("/var/lib/angmoo/secrets").rglob("*")) if p.is_file()}
    assert result["secrets"], "fixture_secrets_missing"
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("operation", choices=("seed", "probe", "write"))
    parser.add_argument("--source", required=True)
    args = parser.parse_args()
    assert runtime_identity()["source_sha"] == args.source, "fixture_source_mismatch"
    metadata()
    engine = create_database_engine(read_dsn(Path("/var/lib/angmoo/secrets/postgresql-runtime-dsn")))
    try:
        if args.operation == "seed":
            seed(create_session_factory(engine))
        if args.operation == "write":
            with engine.begin() as db:
                db.execute(text("INSERT INTO site_operation_settings(key,value) VALUES(:key,:value)"),
                    {"key": MARKER, "value": "updated / 업데이트 🪴"})
        search_ready = None
        if runtime_identity()["version"] == "0.1.5":
            from app.runtime.memory.postgresql_recall import PostgresMemoryRecallIndex
            from app.runtime.memory.sqlite_fts5_recall import MemoryRecallIndexSettings
            index = PostgresMemoryRecallIndex(engine, settings=MemoryRecallIndexSettings.for_representation("episode_v1"))
            search_ready = index.open().healthy
            assert search_ready, "runtime_search_not_ready"
            with engine.connect() as db:
                assert not db.execute(text("SELECT has_schema_privilege(current_user,'public','CREATE')")).scalar_one()
        print(json.dumps({"source_sha": args.source, "provider_transmissions": 0,
            "search_ready": search_ready, "data": probe(engine)}))
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
