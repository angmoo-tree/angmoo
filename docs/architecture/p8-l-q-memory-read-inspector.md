# P8-L-Q Memory read surface and evidence inspector

Status: implemented on `feat/p8-l-q-memory-read-inspector`; local and Hosted
verification remain separately recorded.

Issue: `#246`

Exact predecessor: P8-L-P merge
`df2edb4afe6991a33eb1db9398ac3f0fd20313d9`, tree
`679055c05e1091edc462de0a0cb169a1032ca505`.

## Outcome

P8-L-Q makes the canonical Memory data created by P8-L-F~P readable to the
authenticated Local owner. It adds a feature-owned `/memory` workspace and a
message-scoped evidence inspector without adding any Memory mutation.

The slice preserves two distinct truths:

- `Memory enabled` controls future candidate/write and retrieval use. It does
  not erase or hide already stored owner data.
- A stored memory or frozen answer snapshot does not prove that its source is
  still usable. Every detail/inspector read revalidates the current canonical
  source before exposing an excerpt or navigation target.

## Ownership

```text
HTTP composition
  app.api.v1.routes.memory
  app.api.v1.routes.world_chat_response
       |
       v
domain-first backend
  app.domains.memory.domain.read_surface
  app.domains.memory.application.read_surface
  app.domains.memory.ports.repository
  app.domains.chat.domain.evidence_bundle
       |
       v
runtime adapters
  SQLAlchemy canonical Memory repository
  canonical source reader
  World Chat response lifecycle repository

Next/static route composition
       |
       v
feature-first frontend
  features/memory/{api,model,ui}/public.ts
       |
       +-- /memory MemoryWorkspace
       +-- Chat MemoryScopeSummary
       +-- WorldChatEvidenceInspector Dialog
```

Domain/application modules contain no FastAPI, SQLAlchemy, provider SDK or
runtime import. The top-level API layer composes concrete repositories and
source readers. Chat imports Memory UI only through `features/memory/public.ts`.
No World, Memory or evidence policy moves into `shared`.

## Read API

All routes require the authenticated Local frontend and derive `owner_id` from
that principal. No route accepts an owner ID from the client.

| Method and route | Result | Mutation |
|---|---|---:|
| `GET /api/v1/worlds/{world_id}/world-characters/{subject_id}/memory/settings` | side-effect-free saved/default-OFF view | 0 |
| `GET /api/v1/worlds/{world_id}/world-characters/{subject_id}/memories` | stable, bounded owner+World+subject page | 0 |
| `GET /api/v1/worlds/{world_id}/world-characters/{subject_id}/memories/{memory_id}` | lifecycle plus currently revalidated provenance | 0 |
| `GET /api/v1/worlds/{world_id}/chat/threads/{thread_id}/requests/{request_id}/evidence` | committed answer evidence snapshot after current revalidation | 0 |

The setting GET must not call `get_or_create_scope_setting`. An absent row is
presented as `configured=false`, `enabled=false`, provider `none`, default
retention and version `0`. List pages are capped at 50 and use an opaque stable
item cursor. The UI currently requests pages of 20.

The list and detail DTOs expose a product resource `memory_id`, summary,
lifecycle, dates, pin state, supersession destination, retention policy and a
safe related-Character presentation. They do not expose owner IDs, source IDs,
source digests, database tables, FTS query text or provider material.

## Current-source revalidation

For every Memory evidence row, the application re-reads the canonical source
under the same owner+World+subject scope and accepts it only when all of these
remain true:

1. source type, source ID, source World and stored digest still match;
2. the source operation succeeded;
3. the source is visible and observed by the subject;
4. relevant membership remains active;
5. the source is not blocked;
6. the requested memory belongs to the exact scope.

An accepted source may expose a bounded excerpt, safe Character presentation
and an allowlisted product route. A hidden/deleted post or reply is reported as
`deleted`; any other mismatch is `unavailable`. Neither state exposes the old
snapshot text or canonical link.

Memory lifecycle is derived without mutation as `active`, `expired`,
`superseded` or `deleted`. P8-L-Q does not revive or rewrite any item.

## Chat evidence inspector

P8-L-P's immutable Evidence Bundle now carries a typed, private revalidation
locator. At the fenced assistant commit, code stores an
`evidence-inspector.v1` snapshot under the private
`_evidence_inspector_v1` response-metadata key. It is not returned by normal
generation request/status DTOs; those presenters strip underscore-prefixed
metadata.

The locator can name only one of these bounded kinds:

- canonical source: closed `MemorySourceTypeV1` plus source revision;
- canonical Memory item: item ID plus item version;
- graph relationship: canonical relationship-state ID/version and exact
  actor/target WorldCharacter IDs.

The inspector accepts only a committed response owned by the requested thread
and World, caps output at 12, and revalidates every locator against current
SQLite truth. Graph state must still match exact World, direction and version,
both roles must remain valid, and the pair must not be blocked. A Memory item
must remain active with a matching version and at least one currently available
canonical evidence source.

The public Chat thread DTO contains only deterministic summaries:
`request_id`, committed assistant message ID, `available|degraded`, and count.
That summary decides whether the `근거 N개 보기` action exists. The Dialog
fetches the full safe view only after an explicit user action. Missing locators
or stale/deleted sources degrade to `unavailable`; they do not fail the whole
Dialog and never reveal frozen text.

Raw prompts, raw Router/Planner output, SQL/Cypher, tokens, provider bodies,
credentials, source IDs/revisions and the private locator are not part of any
public inspector DTO.

## Frontend surfaces

`features/memory` owns one API/model/UI implementation shared by Next and the
static product router.

- `/memory` is the canonical Browser route.
- `/memory-explorer` is a hidden compatibility redirect to `/memory`; it is not
  a second product surface.
- Tauri window kind `memory` is a singleton wide window with `/memory` as its
  exact path. Query keys are limited to `world`, `subject`, `memory`, with
  `subject -> world` and `memory -> subject` dependency checks.
- The Phone window rejects `/memory`. A Phone Chat link opens the wide Memory
  window; the small answer-level evidence view stays a shared Dialog in Chat.
- A narrow Browser may render `/memory` and reflows the two-pane workspace to a
  single column at 799px and below.

The workspace presents explicit loading, no-scope, empty, not-found/forbidden,
degraded-source and transport-error states. An invalid requested World or
subject never silently falls back to a different scope. Memory OFF is shown as
an informative state while existing items remain readable.

No ON/OFF switch, pin/unpin, correction or delete control appears in this
stage. Those mutations and their optimistic-version/idempotency contracts are
owned by P8-L-R.

## Persistence and compatibility

P8-L-Q adds no canonical table, column, Alembic migration, Embedded SQLite
schema version or LadybugDB generation. It reads the P8-L-F~P SQLite v7 data and
stores the inspector snapshot in the existing response metadata field. All
supported installer predecessors and P8-L-P model-binding semantics remain
unchanged.

## Failure and security contract

- cross-owner, cross-World and cross-subject Memory reads fail closed;
- an outsider cannot inspect another thread's response evidence;
- a non-committed or non-matching request has no inspector;
- source revision, visibility, observation, membership or block drift removes
  excerpt and navigation before the response is returned;
- all Memory API calls in this stage are GET; setting reads create no rows;
- no provider call, Memory candidate, graph projection or FTS rebuild is
  triggered by viewing the workspace or Dialog;
- read failure cannot silently enable Memory or mutate lifecycle state.

## Verification boundary

The generated inventory
`docs/architecture/p8-l-q-memory-read-inspector-inventory.json` freezes the
exact files, predecessor digest, read-only routes, caps, schema non-change,
domain/feature ownership and deferred scope. Focused backend tests prove
side-effect-free setting reads, OFF-data readability, current-source revision
failure, owner/subject isolation, Chat inspector privacy and locator-less
degradation. Next and static Playwright tests cover the workspace, narrow
reflow, canonical links and Chat Dialog; Rust tests cover the singleton wide
window and strict route/query allowlist.

These tests are technical evidence only. P8-L-Q is not P8-L full PASS. P8-L-R
still owns Memory mutations, and P8-L-S still owns installed-runtime,
accessibility/visual, held-out routing, causal source-to-memory-to-later-chat
and user closeout.
