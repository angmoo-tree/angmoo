# PostgreSQL runtime and storage

English | [한국어](postgresql-runtime.ko.md)

Angmoo 0.1.4 uses one backend process and a dedicated PostgreSQL 17 server with pgvector 0.8.7. The backend owns the scheduler and projector in process. PostgreSQL owns application rows, job state and activity checkpoints. LadybugDB is a rebuildable relationship projection.

| Environment | Processes and storage |
| --- | --- |
| Docker amd64 / ARM64 | frontend, backend and postgres services; separate PostgreSQL and application-data volumes |
| Termux ARM64 | Three image filesystems under PRoot; private PGDATA, application data and credentials; no Docker daemon |
| Windows x64 | Tauri, bundled backend sidecar and Angmoo-owned native PostgreSQL; per-user data, no machine-wide DB service |

The Windows installer requires Windows 10 version 1903 (build 18362) or later.
Its bundled PostgreSQL processes use UTF-8 for Unicode installation/data paths;
this does not change the Windows system locale or another PostgreSQL installation.

## Search and memory

Keyword retrieval uses PostgreSQL full-text search with the existing CJK preprocessing and trigram/partial-match policy. Semantic retrieval uses **pgvector exact cosine search at 768 dimensions** with the stored model/profile and owner/World/character/thread boundaries. This release does not add an HNSW index or regenerate embeddings merely to migrate a database.

The index is not the source of authority. Deleted or out-of-scope memories cannot be delivered because they appear in an index. Chat and SNS keep their accepted starting input and deliver the stored original snapshot associated with selected memories. Relationship review uses situation-memory bodies grouped by counterpart and the existing relationship perception; it does not re-read original snapshots.

Memory and relationship maintenance share one execution slot. The selected character's prepared memory run or counterpart reviews continue at short safe transaction boundaries; this does not hold a DB lock across the whole character round. Embedding batches retain the existing limit of 20. SNS, Chat and normal reads continue independently.

## Connections and failures

The main SQLAlchemy pool retains up to 10 connections and permits 5 temporary overflow connections. The checkpoint pool allows 2 and direct connections are bounded at 2. They are limits, not a promise that every session exists at startup. The runtime role limit is 20. The server connection budget is 28 including 3 administrator reservations and operating headroom.

Serializable conflicts can still occur. DB-only operations retry the complete transaction with bounded attempts and elapsed time. Provider I/O is outside that transaction. A saved AI result is reused for storage recovery; uncertain commits are reconciled by identity and receipts before another public action.

Invalid AI text is not retried as a database outage. Failed maintenance parts require explicit manual recovery; closing a failure keeps completed results and history and excludes the closed part from later automatic rounds. Provider 429/503 retries remain at most two actual transmissions including the first attempt across SDK and app.

## Identity and schema

`CONTRIBUTOR_POSTGRESQL` is the Docker/browser profile. `LOCAL_POSTGRESQL` is the token-protected desktop profile. The runtime marker binds a data root, installation ID and private DSN file. The database has a matching installation identity. Serving uses a restricted runtime role, not the owner account.

`app/runtime/persistence/postgresql_schema.py` owns schema version 5 and explicit incremental changes. The owner-side installation/migration path prepares schema and extensions before serving. The normal backend rejects the wrong identity/schema; it does not fall back to SQLite or run historical Alembic migrations.

Schema version 5 is not product version 0.1.4. Frozen SQLite schema 41 is the supported 0.1.3 input contract. Old `LOCAL_EMBEDDED` / `CONTRIBUTOR_EMBEDDED` implementation and fixtures remain for legacy compatibility; current public launchers select PostgreSQL.

## Files and secrets

Application data includes media, the original encryption secret, runtime DSN and received-result journals. PostgreSQL files live separately. A database dump alone does not preserve media or the secret required to read encrypted credentials. Keep backup material private and use the [backup procedure](postgresql-backup.md).

Windows uses its own loopback port and verifies the actual cluster path and system ID before controlling it. It does not adopt an unrelated PostgreSQL server. Docker keeps the DB port inside the service network; Termux binds it to loopback. Credentials are stored in private files and do not enter image layers or command-line passwords.

Database connection passwords use owner-restricted local files so the services can restart. This file format does not encrypt those passwords; keep the secret directory and backups private. The Docker migration tool publishes complete files without replacing existing credentials. See [PostgreSQL password-file protection](https://www.postgresql.org/docs/17/libpq-pgpass.html) for the underlying access model.

See [migration](postgresql-migration.md) for the supported 0.1.3 transition. Historical SQLite documents retain their original scope; their PRAGMA, FTS5 and Vec1 commands are not PostgreSQL operating instructions.
