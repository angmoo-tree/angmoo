# L3-ER3 LadybugDB relationship projection contract

ER3 PR H turns the ER1 compatibility spike into a production-shaped but
inactive relationship projection adapter. It does not switch Angmoo's current
PostgreSQL canonical store, Neo4j graph default, Docker topology, or frontend.

## Ownership and data authority

```text
successful social transaction
→ canonical SQLite SocialEvent + projection outbox
→ GraphProjectionWorker
→ RelationshipProjectionPort
→ LadybugRelationshipProjection
→ rebuildable relationships.lbdb
```

SQLite is the only authority. LadybugDB stores no credential and is safe to
delete and rebuild from canonical events and outbox commands. A graph failure
therefore cannot roll back or reject a committed Post, Comment, or SocialEvent.
The outbox row remains pending with a sanitized `ladybug_unavailable` class.

## Schema v1

Nodes:

- `ProjectionMeta`: adapter and schema version;
- `World`: `world_id` primary key;
- `WorldCharacter`: global WorldCharacter ID plus World and Character IDs;
- `SocialEvent`: event ID, World, evidence type, occurrence time, and source
  schema version.

Edges:

- `MEMBER_OF`, `PERFORMED`, `TARGETED`, and `OCCURRED_IN` preserve event
  provenance;
- directional `RELATES_TO` contains relationship state, scores, interaction
  count, latest event/time, updated time, and monotonic relationship version;
- `RELATIONSHIP_GROUNDED_IN` joins a directional relationship actor to one
  source event and records World, target, state, event, and relationship
  revision.

Every query or mutation includes an explicit World scope. An older
relationship version is a deterministic no-op. Replaying the same command does
not duplicate nodes, aggregate edges, or evidence edges. Source delete/hide
detaches the source event and its evidence edges while retaining the aggregate
relationship snapshot, matching the current Neo4j contract.

## Lifecycle and concurrency

One `LadybugRelationshipProjection` instance owns one database and one
connection. An in-process re-entrant lock serializes worker calls, and a
cross-process one-byte file lock rejects a second READ_WRITE owner. The adapter
does not expose a request-scoped connection factory. Each accepted projection
command runs in one LadybugDB transaction and applies the worker's bounded
query timeout to the owned connection; a failed multi-query apply is rolled
back and remains replayable from the canonical outbox.

On Windows, a non-ASCII application-data path is exposed to LadybugDB through
the ER1-approved temporary `subst` drive alias. The adapter dynamically chooses
an unused drive, keeps the canonical files in the original directory, and
removes the alias on close. Opening failure releases both the alias and writer
lock.

## Portable virtual address reservation (2026-10-22)

Runtime opens and schema inspection explicitly use `max_db_size=64 * 1024**3`
through the adapter's `LADYBUG_MAX_DB_SIZE_BYTES` policy. Ladybug 0.19.1 otherwise
reserves 8 TiB of virtual address space; that reservation fails on the tested
native ARM64 Android phone even though the small graph needs little resident
memory. This uses Ladybug's supported constructor option on all platforms,
without changing the library, query results, startup deadlines, or schema v3.

64 GiB is a finite graph mapping/capacity limit, not a RAM requirement or an
immediate disk allocation. SQLite, media and chat storage are not covered by
this graph-only limit. Large graphs can exhaust this native capacity; the
adapter keeps its existing failure/rollback and canonical-outbox recovery
semantics rather than deleting data, silently increasing the reservation, or
reporting a failed graph as ready. Changing this policy in the future requires
capacity and supported-device verification, including existing graph reopen.
The buffer pool's memory policy is separate and is not changed by this fix.

The focused regression creates, writes, closes, inspects and reopens a real
graph behind a factory that rejects the unbounded library default. It also
reopens a graph created with a different reservation size and compares its
relationship digest. Existing writer-lock, replay and World isolation tests
remain applicable. Actual Android startup and memory use must be measured
separately; passing the desktop regression does not establish those outcomes.

## Error and privacy boundary

Provider-specific exceptions map to the domain-owned
`RelationshipProjectionBackendError` with stable classes only. Raw native
messages, query text, absolute paths, event content, prompts, and credentials
are not written to the outbox or worker logs.

## PR H executable evidence

`backend/tests/test_l3_er3_ladybug_projection.py` uses a real LadybugDB file to
prove:

- Unicode-and-space data path open, close, and reopen;
- schema bootstrap and stable World digest;
- idempotent event and relationship replay;
- stale relationship-version rejection;
- idempotent source hide/delete exclusion;
- two-World isolation and scoped clear;
- second writer rejection and later lock reuse;
- Ladybug outage leaves the SQLite outbox pending and marks graph degraded.

PR I separately owns the sixteen typed read queries, Neo4j/Ladybug parity,
full World replay digest, and the user-visible relationship graph scenario.
