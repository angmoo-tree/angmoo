# P8-L-R Memory owner control UI

Status: implemented on `feat/p8-l-r-memory-owner-control-ui`; local, Hosted,
user and merge Gates remain separately recorded.

Issue: `#248`

Exact predecessor: P8-L-Q merge
`cb7e32a7d77937f5e117eb8c99b21dd0d77de42d`, tree
`386fa5efd6e1ad464bca57e9a00d0148297730fd`.

## Outcome

P8-L-R turns the read-only P8-L-Q `/memory` workspace into an authenticated
owner control surface. The Local owner can save Memory ON or OFF for one exact
`(owner, World, remembering WorldCharacter)` scope, pin or unpin an active
item, replace an item with a corrected summary, and tombstone an item.

This slice changes control, not authority. Canonical SQLite remains the source
of truth. The private FTS5 index remains a disposable projection and no LLM,
raw SQL, raw Cypher, source locator or provider payload crosses the owner API.

## Ownership

```text
HTTP composition
  app.api.v1.routes.memory
       |
       v
domain-first backend
  domains.memory.application.scope_control
  domains.memory.application.write_lifecycle
  domains.memory.ports.repository
       |
       v
runtime adapters
  SQLAlchemy canonical repository
  canonical source evidence reader
  after-commit private FTS5 projection

Next/static route composition
       |
       v
feature-first frontend
  features/memory/{api,model,ui}/public.ts
       |
       +-- wide MemoryWorkspace
       +-- narrow Browser one-column reflow
```

The application layer has no FastAPI, SQLAlchemy, runtime or provider import.
The API route composes concrete adapters. The frontend route imports the
feature public boundary, and Memory policy does not move into `shared`.

## Owner mutation API

Every route derives `owner_id` from the authenticated Local principal and
requires the exact World and remembering WorldCharacter in the URL. Each body
forbids unknown fields, carries a version, and carries an opaque 8..128
character idempotency key.

| Method and route | Canonical effect |
|---|---|
| `PUT .../memory/settings` | save an explicit ON/OFF target; absent read version `0` is accepted only for the first write |
| `PUT .../memories/{memory_id}/pin` | pin or unpin one active item |
| `POST .../memories/{memory_id}/corrections` | create one evidence-bound replacement and supersede the old item |
| `DELETE .../memories/{memory_id}` | tombstone the item so canonical retrieval rejects it immediately |

Mutation requests require the authenticated Local frontend mutation origin.
Cross-owner, cross-World and cross-subject resources are indistinguishable
from missing resources. Malformed input is `422`, stale version or invalid
lifecycle is `409`, and a transient adapter failure is `503`.

Target-state ON/OFF and pin/delete replays are no-ops. A correction derives a
stable internal replacement ID from its scope, old item ID and idempotency key,
so a transport replay returns the same replacement rather than creating a
second memory. The API returns only the safe scoped product item and the
generic `automatic_after_commit` projection-cleanup contract.

## Correction and deletion safety

Owner correction changes the stored summary but does not turn owner text into
new source evidence. Before supersession, code re-reads every evidence row and
requires the same source identity, digest, World, successful state,
visibility, observation, active membership and unblocked state. If any source
is stale or unavailable, correction fails without changing either item.

On success, the replacement preserves the existing typed Memory kind and
scope, carries only the revalidated evidence, receives a fresh retention
window, and becomes active. The old item becomes `superseded` and records only
the replacement product ID. Canonical retrieval already rejects superseded,
deleted and expired items.

Delete commits a canonical tombstone before success is returned. Therefore a
stale projection cannot make the item retrievable: the typed recall path
revalidates canonical lifecycle. Pinning excludes an active item from normal
retention expiry; unpinning restores the saved retention policy. Existing
items can be pinned, unpinned or deleted while Memory is OFF, but correction
requires ON because it creates a new active item.

## Projection cleanup

The existing after-commit Memory projection listener observes scope-setting,
item and evidence changes:

- OFF tombstones every private recall document in the exact scope;
- ON rebuilds that scope from current canonical records;
- pin/unpin refreshes the affected item;
- supersession tombstones the old item and indexes the replacement;
- delete tombstones the deleted item.

Projection failure occurs after the canonical transaction and cannot roll it
back. The projection becomes degraded and is rebuilt from SQLite later. The UI
therefore reports that cleanup is automatic without claiming that a derived
index is canonical or exposing internal projection errors.

## Frontend interaction

The same `MemoryWorkspace` serves Next and static Browser composition. It
presents:

- an explicit `기억 켜기` or `기억 끄기` saved-state action;
- active-item `고정/고정 해제`, `정정`, and destructive `삭제` controls;
- a correction Dialog that explains supersession and limits text to 2,000
  characters;
- a delete confirmation Dialog that states immediate recall exclusion;
- one pending mutation at a time while scope selectors and conflicting actions
  are disabled;
- bounded success copy, transient same-idempotency retry, and stale-version
  `최신 상태 불러오기` recovery.

The UI never optimistically claims a canonical write. It updates only from a
validated mutation response or an exact-scope refetch. A successful correction
opens the replacement item; a successful deletion removes the item from the
list and clears the selection. At 799px and below, the existing workspace
reflows to one column without creating a second Phone-only implementation.
The Tauri `memory` window and Phone rejection policy do not change.

## Persistence and compatibility

P8-L-R adds no table, column, Alembic revision, Embedded SQLite schema version,
LadybugDB generation, provider or dependency. It uses the canonical Memory
schema and private FTS5 projection delivered by P8-L-F~Q. Existing installer
predecessors and P8-L-P Chat/model contracts remain unchanged.

## Verification boundary

Focused backend tests cover CSRF, absent-setting version `0`, ON/OFF saved
state and replay, exact-scope isolation, OFF-state pin management, stale
version conflict, evidence-revalidated correction, deterministic correction
replay, supersession, stale-source rejection, deletion replay and immediate
canonical retrieval rejection. Browser tests execute the owner sequence in
the shared Next feature and verify narrow reflow; static export continues to
compose the same feature.

The generated inventory
`docs/architecture/p8-l-r-memory-owner-control-inventory.json` freezes the
mutation routes, schema non-change, domain/feature boundary, predecessor
digest and security constraints. These are technical Gates only. P8-L-S still
owns installed-runtime parity, actual successful source-to-memory-to-later-chat
causal proof, OFF/correction/delete restart proof, visual/accessibility and
held-out quality/latency closeout.
