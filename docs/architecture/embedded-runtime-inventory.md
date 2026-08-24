# L3-ER0 inventory and ER7 residual audit

- Source baseline: `db1c32510f66cee20a3e64a01e85c5ea8753d77e`
- Public tracking issue: [#97](https://github.com/angmoo-tree/angmoo/issues/97)
- ER0 baseline behavior change: **zero**
- ER7 PR P current default: **SQLite/FTS5 + LadybugDB + in-process components**

## Reproduce the inventory

Run from the repository root with Python 3.13 or newer:

```powershell
python scripts/verify_embedded_runtime_inventory.py --write
python scripts/verify_embedded_runtime_inventory.py --check
```

`--write` regenerates all source-derived JSON using sorted paths, stable JSON,
and SHA-256 source hashes. `--check` fails if a checked-in artifact is missing,
stale, incomplete, or violates the frozen corpus.

## Frozen counts

| Surface | Count | Artifact | Transition owner |
|---|---:|---|---|
| Residual PostgreSQL-marker files | 67 | `postgres-sql-inventory.json` | frozen migration/history audit |
| Alembic version files | 81 | `migration-conversion-inventory.json` | ER2 |
| Neo4j static queries | 24 | `neo4j-query-corpus.json` | ER3 |
| Next pages and route handlers | 39 | `next-static-compatibility.json` | ER5 |
| P1-P7 parity workloads | 7 | `embedded-runtime-inventory.json` | ER0-ER7 |
| Scheduler/projector/API coupling files | 9 | `embedded-runtime-inventory.json` | ER4/ER7 |

Every generated entry carries an owner, transition PR, source hash or line,
and removal condition. Existing compatibility paths can be removed only when
their recorded condition passes.

## PostgreSQL and migration inventory

`postgres-sql-inventory.json` searches Python, Compose, scripts, and dependency
metadata for drivers/URLs, JSONB, pgvector, row locks, `SKIP LOCKED`, and
advisory locks. After ER7 PR P, a hit must be frozen `LEGACY_MIGRATION` input,
historical Alembic source, or dialect-neutral SQLite schema translation
metadata. It is not evidence of a supported PostgreSQL application runtime.

`migration-conversion-inventory.json` parses every file under
`backend/alembic/versions`. All 81 paths and revision identifiers must be
unique. Files with PostgreSQL-specific markers are marked
`translate-and-validate`; the rest still require `schema-parity-review`.

## Neo4j query corpus

`neo4j-query-corpus.json` freezes the former bootstrap DDL, projection writes,
delete/source-exclusion behavior, maintenance/digest queries, typed reads, and
the dynamic bounded 1-3 hop path generator. The typed corpus includes direct,
reverse-capable shared-neighbor, path, positive/tense/recent ranking, evidence,
and visualization semantics. ER3 reproduced their World-scoped results and the
L3 oracle digest in LadybugDB. ER7 consumes this file as static evidence only;
there is no live Neo4j server, driver, JVM, or public runtime.

## Next.js static compatibility

The same frontend source supports Next.js development in the Docker contributor
stack and the static-export profile embedded by Tauri. The route inventory keeps
direct-open and static-router compatibility reproducible.

## Runtime coupling and dependencies

`embedded-runtime-inventory.json` records the two-service contributor topology,
scheduler lease/fencing and signal paths, projector outbox/component/degraded
paths, FastAPI lifespan, behavior-critical file hashes, Python and Node package
manifests, Docker bases, future Rust/LadybugDB owners, and license evidence.

The current default dependency baseline is Python `>=3.13`, Node via
`pnpm@11.22.0`, Next `16.3.0`, and pinned `ladybug==0.19.1`. `psycopg` and
`pgvector` are isolated in the optional `legacy-migration` dependency group;
the Neo4j Python driver is absent. Rust/Tauri remains the installed-product and
optional platform-shell layer, while ordinary contributor development uses the
Linux Docker two-service stack.

## Resource baseline

The non-secret live capture is stored in
`embedded-runtime-resource-baseline.json`. It records a six-healthy-service
Windows Docker development stack, images, canonical volume sizes, one-shot
container resource samples, and observed start/UI timings. Build cache is
reported separately because contributors build images while ordinary GHCR
image users do not.

The baseline is diagnostic evidence, not a performance promise. Repeating it on
different hardware must create a new reviewed capture rather than modifying the
source-derived generator.

## Parity oracle and workload

The merged oracle is:

```text
docs/architecture/l3-er-postgres-neo4j-parity-oracle.json
```

Its integrity is included in `embedded-runtime-inventory.json` as SHA-256. It
contains structural PostgreSQL row digests, Neo4j projection and typed-query
digests, migration round-trip evidence, privacy flags, provider call count, and
clean-clone evidence. It intentionally contains no credential, raw user text,
or absolute user path.

Rebuild the oracle only through an explicitly reviewed closeout run; verify the
frozen schema and current digest with:

```powershell
python scripts/verify_embedded_runtime_inventory.py --check
python -m pytest -q tests/test_l3_closeout_contract.py
```

The workload map fixes P1 World lifecycle, P2 three-request/40-candidate setup,
P3 zero-call deterministic four-item planning/no-catch-up, P4 atomic two-call
continuation, P5 keyword/reaction intent, P6 directional evidence-backed
relationships, and P7 replay/outage/query parity. Later ERs may change adapters,
not these outcomes.

## ER0 closeout boundary

ER0-ER6 are complete. ER7 PR O made typed embedded composition canonical and
PR P removes the default PostgreSQL/Neo4j server topology while establishing
the official Docker `frontend + backend` contributor runtime. Final ER7 PASS
still requires PR P local/Hosted/user gates and merge; this inventory alone is
not completion evidence.
