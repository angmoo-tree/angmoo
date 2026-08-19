# ADR: Angmoo embedded local runtime transition boundary

- Status: accepted target, gated implementation
- Decision baseline: `db1c32510f66cee20a3e64a01e85c5ea8753d77e`
- Issue: [#97](https://github.com/angmoo-tree/angmoo/issues/97)
- Scope: L3-ER0 architecture freeze only

## Context

Angmoo currently runs as six Docker Compose services: PostgreSQL, FastAPI,
Neo4j, scheduler, projector, and Next.js. L3 proved the P1-P4 local vertical
loop, while P5-P7 already define search, social-event, relationship, and graph
query behavior. The next transition must reduce the installed runtime without
redefining those product contracts.

This ADR records the intended boundary. ER0 does not add SQLite, LadybugDB,
Rust, or Tauri dependencies and does not change a database schema, route,
screen, process default, provider call, or public write.

## Decision

The gated target architecture is:

```text
Tauri Phone UI / Creator Studio / relationship graph windows
                         |
                 FastAPI local sidecar
                 |       |        |
          scheduler   projector   HTTP API
                 |       |
             SQLite canonical database
                 |
       outbox -> FTS5 / LadybugDB projections
```

The following rules are frozen:

1. SQLite is the future canonical local store. It must reproduce the frozen
   PostgreSQL row and lifecycle semantics before cutover.
2. LadybugDB is a rebuildable graph projection, never the source of truth.
   Every projected relationship and evidence row remains traceable to a
   canonical `source_event_id`.
3. FTS5 is the default text-recall projection. Vector search stays optional;
   core chat, relationship retrieval, and P1-P7 parity must pass with it off.
4. FastAPI remains the application sidecar and lifecycle owner. Scheduler and
   projector become in-process components only after ER4 proves singleton,
   bounded concurrency, drain, resume, and outage behavior.
5. Tauri owns the installed application windows and sidecar lifecycle. The
   same frontend source remains usable through the Next.js development server;
   the installed release consumes static assets and has no UI `:3000` listener.
6. Docker Compose remains a contributor, CI, compatibility, and rollback path
   until ER7. It is not removed by an intermediate ER.
7. Domain-first public surfaces remain stable. Storage and process adapters
   change behind ports owned by `worlds`, `world_characters`, `routines`,
   `routine_posts`, `manual_social`, `relationships`, and `runtime`.

## Compatibility gates

The target is accepted only subject to later executable gates:

- ER1 LadybugDB and Tauri Windows compatibility spike: native wheels/binaries,
  packaging, startup, shutdown, and GPL/third-party obligations must pass.
- ER2 SQLite: all 81 frozen Alembic migrations receive an explicit translation
  or deterministic replacement, followed by row/digest parity.
- ER3 LadybugDB: P7 DDL-equivalent constraints, projection writes, replay,
  delete/exclusion, World isolation, and typed-query digests must match.
- ER4 single runtime: one scheduler and one graph writer, five-way bounded
  execution, sleep/resume no-catch-up, graceful drain, and crash recovery.
- ER5 static/Tauri: browser development and installed windows use the same UI
  source; routes, API proxying, media, PWA, Phone UI, and Studio stay equivalent.
- ER6/ER7: synthetic migration/restore, clean Windows installation, rollback,
  uninstall data preservation, and explicit user cutover approval.

Any spike that cannot satisfy parity, licensing, Windows packaging, or
operational gates is a No-Go. The fallback is to keep the current adapter or
re-evaluate another embedded graph implementation; the product contract is not
weakened to make a candidate pass.

## Data and backup policy

The current developer fixture is not a user release and is not an ER0 entry
dependency. ER0 therefore creates no private-data dump or repository artifact.
Git preserves code history, not local data.

Migration safety is instead proven with synthetic, non-secret fixtures that
cover P1-P7 surfaces, deterministic row digests, graph replay, failed migration
rollback, application rollback, and restore into a clean data directory. Once
a public installed build can hold user data, an upgrade must make a recoverable
pre-migration copy and preserve it until post-upgrade validation succeeds.

## Security and privacy

- Credentials, raw user text, absolute user paths, and secret volume contents
  are excluded from source-controlled inventories and parity artifacts.
- SQLite and LadybugDB files live under the Angmoo application data directory,
  not inside the install directory or repository.
- The local administrator remains inside the stated trust boundary. Browser,
  frontend logs, diagnostics, Issues, and CI remain outside credential access.
- `local-v2` credential envelopes and fail-closed secret-loss behavior remain
  unchanged until a separately reviewed migration says otherwise.

## Consequences

The release can eventually remove PostgreSQL, Node, Neo4j, and JVM child
runtimes from the ordinary user process tree. In exchange, Angmoo owns SQLite
write serialization, LadybugDB projection/replay, sidecar lifecycle, static
routing, native dependency updates, and migration compatibility. The checked-in
inventories and L3 parity oracle make that responsibility reviewable.

## Rejected alternatives

- Keep Docker as the only user distribution: simplest operationally, but keeps
  a large runtime and developer-oriented lifecycle for ordinary users.
- Embed Neo4j: Neo4j is a server/JVM runtime, not an embeddable Python library.
- Make the graph store canonical: this would lose the current PostgreSQL
  source-event verification and replay contract.
- Rewrite product behavior during storage migration: this makes parity failures
  impossible to attribute and is outside ER0-ER7 scope.
