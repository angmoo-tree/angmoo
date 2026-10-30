"""Read basic diagnostics from an explicitly selected PostgreSQL installation.

Example (container): python /workspace/scripts/diagnostics/read_chat_retrieval_diagnostics.py
  --dsn-file /var/lib/angmoo/secrets/postgresql-runtime-dsn --request-id request-...
Legacy --database reads only a preserved SQLite source. This tool never imports
application settings or prints connection credentials/detailed query inputs.
"""
import argparse
from datetime import UTC, datetime
import json
from pathlib import Path
import sqlite3


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    store=parser.add_mutually_exclusive_group(required=True)
    store.add_argument("--dsn-file", type=Path)
    store.add_argument("--database", type=Path,help='Legacy SQLite migration source only')
    parser.add_argument("--request-id", required=True)
    args = parser.parse_args()
    if args.dsn_file:
        import psycopg
        dsn=args.dsn_file.read_text(encoding='utf-8').strip().replace('postgresql+psycopg://','postgresql://',1)
        with psycopg.connect(dsn,connect_timeout=5,options='-c default_transaction_read_only=on') as db:
            exists=db.execute("SELECT to_regclass('public.chat_retrieval_diagnostics')").fetchone()[0]
            row=None if not exists else db.execute(
                'SELECT expires_at,payload_json FROM chat_retrieval_diagnostics WHERE request_id=%s',(args.request_id,)).fetchone()
    else:
        uri = args.database.resolve().as_uri() + "?mode=ro"
        with sqlite3.connect(uri, uri=True) as db:
            db.execute("PRAGMA query_only=ON")
            exists = db.execute("SELECT 1 FROM sqlite_master WHERE name='chat_retrieval_diagnostics' AND type='table'").fetchone()
            row = None if not exists else db.execute(
                "SELECT expires_at, payload_json FROM chat_retrieval_diagnostics WHERE request_id=?", (args.request_id,)
            ).fetchone()
    result = {"status": "not_recorded", "record": None}
    if row:
        expiry = (datetime.fromisoformat(row[0]) if isinstance(row[0],str) else row[0]).replace(tzinfo=UTC)
        record=json.loads(row[1]) if isinstance(row[1],str) else row[1]
        result = {"status": "expired", "record": None} if expiry <= datetime.now(UTC) else {"status": "available", "record": record}
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
