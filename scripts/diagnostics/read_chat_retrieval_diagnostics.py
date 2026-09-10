"""Read basic diagnostics only from an explicitly selected local SQLite file.

Example (container): python /workspace/scripts/diagnostics/read_chat_retrieval_diagnostics.py
  --database /var/lib/angmoo/canonical/angmoo.sqlite3 --request-id request-...
Use the actual configured database path. This tool never imports application
settings, modifies SQLite, or prints messages/credentials/detailed queries.
"""
import argparse
from datetime import UTC, datetime
import json
from pathlib import Path
import sqlite3


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--request-id", required=True)
    args = parser.parse_args()
    uri = args.database.resolve().as_uri() + "?mode=ro"
    with sqlite3.connect(uri, uri=True) as db:
        db.execute("PRAGMA query_only=ON")
        exists = db.execute("SELECT 1 FROM sqlite_master WHERE name='chat_retrieval_diagnostics' AND type='table'").fetchone()
        row = None if not exists else db.execute(
            "SELECT expires_at, payload_json FROM chat_retrieval_diagnostics WHERE request_id=?", (args.request_id,)
        ).fetchone()
    result = {"status": "not_recorded", "record": None}
    if row:
        expiry = datetime.fromisoformat(row[0]).replace(tzinfo=UTC)
        result = {"status": "expired", "record": None} if expiry <= datetime.now(UTC) else {"status": "available", "record": json.loads(row[1])}
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
