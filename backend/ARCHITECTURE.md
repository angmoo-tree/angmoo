# Angmoo Backend Architecture

## Situation embedding delivery groups (2026-10-16 LOCAL)

The situation runtime prepares at most 32 receipts per turn, still committing
one receipt per existing fenced UoW and yielding its canonical queue between
receipts. Dirty-brief rebuilding runs once after that bounded turn. It never
holds one write transaction across all receipts or an embedding request.

Initial vector delivery coalesces applied receipts from the same admitted run.
The existing run cutoff/state and atomic eligibility registration own recovery;
no new table, timer or authorization cache is added. A full model-sized group,
run completion or producer error releases already prepared work. No later
unrequested receipt is awaited. Retry, expired-lease, changed and erased items
retain their existing independent delivery paths. Bounded read pagination keeps
waiting groups from hiding unrelated work. Committed eligible cohort members
whose outbox fanout has not arrived yet may be enrolled in the same short claim
transaction after a fresh registration/World-deletion check.

Runtime uses each model's batch capability, adapter method and declared limits.
Gemini embedding 2 retains the application limits of 20 independent inputs,
8,192 UTF-8 bytes per input and a 65,536-byte conservative serialized request
budget (JSON escaping plus per-item envelope); these are Angmoo
budgets, not a claim about the provider's maximum. Larger/longer groups split;
single-only providers remain single-input. Existing per-item source/credential
proofs, response mapping, result journals and short canonical-to-Vec1 effects
remain authoritative. Group readiness never substitutes for these validations.
See the [scoped delivery verification](../docs/verification/situation-embedding-batches-20261016.md)
for HTTP counts, contention recovery and deployment boundaries.

## SQLite recovery and private result delivery (2026-10-16 LOCAL)

Domains retain authorization, source validation, persistence and state transitions;
Runtime composes owned queues, projections and erasure. The common SQLite writer
pins its physical connection through commit/rollback and timeout restoration.
BUSY (including extended codes), queue/pool capacity, LOCKED, application defects
and post-commit cleanup failure remain distinct. A committed operation is never
replayed. Admission remains four bounded attempts / 0.25 seconds; the next worker
turn uses its existing owner and lease, not nested unbounded retries.

Situation application commits one receipt plus its evidence/counters/cursor.
After binding flush, one synchronous, same-Session MemoryAccessValidation batches
the current rows and lineage for that receipt; it never crosses a write, await,
receipt or transaction. Relationship preparation reads the complete cutoff before
creating a target/period root, then revalidates policy, environment, credentials and
every input in a short target writer. Existing root/partial/reduce receipts remain
the restart ledger. No new canonical schema or validation staging ledger is needed
for the measured high-fanout fixtures; future growth must be measured again.
`SituationSources` remains a lower-level canonical source reader;
`PreparedSituationSources` composes episode/access batching only at the application
boundary. Relationship execution and result delivery depend on shared
`review_payloads` operations, never on each other. Provider batch transport receives
its provider-owned error normalizer rather than importing its caller.

The existing vector worker uses model-declared optional embedding batch limits.
Only eligible missing/changed vectors are grouped by scope, settings, credential
revision, model and profile. The Gemini adapter owns explicit Content boundaries
and one physical HTTP request; providers with only single-input support remain
valid. Query embedding remains single-input with its original deadline. Runtime
holds no Session across provider awaits and revalidates each item before its
idempotent Vec1 write. Request usage is counted once, not once per vector.

Core ResultJournal owns bounded private files and content-free erasure fences;
it has no ORM or provider policy. Relationship and embedding owners bind records
to their current manifest/attempt or content/scope/credential digest, preserve
received results before retrying local storage and remove them after delivery.
World erasure closes both journals before canonical cleanup. Individual memory
privacy erasure also closes the item even if no vector generation exists. A crash
before durable receipt is not reported as recovered provider output.

World file cleanup uses explicit direct-URL, image-profile, origin and draft
selectors. Embedding profile strings are never parsed as image JSON. Exact file
generation, live references and deletion epoch are checked before unlink in a
non-replayed short writer; external graph/index/checkpoint effects remain outside
canonical transactions and have fenced acknowledgements. Defaults, original
character assets and other Worlds remain protected. Scheduler and SNS settlement
keep their existing durable owners and fences; they do not gain a second retry loop.

Image HTTP diagnostics preserve the original error and distinguish observed
transport stages from local storage. The allowlisted DTO is bounded, contains no
remote body/prompt/key/URL, preserves existing HTTP timeouts and never authorizes
another generation. Identity returns typed 503 only after rollback-confirmed
contention; revision conflict stays 409. Technical checks and operational user
checks are separate: [execution evidence](../docs/verification/sqlite-recovery-world-erasure-20261016.md).

## World owner-profile notifications (2026-10-15 LOCAL)

Social owns notification DTOs, the shared eligibility query, delivery identities
and HTTP services. Runtime supplies bounded multi-domain reads using the caller's
Session. Scope is the claimed local owner's active owner-controlled World profile;
GET never ensures a profile. Home resolves up to 50 unique visible World IDs in
one batch, with unavailable per ineligible World and no all-owned-character fallback.

Canonical writers deliver in their existing UoW: immutable Post IDs for
reply/quote/mention; successful SocialEvent IDs for like/repost/follow. The nullable
unique delivery key deduplicates replay without resetting read/handled state.
SQLite v38 / Alembic 20261015_0115 adds the field/indexes. Earlier manifests and
data remain immutable. Migration fences use the actual schema generation; v38
refreshes only Notification write fences in its migration UoW.

List/count/read share visibility, ancestor, block and live-reaction predicates.
Visibility projects post ID, World and parent into one materialized scoped set
before recursive reachability; this avoids a World-only Post index rescan for
each descendant without adding a schema/index or dropping ancestor/block checks.
Explicit user read updates only the first read_at and returns canonical count;
it creates no activity/relationship/memory event and never modifies handled_at.
The read-all POST compares the expected recipient with the currently authorized
scope inside the caller's immediate UoW. One set-based UPDATE covers eligible
unread rows across all pages, preserving prior read_at values and later deliveries.
SQLite changes() is read on the same connection because CTE UPDATE rowcount may
be -1. There is no row-by-row commit, new schema, provider I/O or automatic replay
after uncertain transport outcomes. The individual endpoint remains compatible.
Closed post/profile targets grant no additional reader permissions. Evidence:
[focused verification](../docs/verification/world-user-notifications-20261015.md).
Bulk-read follow-up: [scoped verification](../docs/verification/world-notifications-bulk-20261015.md).

## SNS recovery and canonical receipt boundaries (2026-10-14)

Social owns bounded received-result slots and attempt-bound atomic journals;
Media owns pixel preparation and asset registration. Runtime injects their
existing interfaces and owns canonical worker/session/future lifetimes. Durable
received state requires verified bytes; no automatic replacement submission is
authorized by a lost result. Activity recovery validates current scope/claims
and exact committed effects/state/situation receipts before old snapshot guards.
Memory prepares immutable bounded pages outside the writer and freshly validates
the prefix under its existing SQLite UoW. Relationship validation batches only
within one guard and distinguishes canonical read failures from changed facts.
See [source verification](../docs/verification/sns-recovery-consistency-20261014.md)
for regression evidence and separate deployment/provider limitations.

## Current CI protection after completed refactors (2026-10-14)

Current import boundaries, ownership, authorization, persistence and runtime behavior
are the executable architecture contract. Completed refactor evidence remains historical
documentation; routine CI no longer requires retired forwarding bodies, exact historical
AST copies or frozen M3/M4 test names. Their current behavior remains covered by the
runtime composition, ASGI, Chat ownership/lifecycle and architecture-boundary tests.
CI full runs collect the complete current corpus. Scoped runs record and verify the
current collection, dependency selection and exact executed union; unknown impact
expands validation. See [CI validation](../docs/operations/ci-validation.md).

## World image reads and own-profile media contracts (2026-10-12 LOCAL)

Worlds owns current icon/banner pixel reads in `service/media.py`. Both the
retained `/media/worlds/{world_id}/{filename}` and API
`/api/v1/worlds/{world_id}/media/{filename}` paths reuse this service and the
existing World read policy. Active membership grants the existing private/draft
read; anonymous access is only published public/unlisted. Current persisted image
reference, bounded filename, World directory and symlink checks precede FileResponse.
Main composes the compatibility router; common public media mounts do not expose
the World directory or private asset/draft/candidate directories. Reads use
private/no-store responses and preserve existing files, URLs, package IO and schema.

Own-profile upload keeps its strict four-field schema, owner and version guards.
Worlds frontend serializes only those fields from the shared Characters crop
payload. The identity response projection includes its existing handle/banner
fields so saved values survive upload and reload; no new stored field is added.
Evidence: [focused image recovery](../docs/verification/world-image-recovery-20261012.md).

## Chat advisory interpretation and fresh canonical reads (2026-10-11 LOCAL)

New `social_hybrid` Chat admissions freeze the server-owned
`_selection_protocol=selection-args.hybrid.v3`. The three native functions keep
their core execution contracts; an optional `entities` list supplies person names
and nullable roles only. There is no relationship-pair or model-created ref field.
Chat owns bounded pure normalization (scan 32, deliver 4, name 160), immutable
`person-hints.v1` and request/identity/core/evidence binding in `hybrid-admission.v3`.
Invalid hints are omitted or partly retained without repair or response failure.
Core search text, scope, ranking, permissions and actual source proof still fail
when invalid. Hints do not rewrite queries or filter the authorized memory set.

Only frozen requester/responder names (and actually supplied handles) can confirm
a hint, without additional person lookup SQL. Other names remain `not_checked`.
CRG reads usable names/roles/status alongside the complete original question,
verified participants and authorized evidence. It preserves actual fact/direction,
uncertainty and persona rules and can interpret the question when hints are absent.
Common role and speaker/quotation definitions are reused; English instructions do
not change situation descriptions' admitted `memory_search_locale`. One final
payload still feeds both situation and relationship delivery captures.

Historical v1/v2 schemas, names/endpoint validators and hashes remain supported.
Pending/idempotent requests retain their admitted protocol. An explicit retry with
retained identity creates a new v3 attempt preserving question, model, environment,
settings, identity and situation policy; history without identity keeps its old
contract. Damaged markers/identity fail before provider work. Both v3 Supervisor
and CRG awaits checkpoint caller read transactions; leases and final fences remain.

Memory owns `MemoryAccessValidation` and batched Memory rows/bindings/unique prior
nodes, scoped to one read Session and one timestamp. Runtime owns foreign current
Post/Reply/Chat/routine/image facts through injected read ports. Cycles are checked
before completed-node memoization; each receipt/manifest/ordinal/range is validated.
Candidate, hydration and final provider/application guards each open fresh contexts.
Owner detail and Chat inspection share exact situation entry resolution, including
nullable evidence and corrections. A damaged situation origin cannot become legacy
Feed authorization. Memory OFF permits owner inspection, without source ACL bypass.
Original links are only canonical World POST/REPLY routes.

Production hybrid recall uses a separate Runtime canonical worker (one worker,
capacity eight). Queue wait, axes, validation and hydration share one absolute
deadline; SNS includes its semaphore wait in the existing 15 seconds. Sessions
open inside the worker, SQLite progress/busy limits are restored in finally,
cancelled running futures remain owned, and shutdown drains before engine dispose.
Only immutable results and bounded diagnostics cross back to the parent. SQL,
completed privacy nodes/memo hits, queue wait and cleanup counts remain unknown
when not observed. No request collector or Session crosses the thread boundary.

Evidence: [integrated implementation and scoped verification](../docs/verification/chat-memory-world-integrated-20261011.md).

## Runtime contention recovery and Media SQL ownership (2026-10-11 LOCAL)

Runtime Media owns a bounded, single-worker `SqliteAsyncTaskQueue`, using the same
cancellation/drain contract as `MemoryCanonicalWork`. Image job discovery, leased
preparation, submission/receipt/diagnostic transitions, result persistence and
maintenance open and close their own Sessions inside that worker. Provider I/O
stays asynchronous. Request Sessions and ORM entities never cross this boundary;
ownership/settings rechecks, quotas, result spooling and lease-token fences remain.
Shutdown stops producers and drains running local work before unregistering Media.

The graph projector retains its registered loop after canonical checkout timeouts
and reports degraded until a real successful batch/probe. Backoff is bounded at
30 seconds with the normal runtime polling interval. Memory FTS page failures retry
without requiring a new commit, retaining 32-item pages and the existing
build/validate/orphan/promotion fence. Persistent failures remain degraded.
Unsaved-experience pages share `MemoryAccessValidation` only within one synchronous
request, Session and timestamp; every later read revalidates current source/access.
Pool capacity, readiness/health criteria and authorization policies are unchanged.

Evidence: [implementation, tradeoffs and local Docker checks](../docs/verification/docker-runtime-limited-features-20261011.md).

## Chat participant presentation and historical relationship evidence (2026-10-11 LOCAL)

Chat admission derives `chat_identity_context.v1` from the existing NameBinding v1,
freezes the actual World requester/responding identities for the request, and rejects
damaged or mismatched namespaces before provider work. Runtime batches only selected
effective World names. Neutral episode/Today values carry private, verified source
authors from the original Post or Thread role; shared SNS packet serialization and
legacy source hashes exclude those identities. Integrations adds only Chat presentation
names and selected opaque participant links, preserving raw source text and provider
message/schema contracts. One final payload feeds serialization and both delivery captures.

Memory owns the explicit `episode-packet.v1` delivered-source projection. Packet
serialization and SNS snapshot currentness comparison share that same projection;
private canonical author metadata never becomes model input or an accidental
source-change signal. Current scope/access, source digest/status, delivered text,
role/range, thought and follow-up checks remain; unexpected delivery fields fail
the exact comparison. This requires no stored-data rewrite or provider call.
Evidence: [SNS currentness regression and scoped Docker checks](../docs/verification/sns-memory-source-currentness-20261011.md).

Chat finalize binds `relationship-evidence-delivery.v2` to request, scope, generation,
slot, attempt and actual JSON/user-prompt digests in the existing canonical UoW. It is
independent of Memory enablement or receipt processing. Committed evidence reads validate
the retained proof and current canonical authorization through Runtime, on the caller's
Session, without graph projection or writes. A normal later version/view change displays
verified frozen facts as changed; lower versions, damaged facts or lost access do not.
Only retained, bound legacy delivery material can recover a historical graph excerpt.
The public v1 DTO adds safe projections/change status and separates original retrieval
limitations from current read limitations; private proofs and IDs are not exposed.

Evidence: [implementation and scoped checks](../docs/verification/chat-identity-evidence-preview-20261011.md).

## Memory validation and runtime responsiveness (2026-10-10 LOCAL)

Memory keeps current scope, participants, blocks, private-thread access, delivered
proof, source digests, prior versions and cycle checks. `MemoryAccessValidation`
belongs to one synchronous read operation with one Session and timestamp; it
memoizes shared lineage and canonical facts only inside that operation. It must
never be retained on a reader, Session, runtime or index, or reused across writes,
provider waits or later requests. Final canonical hydration and post-provider
application still perform fresh validation.

Runtime owns the execution boundary. The FTS after-commit listener only enqueues
bounded identifiers and never waits for a projection lock, opens a new Session or
revalidates history on the HTTP/scheduler loop. One owned worker reconciles current
SQLite rows, drains committed edits, and rebuilds in 32-item pages with the existing
build/validate/orphan/promotion fence. Overflow requests a bounded rebuild;
restart reconciliation recovers an interrupted in-memory queue. Canonical recall
still rejects stale or forbidden candidates while derived work catches up.
Whole-library FTS rebuilds keep the existing `MemoryRecallPreparing` fence until
validation and promotion finish.

The situation consumer and vector source lookup use a single-worker bounded
`MemoryCanonicalWork` queue per runtime. Sessions open and close inside the worker;
only immutable documents/results cross the boundary. Cancellation keeps running
futures owned and shutdown drains them before disposing the canonical engine.
Situation application retains its cutoff, admission, source and lease checks in
16-receipt transactions. Dirty briefs advance one scope per transaction with a
cursor that also advances past invalid scopes. Quit preparation/fencing uses the
same serialized worker and search drain includes queued FTS commits. Provider I/O
and the vector's final canonical write fence keep their existing contracts. The
scheduler lease TTL, heartbeat checks and Compose health contract are unchanged.
[Implementation, tradeoffs and local Docker validation](../docs/verification/docker-backend-memory-startup-20261010.md)

## SNS stored-text comparison and immutable result recovery (2026-10-10)

Social owns the strict `social-visible-text.v1` expected-output projection and
reuses its existing title/body sanitizers once. Runtime compares the selected
final draft in that representation with the independently stored Post in the
caller-owned Session. Actions, targets, effects and substantive content remain
separate guards; Chat text does not use this Social projection.

Memory separates restored immutable admission material from trusted validation
context. Only an explicit, lease-fenced v4 blocked recheck can approve an
append-only result binding after exact original planned/final hashes, source,
scope and access checks. Runtime supplies a bounded read-only checkpoint basis
through a typed port. Receipt, manifest and prior v2/v3 rules remain immutable;
v3 parent bindings continue to work. Successful proofs and memories share the
existing outer UoW, failed checks roll back tentative proofs, and reads restore
the saved proof without checkpoint I/O. The proof retains its original run ID
when mutable processing history is pruned. Current source/access guards remain.

SQLite v36 / Alembic 20261010_0113 adds the empty result-binding table after
v35/0112, preserving frozen prior metadata and staged upgrade failure behavior.
The auxiliary `situation-observation.v1` capability uses the existing opt-in,
bounded SNS recorder; Memory's pure parser owns structural interpretation.
Physical/JSON/stage attempts and final Writer selection are explicit. Committed
receipt diagnostics follow the existing outer commit and never own a commit.
Auxiliary export completeness is independent of core schema3 completeness and
AI quality. External PowerShell/Python collectors stay outside app workers,
read canonical data without mutation and terminate after bounded finalization.
[Implementation and scoped validation](../docs/verification/sns-result-normalization-observation-20261010.md)

## Basic activity settings, SNS parent evidence and World topic retirement (2026-10-10)

WorldCharacters owns the strict `world-activity-settings-v1` projection and its
eight policy fields. Basic and detailed saves share configuration normalization,
configuration CAS and the caller's Session. Runtime composes a saved-facts
activation decision for GET, dashboard and actual ON admission: published World,
eligible actor, saved policy and SNS purpose/model/key, readiness and maintenance.
An owned pending/inactive/active autonomous actor with an active membership may
save basic settings and SNS/image credentials before publication. This exception
does not grant Chat, vision, graph, general profile or autonomous execution access.
OFF does not cancel an already admitted activity. Image options, provider vault
revisions, blank-key preservation and explicit connection checks remain owned by
Identity/Media. Character registration returns the durable `registration_scope`
for the atomically registered OFF actor, including idempotent completion replies.

Social's TodayActivityRecord carries `parent_post_id` alongside the delivered
parent body/title, independently of source/target/root IDs. Both producers reuse
the parent they already loaded. The final bounded provider payload must retain
the pair; inconsistent input is rejected before provider submission even when
Memory is OFF. Runtime captures the actual parent fragment with its payload hash.

Memory owns the typed parent-binding contract, exact pure policy, append-only
`memory_situation_source_bindings` repository and validation revision v3. The
Runtime adapter reads canonical Social rows in the same Session through the
optional typed resolver. Memory imports no Social persistence model. Original
manifest, admission, call, scope, result and description integrity is checked
before loading a binding. Historical correction requires the exact parent-body
path, an unchanged same-record child and its frozen direct-parent relationship,
the full original parent-body SHA256, delivery ranges/payload and current access.
No search, similarity, guessed IDs or source mutation is used. The fixed proof
view serves application, details/correction, recall/hydration, prior memory and
HotBrief access checks; later child/parent edits, reparenting or access revocation
still prevent return. A receipt savepoint rolls back tentative bindings on failed
validation; successful bindings, Memory/evidence, incremental eligibility and
receipt share the outer UoW. A shared manifest retains its proof until its final
dependent is removed. Older unfinished v2 runs retain v2 rules; unknown revisions
stop, and only a new explicit request can use v3. GET/startup/migration never
recheck blocked receipts. Existing individual/bulk recheck and discard are reused.

Embedded SQLite v35 and Alembic 20261010_0112 add the empty binding table after
v34/0111. Historical metadata builders/manifests are frozen. Copy/stage/validate/
promote remains the upgrade boundary; failure preserves the original DB, key and
selection marker. New accepted memories use existing incremental FTS/vector
registration and do not prepare the whole historical corpus.

World-level recommendation topic generation is retired after authorization with
`410 world_recommendation_topics_retired` for GET/key PUT/regenerate POST.
World create/publication/restart and late results cannot dispatch/apply it.
Catalog and relationship initialization remain independent. The matching
dictionary consists of valid character sources (including OFF/inactive actors),
retains common/World-scoped shared IDs, and excludes World-only/deleted/left
sources. Actor preparation, maximum six post links, cache invalidation, historic
PostTopic/epochs and delivery DTOs remain intact. No dependency was added.

## Image provider vault and supported creation methods (2026-10-09)

Identity owns `WorldImageProviderCredential`, keyed by owner, World, actor,
provider and credential purpose, with encrypted material, key revision and
tombstone. The existing WorldCredential remains the current executable
provider/model selection and preserves admitted execution revisions. Selecting
another provider reuses its active vault key without reading plaintext into a
DTO. Same-provider model changes reuse the key; explicit deletion tombstones
the vault and revokes that provider's execution copies. Other providers and
Comfy Partner remain independent. Current, provider-key and image-policy CAS
checks participate in the runtime's existing Session/UoW and rollback together.
Runtime composes authorization, policy invalidation and privacy deletion; domain
services do not import another domain's internal service or open nested Sessions.

ComfyUI accepts no server authentication key. Its separate Partner key is the
account credential used only in Comfy extra_data. Runtime resolution and the
HTTP integration reject retired server material before submission; external
service secrets cannot become Comfy server headers. Embedded SQLite v34 and
Alembic 20261009_0111 authenticate prior material before mutation, seed the
provider vault without reviving deletion, and retire Comfy server secrets from
current/history and legacy USER_IMAGE. Partner/other-provider material remains
protected. Previous manifests and migrations are frozen. Failed authentication
does not promote a staging DB or alter the source DB/selection marker.

Characters separates supported new creation inputs from legacy read types.
New local/external creation and new external draft registration are rejected
before side effects. Completed receipt reads remain idempotent. An owned,
unexpired editing external draft may be explicitly reselected as direct under
target/revision checks, preserving fields and temporary media in one transaction.
V1 adoption does not silently reselect; old credentials are not copied.

Memory admission, validation, apply, scheduling, shutdown, FTS5 and Vec1 behavior
is unchanged by the frontend saved-embedding controller. Related isolated and
mock evidence is recorded in [2026-10-09 verification](../docs/verification/world-ui-settings-improvements-20261009.md).

## Situation delivery validation and owner recovery (2026-10-08)

Memory owns `SituationValidationContext`, delivery/relationship policies, receipt
restoration, the common apply operation and owner recovery endpoints. Runtime
adapters read foreign canonical sources through injected ports and participate
in the existing Chat/SNS transaction. They never fabricate Feed observations.
`MemoryItemEvidence.observation_id` remains the actual Feed foreign key; an Inbox
fragment proved by a restored receipt uses the separate `situation_delivered`
origin and leaves that foreign key empty.

The v2 delivery manifest binds the actual final payload digest, JSON pointer,
fragment ranges, source identity and scope to the successful execution result.
Restoration verifies the stored manifest hash, receipt's original admission hash,
call/target/lane/epoch and committed effects before constructing trusted context.
Raw manifests, client flags and unsigned observation booleans cannot grant access.
Relationship background evidence carries the approved prepared version, view
version and facts digest. Normal later version increments preserve that history;
current World ownership, participants, blocks, thread access and source integrity
are still mandatory. V1 serialization and hashes remain unchanged; insufficient
historical relationship proof fails closed.

Apply, correction lineage, canonical/hybrid recall, prior memories, HotBrief,
relationship review and source hydration share the restored proof and current
access checks. Hydration reads only allowed delivered ranges. Summary-only FTS and
vector preparation remain derived work after canonical commit, without library
backfill or provider calls inside save/recheck/discard transactions.

`pending_apply` and explicit `blocked_recheck` use the same bounded, lease-fenced
consumer. Individual recovery freezes one receipt and state version; whole-scope
recovery freezes a cutoff and processes at most 100 rows per page. Operation,
validation revision, scope, target and version bind idempotent requests, including
legacy save-key reuse. Recheck attempts record decisions atomically with item,
source, cursor and receipt updates; previous completed runs are immutable.
Operational `run_state=error` is distinct from a completed run with rejected rows.

Owner discard accepts only unapplied blocked receipts with a matching state
version, including Memory OFF/closed epochs. A live scope lease prevents races;
queued/deferred/error rechecks may record an atomic discarded/skipped attempt.
Discarded receipts are terminal and excluded from replay, counts and consumers.
Only their description, result detail and unshared manifest are removed; original
activities, other memories and shared manifests remain. Identity, content digest,
sequence, state version and discard time retain the minimal termination record.

SQLite v32 / Alembic 0109 is a forward delta from v31 / 0108. Frozen historical
migrations are unchanged. Embedded upgrade rebuilds affected tables only in an
unpublished staging database, preserving legacy rows, foreign keys, credentials
and receipt sequence high-water marks. Failure leaves the selected database and
marker unchanged. [Implementation and validation](<../docs/verification/10-08 Chat·SNS 상황기억 관찰 검증과 차단 기록 복구 구현 결과.md>)
separates local regression, isolated Docker, real AI and installed/user checks.

## Activity situation admission and deferred application (2026-10-08)

Memory owns `activity_situation` policy, immutable delivery manifests, receipts,
processing settings, accepted cutoffs, application runs and canonical metadata.
Chat and WorldCharacters consume neutral values from `contracts/activity_situation.py`;
Runtime injects policy capture and same-Session participation at their existing
admission/finalization boundaries. A receipt commits with the successful assistant
message, SNS target effects or Routine post. Invalid auxiliary descriptions do not
invalidate a valid base answer; a database admission failure rolls the activity back.

The final provider payload owns delivery proof after selection, truncation and
name binding. Source adapters revalidate the entire delivered scope and current
permissions, including prior memories and image interpretations. No original body
is copied into a replacement evidence store. Source deletion and changed/private
sources have distinct policies. Unknown policies fail closed.

Daily, explicit manual and authenticated host-quit requests use one Memory
application consumer. Each request freezes an immutable cutoff; bounded pages
atomically write MemoryItem, evidence, situation metadata and applied identity.
Ordinary activity, reads, settings saves and Memory ON do not trigger a flush or
whole-library indexing. FTS and Vec1 are derived from each committed summary.
Provider I/O occurs outside canonical write transactions. Shutdown observes only
accepted search work within its deadline and fences late projection results.

Relationship preparation, refresh and apply wait for their own scope's accepted
canonical work, then use the old/new memory union. Other scopes remain eligible;
neither vector readiness nor unrequested pending activities block relationship work.
Explicit D03 maintenance retires only its inventoried legacy queue and fences
re-admission. Ordinary forward migration preserves historical work and memories.
SQLite v31 and Alembic 0108 share the registered ORM; historical migrations remain
immutable. [Implementation and validation](../docs/operations/10-08-activity-situation-implementation.md)
records automated, synthetic-load and unperformed real-provider/native checks separately.

## Runtime diagnostic migration target (2026-10-07)

Runtime diagnostics composition reads the frozen manifest for the shipped
`SQLITE_SCHEMA_VERSION` and injects its `source_revision` into the Runtime
status service. Runtime domain policy compares the persisted revision with
that explicit target; it does not maintain a second release-version constant
or import persistence and migration implementations.

An actual old, unknown, or missing DB revision still reports
`migration_not_current`. Regression checks compare the manifest, SQLite
baseline lineage, Alembic head, and a real canonical DB independently, and
exercise a future packaged manifest without changing domain policy. This
diagnostic correction changes neither stored schema markers nor the startup
migration and component failure checks.

## Embedded migration credentials (2026-10-07)

Before upgrading canonical SQLite, the common embedded coordinator binds
`secrets/app-secret` from its resolved data root through a separate settings
value and injects that reader into Identity's `MigrationSecretInterpreter`.
The interpreter reads and caches the key when credential authentication is
actually needed; transitions without credentials do not require a key read.
Migration authentication and Comfy credential rebinding use the shared local
envelope implementation with that explicit key. They do not modify process
settings, select a default key, or contact KMS or an AI provider.

This applies to both embedded startup entrypoints. Existing local-v2 and legacy
dev-v1 reads keep their envelope contracts, including local-v2 scope validation.
Authentication failure still aborts the unpublished staging generation and
preserves the selected original database, secret and media. Runtime configuration
and worker startup remain after a successful canonical upgrade.

## World configuration and permanent import origins (2026-10-05)

Characters owns immutable import snapshots and proven origin references. Final
registration captures a creation baseline in its existing unit of work; formal
SQLite v28 / Alembic 0106 transition restores verified initial drafts or records a
distinct legacy transition baseline exactly once. Reads never create or recapture
an origin. Copies use that basis with new execution identities and initial OFF,
without copying credentials, memories, relationships, leases or activity history.

Character/account privacy erasure shares the existing deletion unit of work.
It removes the deleting actors' configuration and origin/draft references, then
erases an immutable import basis only after no live origin, draft or World
configuration refers to it. Retained independent Worlds keep their basis and
settings. This explicit privacy path does not permit ordinary snapshot edits.
Idle-slot accepted input is cleared with the deleted actor's private settings.

The Characters import service exposes its immutable input/output values from
`service/import_configuration.py`. Consumers import that narrow typed entry;
the existing `contracts.py` workflow exports retain their historical surface.
Field validation, public media validation and deterministic digests stay with
the import-service values, without storage or runtime dependencies.

Import-profile reads retain sanitized legacy HTTP loopback references to public
managed media and the shipped `/icon.svg` asset verbatim. External HTTP,
credentials, query/fragment data and non-public loopback routes remain rejected.
This read compatibility does not change managed-media ownership on profile writes,
make the server fetch the URL, or rewrite an immutable payload/digest.

WorldCharacters owns typed profile/persona/activity/model configuration, its
WorldCharacter revision and saved autonomous intent. Scoped management validates
local owner, World, active role, media ownership and expected revision. Public
profile/graph reads use the stored World profile; private settings are owner-only.
World edits preserve common Character values, import origins and other Worlds.

API dependency factories compose narrow services with Runtime SQLAlchemy, Media
and Routine adapters. Domain routers do not import concrete runtime workflows.
Routine keeps existing capacity, readiness, quota, lease and admission authority;
World ON/OFF controls only new automatic admission. Accepted Chat, SNS, Routine
and Media jobs keep a validated input snapshot and revision through retry/worker
execution. A later edit or OFF does not rewrite accepted input or another actor.

World Chat soft deletion uses the same admission fence as create, accept, retry
and model updates. Nonterminal requests reject deletion; terminal/idempotent
deletion affects only the thread and preserves separate evidence and World data.

The Runtime Chat graph adapter unwraps LangGraph's `NodeCancelledError` only
when its original cause is an `asyncio.CancelledError`. It propagates that
original signal to the response lifecycle owner, which settles cancellation,
fences and durable checkpoints. The compiled graph remains shared; request
sessions, observations and cancellation signals remain independent.

사용자 환경은 Identity의 `service/environment.py`가 소유하는 명시적 서비스 계약이다.
`contracts/environment.py`의 immutable snapshot을 SNS·Chat·기억 작업의 접수 시점에 저장하고,
각 작업은 재시도·재개에도 같은 snapshot을 사용한다. 환경 전환은 owner 인증·CAS·120초 lease와
단조 sequence로 보호한다. 환경 history는 인증된 보고 transaction에서 저장하며 quota owner는 그 UTC 보호 범위를 읽는다.
`routines/service/environment_schedule.py`는 슬롯 claim의 짧은 transaction에서 미래 idle 일정만 제한된 수로 조정한다. 범용 서비스에서 다른 도메인의 내부 저장 모델을 몰래 수정하지 않는다.

`core/calendar.py`는 UTC 순간과 현지 day/month 경계·DST gap/overlap을 계산한다. 기간별 소비 owner는
`AccountingPeriod`의 보호 구간 합집합에서 원 ID를 한 번 계수한다. 시간대 변경은 새로운 예산을
부여하지 않으며, legacy 집계와 미확정 예약은 보수적으로 보호한다. 24시간 보존·lease·cooldown은
현지 달력이 아닌 UTC 경과 시간 계약을 유지한다. World package의 timezone/hash는 바꾸지 않는다.

공통 Unicode scanner와 memory projection profile은 document/query/postcheck가 함께 사용한다.
원본의 수정·삭제는 after-commit fence로 재검증하며, 새 generation이 검증되기 전에는 preparing 상태다.
새 projection은 bounded page/cursor로 재개하고 기존 vector profile이나 원문을 재작성하지 않는다.

Angmoo 백엔드는 **업무별 폴더 안에서 HTTP, 업무 흐름, 저장, 입출력 형식을 나누는 FastAPI 애플리케이션**입니다. 게시물 문제는 `social`, 대화 문제는 `chat`, 기억 문제는 `memory`에서 시작합니다. 같은 업무 안에서는 `router`, `service`, `repository`, `models`, `schemas`처럼 역할을 드러내는 이름을 사용합니다.

이 문서는 기능을 추가하거나 버그를 수정할 때 코드의 위치와 연결 방식을 이해하기 위한 설명서입니다. 구조 전환의 PR·테스트·설치 결과는 [백엔드 전환 결과](../docs/architecture/refactor-backend-results.md)에 기록합니다. 이 문서에 구조가 설명돼 있다는 사실과 특정 배포판의 검증 완료 여부는 구분합니다.

[FastAPI Best Practices](https://github.com/zhanymkanov/fastapi-best-practices#project-structure)의 업무별 구성을 참고했습니다. 원문의 `src/auth`에 해당하는 Angmoo 경로는 `app/domains/identity`입니다. Angmoo의 로컬 실행과 AI 작업에 필요한 `runtime`, `integrations`, `credentials`도 각자의 책임을 가집니다.

## 1. 먼저 어디를 보면 되나요?

문제를 찾을 때는 **업무 → 역할 → 실제 호출자와 테스트** 순서로 따라갑니다.

| 관찰한 문제 | 시작할 위치 | 함께 확인할 내용 |
| --- | --- | --- |
| 다른 World의 게시물이 보임 | `domains/social/service/`, `repository/` | 현재 actor·World 권한, 정렬과 pagination |
| 채팅의 취소 후 늦은 답변이 저장됨 | `domains/chat/service/generation.py` | 요청 상태·lease·버전·결과 적용 transaction |
| 삭제한 기억이 검색 결과에 남음 | `domains/memory/service/`, `repository/` | 원본 상태, 검색 색인, 반환 직전 재검증 |
| 자율활동이 두 번 실행됨 | `domains/routines/service/`, `runtime/resident/` | tick identity, claim, 재시작과 재시도 |
| API의 필드나 HTTP 오류가 다름 | 해당 업무의 `schemas`와 `router` | 응답 모델·nullable·상태 코드·오류 변환 |
| 설치 앱에서만 DB를 열지 못함 | `runtime/persistence/`, `runtime/migrations/` | 실제 데이터 경로·업그레이드·bundle 자원 |
| AI 응답을 해석하지 못함 | `integrations/llm/`, `providers/gemini.py`, 해당 업무의 parser | provider 형식·허용 schema·timeout·호출 수 |

예를 들어 기억이 중복 저장된다면 화면에서 중복 행을 숨기기 전에 Memory의 원본 식별자와 job identity, 조건부 저장, transaction을 확인합니다. HTTP 요청과 worker가 같은 서비스로 들어가는지도 봅니다.

## 2. 프로젝트 구조

전체 배치에서는 업무와 실행 경계를 찾고, 도메인·외부 연동의 상세 예시에서는 파일별 책임을 찾습니다. 이 문서는 백엔드 설계의 기초이므로 **현재 사용하는 주요 경로와, 현재 사용하지 않아도 역할을 알아야 하는 기본 구성 예시를 함께 포함**합니다. `templates/`·`requirements/`처럼 선택 가능한 구성은 트리의 주석과 설명으로 구분합니다. 실제 파일·import 관계는 현재 코드와 구조 검사 결과로 확인합니다.

### 2.1 전체 구조와 파일 역할

```text
backend/
├── app/
│   ├── domains/                   # 업무별 코드·데이터·규칙의 소유자
│   │   ├── identity/              # 로그인·세션·owner·credential 정책
│   │   ├── characters/            # 캐릭터 정의·페르소나·Creator
│   │   ├── worlds/                # World 정의·membership·배너
│   │   ├── world_characters/      # World 참여·프로필·일과 생성과 승인
│   │   ├── device_home/           # Local World 목록·Home/Studio 진입
│   │   ├── world_packages/        # 패키지 계약·검사·export/import
│   │   ├── social/                # 게시물·댓글·Feed·Inbox
│   │   │   ├── router.py          # 이 업무의 HTTP 진입점
│   │   │   ├── dependencies.py    # 인증·Session·서비스 연결
│   │   │   ├── schemas/           # 요청·응답 형식
│   │   │   ├── models/            # 소유 table·relationship
│   │   │   ├── service/           # 업무 판단·처리 순서·저장 경계
│   │   │   ├── repository/        # 분리한 SQL 조회·저장
│   │   │   ├── contracts/         # 업무 값·결과·협력 객체의 타입
│   │   │   ├── policies/          # I/O 없는 업무 판단
│   │   │   ├── utils/             # 이 업무에서 쓰는 작은 변환
│   │   │   ├── constants.py       # 업무 상수
│   │   │   └── exceptions.py      # 업무 오류
│   │   ├── relationships/         # 관계 사건·후보·그래프 조회 정책
│   │   ├── routines/              # 자율활동 계획·슬롯·tick·활동 기록
│   │   ├── routine_posts/         # 자율 글쓰기 문맥·생성·provenance
│   │   ├── chat/                  # 대화·회상·응답 생성·streaming
│   │   ├── memory/                # 기억·원본 재검증·정리·회상
│   │   ├── runtime/               # 실행 상태의 의미·lease 규칙
│   │   ├── local_bot/             # Local Bot 인증·지원 동작
│   │   ├── character_lore/        # 참고 문서·청크·검색
│   │   ├── media/                 # 공유 미디어 값·검증 계약
│   │   ├── tree/                  # Tree 게시판
│   │   └── operations/            # 기존 운영 설정
│   ├── config.py                  # 공통 환경 설정
│   ├── models.py                  # 단일 ORM Base
│   ├── database.py                # engine·session 생성과 연결
│   ├── exceptions.py              # 공통 오류
│   ├── pagination.py              # 공유 cursor bytes 변환
│   ├── main.py                    # 앱·lifespan 생성과 서비스 연결
│   ├── api/                       # 공통 HTTP 연결·지원 route 조립
│   │   ├── v1/                   # 기존 URL 그룹·route 등록
│   │   └── schemas/              # 여러 업무를 합친 HTTP 응답
│   ├── runtime/                   # 실행·여러 업무의 협력·시작·종료
│   │   ├── persistence/
│   │   │   └── model_registration.py # 앱·migration에 필요한 모델 등록
│   │   ├── migrations/            # 설치 데이터의 embedded upgrade
│   │   ├── chat/
│   │   │   └── message_composition.py # Chat 서비스와 실제 협력 객체 연결
│   │   ├── memory/                # 기억 서비스·저장·worker 연결
│   │   ├── resident/              # 자율활동 작업의 실행 조립
│   │   ├── routines/              # 계획 서비스의 실제 참조 연결
│   │   ├── world_packages/        # 여러 업무의 export/import 연결
│   │   ├── graph_projection/      # 파생 관계 그래프의 실행 연결
│   │   ├── account_deletion.py    # 여러 업무의 삭제 작업 조립
│   │   └── ...                    # 나머지 실행도 실제 협력 업무별로 배치
│   ├── integrations/              # 외부 통신·미디어 변환·SDK 연결
│   │   ├── direct_llm.py          # 공유 LLM 호출·호출 추적
│   │   ├── provider_http.py       # provider HTTP 연결 도구
│   │   ├── bounded_http.py        # 제한을 적용하는 HTTP I/O
│   │   ├── google_identity.py     # Google identity 연동
│   │   ├── replicate_image.py     # 단일 파일로 구성한 이미지 연동
│   │   ├── pollinations_image.py
│   │   ├── llm/                   # LLM 작업별 adapter
│   │   │   ├── character_response_generator.py
│   │   │   ├── memory_selection.py
│   │   │   └── ...
│   │   ├── media/
│   │   │   ├── images.py          # 이미지 변환·입출력
│   │   │   └── files.py           # 미디어 파일 처리
│   │   └── ...                    # 연동 패키지로 나누는 예시는 §6.1
│   ├── providers/
│   │   ├── contracts.py           # 공유 생성·embedding 요청·결과·오류
│   │   ├── gemini.py              # 공유 Gemini adapter
│   │   ├── registry.py            # 실제 provider 선택
│   │   └── fake.py                # 결정적인 테스트용 provider
│   ├── credentials/               # 공유 credential 연결·지원 계약
│   │   ├── contracts.py
│   │   ├── resolver.py
│   │   └── service_images.py
│   ├── core/                      # 공통 보안·동시성·작은 기반 도구
│   │   ├── security.py
│   │   ├── redaction.py
│   │   ├── search_text.py
│   │   └── ...
│   └── contracts/                 # 여러 업무가 함께 사용하는 값의 계약
├── alembic/
│   ├── env.py
│   └── versions/                  # 역사적 revision·연결 그래프 보존
├── templates/                     # 구성 예시: 서버에서 렌더링하는 HTML 템플릿
│   └── index.html                 # 서버 HTML 화면의 템플릿 예시
├── requirements/                  # 구성 예시: 환경별 의존성 목록
│   ├── base.txt                   # 모든 환경의 공통 실행 의존성
│   ├── dev.txt                    # 공통 의존성 + 개발·테스트 도구
│   └── prod.txt                   # 공통 의존성 + 운영·배포용 의존성
├── tests/
│   ├── identity/
│   ├── characters/
│   ├── social/
│   ├── chat/
│   ├── memory/
│   ├── runtime/
│   ├── integrations/
│   ├── migrations/
│   └── conftest.py
├── ARCHITECTURE.md
├── pyproject.toml
├── uv.lock
├── .python-version
├── .env.example
├── logging.ini
└── alembic.ini

저장소 root/
├── .gitignore
├── scripts/ci/
├── security/
└── .github/workflows/
```

`social`은 현재 업무 내부의 역할별 구성을 보여 주는 대표 예입니다. 다른 업무도 같은 책임 기준을 사용하되 파일·패키지로 나눈 깊이는 다릅니다. 현재 외부 연동에는 `replicate_image.py`처럼 파일 하나로 구성된 구현도 있습니다. 아래의 확장 예시를 맞추려고 기존 파일을 일괄 이동하지 않습니다.

### 2.2 도메인 내부에 둘 수 있는 파일

다음은 **역할을 설명하는 구성 예시**입니다. `<domain>`에는 `characters`, `social`, `chat` 같은 실제 업무 이름이 들어갑니다. 도메인 폴더 바로 아래에 `utils.py`, `config.py`, `client.py`를 두는 것도 정상적인 배치입니다.

```text
app/domains/<domain>/
├── __init__.py          # 패키지 구성
├── router.py            # HTTP 경로·입출력·오류 변환
├── schemas.py           # 요청·응답 형식과 값 검증
├── dependencies.py      # 인증된 actor·요청 Session·서비스 연결
├── service.py           # 업무 판단·실행 순서·저장 경계
├── repository.py        # 필요할 때 분리하는 소유 데이터의 SQL
├── models.py            # 이 업무의 ORM table·relationship
├── client.py            # 이 업무의 외부 요청 문맥·응답 해석
├── contracts.py         # 업무 값·명령·결과·필요한 협력 객체의 타입
├── policies.py          # DB·HTTP 없이 계산하는 업무 판단
├── config.py            # 이 업무에만 필요한 설정
├── constants.py         # 업무 상수·안정적인 코드 값
├── exceptions.py        # 이 업무의 의미 있는 오류
└── utils.py             # 업무 판단을 하지 않는 작은 변환·보조 함수
```

이 파일들은 **허용되는 역할 예시이며 필수 생성 목록이 아닙니다.** HTTP로 노출하지 않는 기능에는 router가 없을 수 있고, 간단한 저장은 service가 직접 처리할 수 있습니다. `repository`, `client`, `contracts`, `policies`, `config`, `utils`도 실제 분리할 책임이 있을 때 만듭니다. 여러 파일로 나누는 기준은 §3.1을 따릅니다.

`__init__.py`에는 패키지 구성에 필요한 코드만 둡니다. import만으로 DB 연결·비밀 읽기·외부 요청·worker 시작이 발생하지 않게 합니다. 내부 모듈 전체를 다시 export하는 집합 파일로 만들 필요는 없습니다.

### 2.3 템플릿·환경별 의존성·개발 설정

`templates/`와 `requirements/`도 백엔드의 기본 구성을 이해하기 위한 구조 예시에 포함합니다. 현재 Angmoo에서 해당 방식을 사용하지 않더라도, 어떤 책임이 필요할 때 선택하는 위치인지 문서에서 확인할 수 있어야 합니다.

| 경로 | 역할과 사용할 때의 기준 |
| --- | --- |
| `templates/index.html` | 서버에서 HTML을 렌더링할 때 사용하는 템플릿 예시입니다. `index.html`은 예시 이름이며 실제 화면과 목적에 맞게 나눕니다. |
| `requirements/base.txt` | 개발·운영 등 여러 환경이 공통으로 사용하는 실행 의존성을 모읍니다. |
| `requirements/dev.txt` | 공통 의존성에 테스트·lint·개발 지원 도구를 더한 개발 환경 목록입니다. |
| `requirements/prod.txt` | 공통 의존성에 운영 실행·배포에 필요한 패키지를 더한 운영 환경 목록입니다. |

requirements 파일을 사용하는 구성에서는 `dev.txt`와 `prod.txt`가 `-r base.txt`로 공통 목록을 포함할 수 있습니다. 현재 Angmoo의 의존성 관리 원본은 **`pyproject.toml`과 `uv.lock`**입니다. requirements 방식이 실제로 필요해지면 현재 원본에서 생성할지, 관리 방식을 전환할지 정하고 같은 의존성 버전을 여러 곳에서 따로 수동 관리하지 않습니다. 구조 예시에 포함하는 것만으로 현재 설치·빌드 명령이나 의존성 관리 방식을 바꾸지는 않습니다.

템플릿이 필요한 서버 렌더링 기능을 추가할 때는 해당 HTTP 경계에서 연결합니다. Next.js가 소유한 화면을 이 예시 때문에 백엔드 템플릿으로 옮기지는 않습니다. 개발용 `.env`는 Git과 제품 배포에서 제외하며, 공개 가능한 설정 예시는 `.env.example`에 두고 저장소 루트의 `.gitignore`를 사용합니다.

## 3. 도메인 안의 역할

| 이름 | 무엇을 담나요? | 무엇을 결정하지 않나요? |
| --- | --- | --- |
| `router` | URL·HTTP method·입출력·HTTP 오류·streaming transport | worker에도 적용돼야 하는 업무 권한·상태 전이 |
| `schemas` | Pydantic 요청·응답의 필드와 값 검증 | DB에 실제로 존재하는 대상의 권한 |
| `dependencies` | 인증·요청 Session·앱에 구성된 서비스 연결 | 업무 처리 순서 전체 |
| `service` | 업무 판단·권한·실행 순서·상태 전이·저장 경계 | HTTP transport나 앱 프로세스 시작 |
| `repository` | 해당 업무의 SQL 조회·저장·조건부 갱신 | 다른 업무의 정책을 우회하는 임의 변경 |
| `client` | 해당 업무의 외부 서비스 연결·요청 문맥·응답 변환 | 공개 여부·권한·저장 자격 판단 |
| `models` | 해당 업무의 table·column·relationship | API에 노출할 필드 선택 |
| `exceptions` | 안정적인 업무 오류 타입·의미 | provider 오류 원문을 그대로 공개하는 처리 |
| `constants` / `config` | 해당 업무의 상수·설정 | 다른 업무 전체의 설정 집합 |
| `policies` | 입력된 값에 대한 순수 업무 판단 | DB·파일·네트워크 I/O |
| `contracts` | 업무 값·명령·결과·필요한 협력 객체의 타입 | 모든 서비스에 강제하는 추상 계층 |
| `utils` | 업무 판단 없는 작은 변환·보조 함수 | 권한·공개 여부·저장 자격 |

기본은 역할별 파일입니다. `repository`, `policies`, `contracts`는 실제 분리할 책임이 있을 때 사용합니다. 간단한 저장은 service에서 SQLAlchemy를 직접 사용할 수 있고, 복잡한 조회나 여러 서비스가 함께 쓰는 SQL은 repository로 분리합니다. 한 함수를 전달하기 위해 서비스·유스케이스·인터페이스를 각각 추가하지 않습니다.

Chat과 Memory처럼 큰 업무는 역할별로 나눕니다. 예를 들어 Chat의 `service/threads.py`, `settings.py`, `messages.py`, `generation.py`, `evidence.py`는 서로 다른 사용자 동작을 소유합니다. `service/` 안에 다시 `application/domain/ports/infrastructure` 전체 계층을 만드는 규칙은 없습니다.

### 3.1 파일 하나에서 역할별 패키지로 나누기

서로 다른 변경 이유와 호출자가 생기면 파일을 같은 역할의 패키지로 나눌 수 있습니다. 예를 들어 생성·승인·조회가 각각 커진 업무는 다음처럼 구성할 수 있습니다. 아래 이름은 분해 방식의 예시이며 특정 도메인의 현재 파일 목록은 아닙니다.

```text
app/domains/<domain>/
├── router.py
├── dependencies.py
├── models.py                   # 작으면 다른 역할과 무관하게 파일 하나 유지
├── service/
│   ├── __init__.py
│   ├── creation.py             # 생성 흐름
│   ├── approval.py             # 승인·상태 전이
│   └── queries.py              # 업무 조회
├── schemas/
│   ├── __init__.py
│   ├── creation.py             # 생성 요청·응답
│   └── approval.py             # 승인 요청·응답
├── repository/                 # SQL을 따로 모을 필요가 있을 때
│   ├── __init__.py
│   ├── queries.py
│   └── writes.py
├── contracts.py
├── policies.py
├── exceptions.py
└── utils/                      # 서로 다른 보조 기능을 나눌 필요가 있을 때
    ├── __init__.py
    ├── text.py
    └── time_format.py
```

- `service.py`를 `service/`로 나눠도 그 업무의 권한·상태 전이·저장 책임은 그대로입니다. 단순히 파일이 길다는 이유로 같은 동작을 여러 전달 계층으로 나누지 않습니다.
- 역할마다 깊이를 독립적으로 결정합니다. `service/`를 사용하면서 `models.py`, `schemas.py`, `client.py`를 유지해도 됩니다. HTTP route나 모델이 커졌을 때만 `router/`, `models/`도 나눕니다.
- **같은 위치에 `service.py`와 `service/`를 동시에 두지 않습니다.** `schemas`, `models`, `client`, `utils` 등 다른 역할에도 같은 기준을 적용합니다.
- 파일 이동 시 실제 호출자의 import, 지원 함수·타입, 테스트와 구조 검사 계약을 함께 갱신합니다. 파일 분리만으로 기존 함수의 Session·commit·오류·재시도 의미를 바꾸지 않습니다.

현재 [Chat 서비스](app/domains/chat/service/)는 사용자 동작별로 나뉘고 [Chat schemas](app/domains/chat/schemas.py)는 파일 하나입니다. [Social schemas](app/domains/social/schemas/)와 [Social repository](app/domains/social/repository/)는 패키지입니다. 서로 다른 형태가 함께 있는 것은 정상이며 모든 업무의 깊이를 맞출 필요는 없습니다.

### 3.2 utils·설정·타입의 소유 범위

`domains/<domain>/utils.py`는 해당 업무의 보조 함수를 두는 위치입니다. 처음부터 모든 보조 함수를 `app/core`나 전역 `utils`로 올리지 않습니다. 여러 업무에서 같은 의미로 사용하는 것이 확인되면 소유권과 의존 방향을 검토해 공통 도구로 분리합니다.

| 작성할 내용 | 적절한 위치와 이유 |
| --- | --- |
| 이 업무만 쓰는 문자열 공백 정리·표시용 값 변환 | 해당 도메인의 `utils.py` 또는 `utils/text.py` |
| 현재 actor가 후보를 승인할 수 있는지 판단 | 해당 도메인의 `service`; 입력된 값만으로 계산하는 부분은 `policies`로 분리 가능 |
| 페르소나가 저장 가능한 길이인지, 패키지와 호환되는지 판단 | 각 규칙을 소유한 도메인의 `schemas`·`service`·검증 함수; `utils`에 저장 자격을 숨기지 않음 |
| 해당 기능의 고정된 상태 코드·상수 | 해당 도메인의 `constants.py` |
| 실행 환경마다 달라지는 해당 기능 설정 | 해당 도메인의 `config.py`; 공통 설정 진입점에서 검증한 필요한 값을 연결 |
| HTTP 요청·응답의 필드 | 해당 도메인의 `schemas.py` 또는 `schemas/` |
| worker나 다른 업무에 제공하는 명령·결과·협력 객체 타입 | 실제 소유 모듈 또는 필요할 때 분리한 `contracts`; 별도 타입 복제가 필요하지 않으면 기존 지원 타입 사용 |

`utils`라는 이름은 DB·네트워크·업무 판단을 어디든 넣어도 된다는 뜻이 아닙니다. 외부 전송의 변환 도구는 해당 integration이, 업무의 허용 조건은 해당 도메인이 소유합니다. 같은 `schemas.py`라는 이름도 위치에 따라 의미가 달라지며 외부 연동의 schema와 HTTP 공개 응답을 그대로 공유하지 않습니다.

`config.py`가 있다는 이유로 도메인마다 환경 변수를 다시 읽거나 `BaseSettings` 인스턴스를 따로 만들 필요는 없습니다. 공통 설정 로딩은 `app/config.py`, 실제 객체와 자원의 연결은 `main`·`runtime`이 담당합니다. `constants.py`에 사용자별 설정·credential·현재 DB 상태를 넣지 않습니다.

## 4. 업무별로 찾아보기

| 도메인 | 책임 |
| --- | --- |
| `identity` | 로그인·세션·Local owner bootstrap·사용자 설정·credential 정책 |
| `characters` | 캐릭터 정의·초안·Creator·프로필·이미지 설정 |
| `worlds` | World 정의·생성·배너·membership·정의 version·readiness |
| `world_characters` | World 참여·owner control·설정 생성과 승인·Studio lifecycle |
| `device_home` | Local World 목록·Home/Studio 진입·실행 가능 표면 |
| `world_packages` | World 패키지 계약·export/import·검사·lineage·원자 적용 |
| `social` | 게시물·댓글·반응·Feed·Inbox·수동 작성·공개 활동·이미지 요청 |
| `relationships` | 관계 사건·포인트·후보·관계 그래프 조회와 적용 정책 |
| `routines` | 자율활동 설정·계획·슬롯·tick·행동 허용·결과와 활동 로그 |
| `routine_posts` | 자율 글쓰기 입력·문맥·생성 결과·중복과 provenance |
| `chat` | thread·message·검색 계획·근거·응답 생성·취소·streaming |
| `memory` | 기억 후보·항목·회상·원본 재검증·AI 배치·예약·Daypart |
| `runtime` | 실행 상태·진단·lease 판단에 필요한 업무 계약과 서비스 |
| `local_bot` | 로컬 Bot 인증·owner key·지원 HTTP 동작 |
| `character_lore` | 캐릭터 참고 문서·파싱·청크·임베딩·검색 |
| `media` | 여러 업무가 공유하는 미디어 값·오류·검증 계약 |
| `tree` | Tree 게시판의 업무 동작 |
| `operations` | 기존 운영 설정의 의미·조회·저장 |

`domains/runtime`은 실행 상태의 의미와 lease 규칙을 담습니다. 앱을 띄우고 worker를 시작하는 상위 `app/runtime`과 책임이 다릅니다. `Character`는 캐릭터 자체이고 `WorldCharacter`는 특정 World의 참여입니다. 캐릭터가 같아도 다른 World의 대화·기억·관계를 합치지 않습니다.

## 5. 요청과 worker가 서비스를 사용하는 방식

```text
HTTP 요청 → router → service → 같은 업무의 DB 접근 / repository
                         └─→ 필요한 협력 객체·외부 client

runtime의 예약·작업 실행 → 같은 service

main → runtime 조립 → 서비스 생성·연결 → app.state → HTTP dependency
```

Router는 요청을 해석하고 응답으로 바꿉니다. Service는 actor와 대상 scope를 받아 무엇을 허용하고 어떤 변경을 저장할지 결정합니다. 검증을 router에만 넣으면 worker가 같은 규칙을 빠뜨릴 수 있습니다. worker에 같은 정책을 복사하면 두 진입점의 동작이 달라질 수 있습니다.

실제 예는 [Chat 서비스 조립](app/runtime/chat/message_composition.py)과 [Chat dependency](app/domains/chat/dependencies.py)입니다. 조립 모듈이 실제 Thread·Message·Generation 서비스를 만들고, dependency가 앱에 연결된 객체를 요청에 제공합니다. Runtime이 업무 서비스를 역으로 가져오는 방향이며, 서비스가 `app.main`을 import해 실행 객체를 찾지 않습니다.

Memory 후보 저장은 [items service](app/domains/memory/service/items.py)에서 시작합니다. scope·설정·원본의 성공 여부와 공개 범위를 확인하고, 같은 원본의 중복 후보를 판정한 뒤 저장합니다. worker가 돌아간다는 사실이나 LLM의 성공 응답만으로 유효한 기억이 되지는 않습니다.

## 6. 다른 업무와 연결하기

필요한 함수와 타입은 **실제 소유 역할에서 명시적으로 import**합니다.

```python
from app.domains.worlds.service import definition as world_definition
from app.domains.identity.contracts import CredentialMaterial, CredentialPurpose
```

지원되는 호출은 입력·출력·오류와 transaction 참여 방식을 설명합니다. 파일이 `service`라는 이유만으로 모든 내부 helper가 외부 계약이 되는 것은 아닙니다. 다른 도메인의 model이나 repository를 가져와 그 업무의 상태 전이·권한·저장 규칙을 우회하지 않습니다.

```text
main / runtime 조립 → 도메인의 지원 service·schema·contract
도메인 service      → 자기 업무 내부 + 필요한 다른 업무의 지원 기능
도메인 model        → app.models.Base
공통 Base·오류·도구  → 도메인에 의존하지 않음
```

여러 업무의 데이터를 함께 읽거나 원자적으로 지워야 하면 구체적인 협력을 `runtime/<업무>/`에 둡니다. 예를 들어 [계정 삭제](app/runtime/account_deletion.py)는 Identity·Character·World·Memory와 비공개 미디어 정리를 같은 작업으로 조립합니다. Identity 서비스가 삭제 요청을 허용하는지 판단하고, 조립은 같은 Session과 기존 commit/rollback 순서를 유지합니다.

Runtime의 다중 업무 조회는 읽는 범위·권한 재검증·Session 계약이 있는 구체적인 조회입니다. 모든 DB 접근을 runtime으로 옮기거나 임의 cross-domain SQL을 허용하는 규칙이 아닙니다. 순환 의존이 생기면 업무 소유권과 협력 방향을 먼저 확인합니다.

외부 provider, clock, 다른 업무의 제한된 조회처럼 실제 교체 경계가 있으면 작은 Protocol이나 callable을 전달할 수 있습니다. 모든 repository와 서비스에 별도 추상 인터페이스를 요구하지 않습니다. 새 코드에서 집합 `public.py`를 거쳐야 한다는 규칙도 없습니다.

공통 코드도 실제 책임으로 구분합니다. 활동 가능 시간은 [`routines/policies/active_hours.py`](app/domains/routines/policies/active_hours.py), 게시물 검색 문서의 필드·길이 규칙은 [`social/service/search_documents.py`](app/domains/social/service/search_documents.py)가 소유합니다. `core/search_text.py`에는 여러 업무가 쓰는 정규화·LIKE 변환만 남습니다. `core/public_media.py`는 공통 HTTP 미디어 mount, `core/image_generation.py`는 공유 이미지 모델·provider 설정을 연결합니다.

`integrations/llm`은 외부 AI 통신·SDK 연결을, 도메인의 `client`는 업무별 외부 요청과 응답 해석을, `providers/gemini.py`는 공유 Gemini 생성·embedding adapter를 제공합니다. `providers/registry.py`가 선택하는 실제 adapter와 업무별 parser를 함께 확인합니다. SDK 호출이 모두 한 폴더에 있다는 의미는 아닙니다.

`api/v1`에는 기존 URL 그룹·등록 순서를 유지하는 조립과 공통 HTTP 연결이 남습니다. `api/schemas/first_greeting.py`는 실행 결과와 Social 게시물을 합친 HTTP 응답 형식입니다. 이 조립 파일들에 업무 권한이나 SQL을 다시 모으지 않습니다. 지원되는 옛 route import가 필요한 경우에도 실제 HTTP·업무 구현은 한 소유 경로에서 제공합니다.

### 6.1 외부 연동 패키지의 세부 구조

현재 `integrations/replicate_image.py`처럼 외부 연동을 파일 하나에 구성하는 형태도 지원합니다. 요청·응답 형식, 설정, 오류와 변환의 책임을 나눌 필요가 생기면 **같은 연동 대상의 폴더 안에서** 다음처럼 구성합니다.

```text
app/integrations/<external_service>/
├── __init__.py          # 패키지 구성; import 시 외부 연결을 시작하지 않음
├── client.py            # HTTP·SDK 요청, 응답 읽기, timeout·실패 변환
├── schemas.py           # 해당 외부 API의 요청·응답·전송 데이터 형식
├── config.py            # endpoint·연결 제한 등 연동별 설정
├── constants.py         # 외부 상태 코드·지원 형식·고정된 전송 상수
├── exceptions.py        # timeout·인증 실패·잘못된 응답 등 연동 오류
└── utils.py             # 전송 인코딩·필드 변환 등 작은 보조 함수

tests/integrations/<external_service>/
├── test_client.py       # 성공·실패·timeout·재시도·호출 수
└── test_schemas.py      # 외부 응답 형식과 누락·잘못된 값
```

`<external_service>`는 실제 폴더명이 아니라 연동 대상 이름을 넣는 자리입니다. **위 파일과 테스트는 분리 가능한 책임의 예시**이며 새 연동마다 전부 생성하지 않습니다. 테스트도 작으면 기존 `tests/integrations/test_direct_llm.py`처럼 파일 하나로 둘 수 있습니다. `integrations`에는 외부 서비스뿐 아니라 미디어 변환·파일 처리·그래프 SDK 같은 기술 연결도 포함됩니다.

| 연동 내부 파일 | 담당할 내용 | 도메인에 남길 내용 |
| --- | --- | --- |
| `client.py` | 요청 직렬화·전송·응답 읽기, 허용된 timeout·재시도 실행, SDK 실패 변환 | 누가 요청할 수 있는지, 생성·공개·승인·저장 자격 |
| `schemas.py` | 외부 필드명·nullable·상태 값·payload 형태 | Angmoo HTTP 응답의 공개 필드, 캐릭터·World의 상태 전이 |
| `config.py` | 앱에서 전달받은 endpoint·timeout·연결 설정 | 사용자의 동의·업무별 호출 예산·credential 선택 정책 |
| `constants.py` | 해당 연동의 고정된 API 값·오류 코드 대응 | 실행 중 달라지는 권한·사용자 설정 |
| `exceptions.py` | 실패 종류·재시도 가능 여부 등 호출자가 처리할 정보 | HTTP 상태 코드 선택, 실패한 결과를 저장할지 판단 |
| `utils.py` | 인코딩·파싱 보조·외부 필드 변환 | 권한·공개 여부·업무 검증을 우회하는 판단 |

기본 예시는 `client.py`입니다. 여러 클라이언트를 한 모듈에 묶는 책임이 있으면 `clients.py`, 연결 종류가 충분히 커지면 `client/`처럼 나눌 수도 있습니다. 기존 연동의 명명과 호출자를 확인하고, 같은 책임을 하는 파일을 이름만 달리해 중복 생성하지 않습니다.

외부 API의 schema와 도메인의 schema는 같은 이름이어도 다른 계약입니다. 외부의 필드명·SDK 객체·오류 payload를 도메인 client나 adapter에서 업무 값으로 바꾸고, service는 그 결과의 사용·저장을 판단합니다. 외부 응답이 형식 검증을 통과했다는 사실만으로 업무 승인이 끝난 것은 아닙니다.

### 6.2 도메인 client·integration·provider·runtime의 연결

같은 외부 연결에 관여해도 다음 책임은 구분합니다. 모든 호출이 아래 위치를 차례로 전부 통과해야 한다는 규칙은 아닙니다. 실제 재사용·교체 경계가 있을 때 나눕니다.

| 위치 | 소유하는 책임 | 현재 참고 위치 |
| --- | --- | --- |
| 도메인 `service` | 사용자 동의·권한·업무 예산·처리 순서·결과 적용 | [World 활동 준비 service](app/domains/world_characters/service/autonomous_setup.py) |
| 도메인 `client` | 해당 업무의 요청 문맥·응답 schema 선택·외부 응답의 업무 값 변환 | [World 캐릭터 client](app/domains/world_characters/client.py) |
| `integrations` | 외부 HTTP·SDK·파일 I/O, 호출 추적과 기술적인 응답·실패 변환 | [공유 LLM 호출](app/integrations/direct_llm.py), [Replicate 이미지 연동](app/integrations/replicate_image.py) |
| `providers` | 공유 생성·embedding 계약, 이를 구현한 adapter와 선택 | [provider 계약](app/providers/contracts.py), [Gemini adapter](app/providers/gemini.py), [registry](app/providers/registry.py) |
| Identity와 `credentials` 연결 | credential 사용 목적·권한·해석과 기존 공유 연결 | [Identity credential resolution](app/domains/identity/service/credential_resolution.py), [credential 연결](app/credentials/resolver.py) |
| `main`·`runtime` | 설정·자원 수명과 실제 서비스·adapter 구성 | [Chat 조립](app/runtime/chat/message_composition.py) |

현재 `integrations/llm/`에는 도메인의 요청·결과 계약을 구현하는 작업별 adapter도 있습니다. 이런 adapter가 지원되는 도메인 타입을 사용하는 것과 도메인의 승인·저장 service를 역호출하는 것은 다릅니다. 기존 typed adapter를 무조건 이동하거나 `providers/gemini.py`와 같은 SDK 코드를 새 연동 폴더에 복제하지 않습니다. 파일 배치 변경이 필요하면 실제 호출 관계와 지원 계약을 함께 정리합니다.

새 연결을 추가할 때는 먼저 기존 `direct_llm`, `provider_http`, `bounded_http`, provider 계약을 재사용할 수 있는지 확인합니다. 외부 SDK의 숨은 재시도·fallback도 실제 호출 수와 timeout 범위에 포함하며, adapter가 업무에서 허용하지 않은 추가 호출을 만들지 않게 합니다. 공유 credential 연결을 사용하고 integration이 임의로 사용자 키를 고르거나 저장하지 않습니다.

예를 들어 World 프로필 생성에서 **요청 동의와 후보 승인**은 `world_characters/service`, **생성 입력 구성과 결과 해석**은 업무 client, **모델 요청과 외부 오류 처리**는 기존 LLM 연결이 담당합니다. 후보 승인 규칙을 HTTP client에 넣거나, 전송 형식이 바뀌었다는 이유로 승인된 DB 상태를 integration에서 변경하지 않습니다.

## 7. 모델·Session·transaction

[`app/models.py`](app/models.py)는 하나의 ORM `Base`를 소유합니다. 개별 table은 각 도메인의 models가 소유하고, [`runtime/persistence/model_registration.py`](app/runtime/persistence/model_registration.py)가 앱 시작과 migration에 필요한 모델을 등록합니다. 모델 등록은 모델의 업무 소유권을 바꾸지 않습니다.

[`app/database.py`](app/database.py)는 engine과 동기 SQLAlchemy `Session`의 생성·연결을 담당합니다. 모듈을 import하는 것만으로 engine을 만들지 않으며, 공식 Local 실행은 명시적인 runtime 구성과 데이터 경로를 전달합니다. 테스트의 `model_fixture_support.py`는 테스트에 필요한 ORM 참조를 모으는 도구이며 제품 코드의 전역 model registry가 아닙니다.

한 업무 변경에 참여하는 함수는 같은 Session을 전달받습니다. Repository를 새로 만들었다는 이유로 안에서 새 Session을 열거나 commit을 추가하지 않습니다. 원래 호출자가 commit하는 함수, flush만 하는 함수, 독립적인 활동 로그 저장은 서로 다른 계약입니다.

예를 들어 World Package import는 여러 모델과 lineage를 함께 반영합니다. World/WorldCharacter seed가 각자 commit하면 중간 실패 시 부분 데이터가 남으므로 Package가 원자 적용을 소유합니다. 반면 기존 Daypart 요약의 그룹별 저장은 실패한 그룹을 rollback하고 다음 그룹을 계속하는 계약을 유지합니다.

Session은 병렬 작업이 함께 쓰는 전역 객체가 아닙니다. 요청이 끝난 Session을 background 작업에 재사용하지 않습니다. 외부 AI 응답을 기다리는 동안 쓰기 transaction을 계속 열어 두지 않고, 결과 적용 시 현재 권한·version·lease를 다시 확인합니다.

## 8. HTTP·검증·비동기 처리

Pydantic은 입력과 응답의 형태를 검증합니다. owner·World·대상의 현재 상태는 service가 확인합니다. UI의 비활성 버튼과 클라이언트가 전달한 ID는 권한 증거가 아닙니다. 인증·cookie·CSRF 같은 HTTP 연결은 dependency와 공통 API 모듈이 담당합니다.

ORM과 응답 schema는 역할이 다릅니다. 암호문·credential·내부 상태를 그대로 직렬화하지 않으며 기존 응답 필드·시간 형식·nullable·오류 body를 유지합니다. Pydantic 모델 반환과 FastAPI `response_model`을 함께 사용할 수 있습니다.

업무 오류를 HTTP 상태로 변환하는 처리는 router 또는 공통 HTTP 경계에서 합니다. 같은 공통 오류도 업무 계약에 따라 다른 HTTP 응답이 될 수 있습니다. 공통 cursor 도구는 bytes 변환을 제공하고, 암호화·World scope·정렬·기본값은 각 업무가 소유합니다.

비동기 I/O는 `await`로 호출합니다. `async def` 안에서 동기 helper를 호출한다고 자동으로 thread pool에서 실행되는 것은 아닙니다. DB·파일·SDK의 실제 실행 경계를 확인합니다. 구조 변경에 동기 Session의 `AsyncSession` 전환이나 라이브러리 업그레이드를 함께 넣지 않습니다.

## 9. 원본 데이터·검색·AI

SQLite가 원본 데이터와 관리 상태를 저장합니다. FTS5와 LadybugDB는 검색·관계 탐색을 위한 파생 데이터입니다. 검색 hit만으로 현재 읽기 권한이나 삭제 여부를 결정하지 않고 원본의 World·관찰 범위·공개 상태를 다시 확인합니다.

LLM은 허용된 문맥을 해석하고 계획·요약·캐릭터 응답을 만듭니다. 코드가 실제 ID·권한·허용 연산·저장 자격·호출 상한을 결정합니다. LLM이 만든 SQL이나 Cypher를 그대로 실행하지 않고 검증한 계획을 허용된 executor로 수행합니다.

반복 작업은 job identity·claim·lease·version으로 중복 실행과 늦은 결과를 제어합니다. Memory 배치의 동의·호출 예산·재시도·종료 저장을 단순한 HTTP background task로 대체하지 않습니다. 이미 취소되거나 종료된 작업이 응답을 늦게 받았을 때 다시 적용되지 않아야 합니다.

Streaming에는 허용된 응답 event만 전달합니다. 내부 planner 출력·reasoning·provider 오류 원문을 공개하지 않고, 실패한 partial 응답을 성공한 원본이나 후속 기억 근거로 저장하지 않습니다. SDK의 숨은 재시도와 fallback도 실제 provider 호출 수에 포함됩니다.

## 10. 앱 생성·설치·마이그레이션

앱과 lifespan의 실제 생성 구현은 [`app/main.py`](app/main.py)의 `create_app`과 `create_lifespan`에 있습니다. `app`은 기존 full profile이고, `public_app`은 Local readiness를 제공하는 public profile입니다. `create_public_app`은 동일 factory에 public profile을 지정하는 연결입니다. 두 profile의 기존 기본값과 health 계약을 보존하며 별도 앱 생성 구현을 복제하지 않습니다.

개발 ASGI의 Local 경로는 `app.main:public_app`이고 공식 sidecar·contributor 실행은 명시적인 RuntimeConfig를 사용하는 `create_public_app`에 연결합니다. 옛 `public_main.py`는 전환을 위한 임시 호환 경로였으며 최종 구조의 진입점이 아닙니다. 파일 이름을 바꾸면서 기본 `create_app()`을 호출하면 profile이 달라질 수 있으므로 지원 export를 확인합니다.

Docker 브라우저 실행과 Windows 설치 앱은 같은 업무 코드를 사용하지만 데이터 경로와 lifecycle이 다릅니다. 설치 앱은 Tauri와 bundled sidecar를 사용합니다. 한 실행이 다른 실행의 DB를 초기화하거나 프로세스를 종료하지 않게 runtime 소유권을 유지합니다.

[`logging.ini`](logging.ini)와 [`runtime/logging_config.py`](app/runtime/logging_config.py)는 앱의 로그 구성을 연결합니다. 반복 factory 호출로 handler를 중복 설치하거나 기존 handler를 닫지 않습니다. sidecar의 JSON stdout·content-free fatal stderr·endpoint·종료 handshake는 서버 access log와 다른 실행 계약입니다. Docker와 bundle에 실제 설정 자원이 포함돼야 합니다.

Alembic은 [`alembic/`](alembic/)과 [`alembic.ini`](alembic.ini)를 사용합니다. `env.py`는 같은 Base의 등록된 metadata를 참조합니다. 역사 revision의 본문·ID·연결 그래프는 보존합니다. 별도로 `runtime/migrations`의 embedded SQLite upgrade가 설치 데이터의 버전을 올립니다. ORM 파일 이동만을 이유로 table·constraint·schema version을 변경하지 않습니다.

SQLite v29는 개발 watch 중 먼저 적용된 v28의 복구를 소유합니다. `sqlite_versions/registry.py`는 당시 generation marker의 정확한 manifest SHA와 동결된 초기 v28 계약을 연결하며, 원본의 schema 지문·revision·table inventory·무결성·외래키를 모두 검증합니다. 최종 v28과 v1–v27 manifest는 변경하지 않습니다. `world_configuration_v29.py`는 미공개 staging 복사본에서 nullable 실행 입력 컬럼 2개와 draft origin의 `ON DELETE CASCADE`만 보완합니다. 이미 저장된 World 설정·불변 가져오기 기준·접수 입력·lease·이력을 재생성하지 않습니다. 최종 v28도 같은 검증·승격 경로로 v29가 되며, 다른 schema drift는 거부합니다. Alembic 정의와 ORM의 최종 구조가 같으므로 source revision은 `20261005_0106`으로 유지하고 embedded 버전만 올립니다.

과거 migration이 import하는 몇몇 옛 model/schema helper 경로와 지원 Hosted 확장이 사용하는 최소 alias는 명시적인 호환 계약입니다. 실제 구현은 소유 역할 한곳에 있고 같은 객체를 제공합니다. 새 제품 코드가 이 경로를 사용하지 않습니다. 임시 업무 집합이나 사용자가 없는 전달 서비스를 이런 역사적 호환과 혼동하지 않습니다.

## 11. 테스트와 구조 검사

기능 테스트는 업무 가까이에 둡니다. `tests/social`, `tests/chat`, `tests/memory`는 실제 업무 회귀를, `tests/runtime`과 `tests/integrations`는 실행 조립과 통신 경계를 검증합니다. 여러 업무가 사용하는 fixture는 명시적인 공통 지원 파일 또는 소유 테스트 패키지에서 가져옵니다. `conftest.py`의 수집 범위와 네트워크 차단은 그대로 유지합니다.

검증은 사용자가 관찰하는 결과와 저장·권한·실패 경계를 확인합니다. Fake provider로 성공·오류·timeout·호출 횟수를 고정하고, transaction과 업그레이드는 격리된 SQLite 데이터로 확인합니다. 파일 이름만 비교하는 테스트가 기능 회귀를 대체하지 않습니다.

아래 명령은 저장소 루트에서 실행합니다. 환경 준비는 [기여 가이드](../CONTRIBUTING.ko.md)를 따릅니다.

```powershell
uv run --project backend python scripts/ci/generate_architecture_inventory.py --check
uv run --project backend python scripts/ci/check_architecture_boundaries.py
uv run --project backend python scripts/ci/check_refactor_preservation.py --contracts --nodes
uv run --directory backend python -m pytest -q tests/chat
uv run --directory backend python -m pytest -q tests
```

Import inventory는 현재 파일과 의존 관계의 사실이고 import policy는 허용 규칙입니다. Inventory를 다시 생성했다고 새 의존이 승인되는 것은 아닙니다. 다른 도메인의 저장 우회, 순환 의존, 옛 계층의 재도입을 검사하고, 파일 이동으로 테스트가 덜 수집돼 통과하지 않도록 원래 source·test node·API·ORM 계약을 대조합니다.

불변 기준 자료는 새 코드로 덮어쓰지 않습니다. 옛 경로의 임시 호환을 제거할 때는 원래 호환이 제공한 실제 객체와 현재 소유자를 확인하고, 기능 단언을 현재 경로에서 유지합니다. 최종 설치 후보는 새 bundle에서 시작·업그레이드·재시작·실패 복원을 검증합니다. 단위 테스트 통과와 설치 검증·CI·post-merge 결과는 각각의 증거입니다.

## 12. 자세한 계약

- [도메인 경계와 검사](../docs/architecture/backend-domains.md), [역사·확장 호환 계약](../docs/architecture/backend-compatibility.md)
- [기능 보존 지도](../docs/architecture/refactor-feature-preservation.md), [실행 결과](../docs/architecture/refactor-backend-results.md)
- [Embedded runtime 결정](../docs/architecture/embedded-runtime-adr.md), [SQLite 동시성](../docs/architecture/l3-er2-sqlite-concurrency.md)
- [World Chat identity](../docs/architecture/p8-l-d-world-chat-identity.md)
- [Canonical recall](../docs/architecture/p8-l-h-canonical-recall.md), [Graph recall](../docs/architecture/p8-l-i-graph-recall.md)
- [응답 생성과 streaming](../docs/architecture/p8-l-p-evidence-response-streaming.md)
- [Memory batch와 종료 저장](../docs/architecture/p8-l-r-memory-batch.md)
- [Tauri sidecar lifecycle](../docs/architecture/l3-er5-tauri-sidecar-lifecycle.md)

이 문서는 구조·역할·연결·변경 예시를 설명합니다. 세부 API 필드, 모델별 예산 숫자, release 상태는 해당 코드와 상세 계약에서 관리해 중복된 기준이 생기지 않게 합니다.

## World 반응·SNS 보조 출력과 입력 예산 (2026-10-05)

Social의 service/repository가 선택 항목 중심 공개 subtree, 사용자 nested parent, scoped PostLike를 소유한다.
Relationships는 수동 반응의 audit_only source 기록을 지원 typed port로 같은 Session/UoW에 연결한다.
World Chat만 대화 개수 quota를 제거하고 tuple/unique/재시도·권한·생성 예산은 유지한다.
Characters는 전체 이름/매크로 검증을, Routine은 topic300/novelty500 정규화를 소유한다.
공통 authored-output 값은 thought280과 안전한 receipt를 제공하며 raw tail/Provider reasoning은 저장하지 않는다.
Chat raw thought finalizer는 생성 port의 선택적 callable이고 DB·prompt에 직렬화하지 않는다.
SNS 신규 정책/모델 자료는 run 생성 때 고정한다. Provider/integration의 같은 요청 준비 경계에서 공식 계수와
전송을 연결하고 runtime이 온전한 선택 문맥 제외·기존 fence/장부를 소유한다. 다른 업무는 명시적 opt-in 없이 변하지 않는다.
옛 run은 저장된 mode/legacy 입력 정책으로 재개하며 실제 계수·품질·비용과 로컬 fake 검증은 구분한다.

## SNS·Chat 이미지 소유권 (2026-09-30)

`domains/media`가 비공개 asset·공통 인식 설정·분석 캐시·분석 시도를 소유한다. `domains/identity/service/media_credentials.py`는 기존 암호화 scope 규칙으로 목적별 키를 저장하고, `domains/characters/service/generation_settings.py`가 캐릭터별 Provider/model/options/reference 선호와 revision을 소유한다. Provider adapter는 같은 Backend의 `integrations`에 있으며 별도 서버를 추가하지 않는다.

`domains/social/service/image_intent_generation.py`는 신규 Routine 글의 frozen intent, 사용량 예약, claim/lease, 실제 제출·receipt·결과 spool·첨부를 담당한다. 기존 `image_generation.py`의 기존 기능은 보존하되 신규 Provider 선택 시 중복 실행을 차단한다. Routine의 마지막 작성 단계는 장면 한 항목만 추가하며 외형·스타일·모델·비용 옵션과 허용 판단은 코드가 결합한다.

SNS/Chat·Credentials·World 소유권을 연결하는 SQL과 lifecycle 구성은 `runtime/media`, `runtime/chat/image_attachments.py`, `runtime/social/composition.py`에 둔다. domain에서 다른 domain의 내부 Session/service 구현을 역참조하지 않는다. 모든 ORM은 단일 Base이며 SQLite v26의 새 9개 table과 3개 기존 table delta는 독립된 frozen forward migration과 manifest로 검증한다. 과거 manifest를 재생성하지 않는다. 네트워크 await 전에 읽기 transaction을 끝내고, 물리 요청 직전 및 결과 첨부 직전에 현재 권한·revision·한도를 다시 검사한다.

앱 factory는 기존 `configure_chat_services`로 기본 Chat 서비스를 연결한 다음 `configure_chat_image_services`에서 그 앱의 media runtime을 받는 Generation·Evidence 서비스를 조립한다. 기본 서비스의 전역 객체를 바꾸지 않으며 full/public 두 앱 사이에 이미지 collaborator를 공유하지 않는다.

비공개 픽셀은 `MEDIA_ROOT/private-image-assets`에 저장하며 인증된 content endpoint로만 읽는다. 백업은 SQLite, 이 디렉터리와 암호화 secret을 함께 보존해야 한다. World Package는 portable DTO projection을 사용하며 이 설정·키·업로드·분석을 포함하지 않는다. 실제 생성 서비스/ComfyUI 실행 검증은 키 없는 계약 검사와 구분한다.

## SNS 계약 2 실행·입출력·역사 책임 (2026-10-03)

SNS 관계 현재성은 AI에 제공한 순서를 유지하는 입력 해시와 backend 전용 검증 기록을 분리한다. `domains/relationships/contracts`와 `policies`는 scope·참조·사실 digest·legacy 증명을, `service/social_context_validation.py`는 유한 원본 검증을 소유한다. `runtime/graph_projection/relationship_graph_read.py`가 같은 Session에서 SQLite 원본과 기존 membership·차단·observed 사실을 읽는다. guard는 graph를 다시 선정하거나 현재 값을 새 baseline으로 저장하지 않는다.

신규 run의 공통 revision 식별자는 `app/contracts/relationship_currentness.py`에서 공유하며 World Characters와 Relationships의 순환 의존을 만들지 않는다. 검증 기록은 LangGraph/Combined의 hidden 채널에 저장하고 SDK DTO에는 넣지 않는다. SDK 대기 전 읽기를 종료하며, 공개 효과는 기존 SQLite writer 안에서 최종 검증과 함께 커밋한다. 완료 효과를 먼저 재사용하고 기존 lease·source·memory·image·언어/시간대 보호를 유지한다. 구현·검증·legacy 제한은 [관계 원본 재검증 기록](../docs/verification/sns-relationship-currentness-20261004.md)에 있다.

수동/예약 SNS의 지원 진입은 `runtime/autonomous_activity/gateway.py`에 있다. 현재 부모는 계약 2의 Combined 순서를 소유하며 모델 호출 정책·복구 장부·lane wire와 canonical 공개 효과를 분리한다. `runtime/social/planned_actions.py`와 `feed_workflows.py`는 실제 공통 executor/workflow의 소유자다. 퇴역 `runtime/resident/langgraph.py` 또는 전용 Feed Provider를 경유하는 임시 facade를 만들지 않는다.

판단 전용 응답/제안의 의미는 `domains/routines/contracts/reply_writing.py`와 `domains/social/contracts/proposal_plan.py`에 두고 실제 본문·서버 task·일정/공개 제안 결합은 canonical owner에서 검증한다. 모델용 view의 필드 축소는 원천 Candidate·revision·Chat/Memory 입력을 삭제하는 절차가 아니다. 신규 wire 정책과 Routine 출력 정책은 별도 metadata로 생성 시 고정하며 이전 V2/2의 정책 부재는 기존 계약으로 읽는다.

미완료 current/V1의 퇴역은 `runtime/autonomous_activity/retirement.py`가 도메인 `routines/service/legacy_claims.py`와 조립한다. 실제 claim·불확실 효과는 actor별로 보류하고, 지원 정산 이후에만 abandoned/aborted로 종료한다. 성공·역사·원장·기존 보존 정책은 유지한다. current 설정은 승인·하루 준비·scope/revision 확인 후 조건부 전환하며 구 실행을 SDK로 재개하지 않는다. startup은 그 앱의 composition session factory를 사용한다. 상세 계약과 검증 범위는 [실행·검증 기록](../docs/verification/sns-v2-routine-io-retirement-20261002.md)에 있다.

## ComfyUI 입력·출력 연동 (2026-10-09)

`domains/media/generation_contracts.py`와 `service/comfy_workflows.py`가 legacy/v2 옵션, typed 자리표시자 위치, 유한 값·JSON 상한, 선택 경로와 실행 snapshot을 소유한다. 문자열 전체가 14개 지원 토큰과 같은 `node.inputs` 위치만 바꾸며 링크·metadata·고정 값은 보존한다. API graph의 class/input type·연결 가능성·custom node·모델 설치 조건은 `integrations/comfy_images.py`의 `/prompt` 요청에서 ComfyUI가 최종 검사한다. `/system_stats`는 연결 확인, `/object_info`는 선택적인 입력 후보 조회이며 후보 실패가 준비 완료를 막지 않는다. Partner 인증은 명시적 옵션과 별도 목적 credential을 사용한다.

다른 업무가 소비하는 지원 경로는 실제 역할 파일인 `service/comfy_workflows.py`(순수 입력 준비·선택·복원), `schemas.py`(제한된 분석·진단 DTO), `service/http_workflows.py`(framework decoding 전 raw HTTP JSON 검사)다. import 정책에 이 세 경로만 명시하며 예외나 facade를 추가하지 않는다. DTO 파일은 워크플로 알고리즘을 역참조하지 않고, 선택 함수는 `service/comfy_workflows.py`에서 DTO를 소비하므로 순환 의존이 없다.

Character와 World runtime은 실제 장면·negative·참조 scope를 조립하고, 접수 전에 seed -1을 한 번 추첨하고 양수 CLIP skip을 한 번 변환한다. 경로·graph digest·입력/출력 정책·실제 값은 기존 intent `request_json`에 고정한다. PNG Base64는 제출 시 픽셀에서 한 번 만들고 저장하지 않는다. 이전 receipt는 history만 조회하며, 이전 미제출 작업만 lease 안에서 snapshot을 보완한다. 참조 없는 텍스트 대체 경로는 제출 전에 선택한다.

자동 출력은 JavaScript Object.values 키 순서의 첫 images 배열 첫 항목을 선택한다. explicit v2도 지정 노드 첫 항목이며 legacy는 기존 단일 출력 규칙을 보존한다. 잘못된 첫 결과를 두 번째 이미지로 대체하지 않는다. 제출 오류는 receipt 유무와 HTTP 상태로 알려진 실패/미확정 상태를 구분하며, history 실행 오류·완료 후 이미지 없음은 종료 상태다.

`schemas.py`와 `integrations/comfy_diagnostics.py`는 whitelist·민감값 가림·20항목/16 KiB 진단을 담당한다. Social worker가 동일 lease의 receipt와 nullable 진단을 짧은 transaction으로 저장하고 spool 복구 시 재사용한다. Alembic 0110 및 embedded SQLite v33은 새 진단 컬럼만 추가하며 v32 이하 manifest를 바꾸지 않는다. [구현·검증 기록](../docs/verification/comfy-workflow-reuse-20261009.md)은 모의 원본 재사용, 실제 무모델 ComfyUI 통신, 미측정 AI/설치 환경을 구분한다.

## SQLite scheduler와 사진 요청 경계 (2026-10-10 LOCAL)

실제 주입 Session의 engine dialect가 sqlite면 기존 SqliteSchedulerLeaseRepository를 사용한다.
다른 dialect의 ORM port는 보존한다. lease의 acquire/heartbeat/begin/finish/release는 짧은
BEGIN IMMEDIATE와 owner/epoch/expiry 조건부 갱신을 유지하며 만료된 같은 owner도 새 epoch를
받는다. DB 작업은 Session/connection을 worker 안에서 만들고 bounded executor(worker1,
capacity4, queued deadline1초)로 event loop와 분리한다. 실제 Future 종료를 추적하며 await
취소만으로 drain 완료를 판정하지 않는다.

BUSY code의 하위8bit만 재시도한다. LOCKED/IOERR/FULL/불명 오류를 일반 재시도하지 않는다.
최대4회/총250ms/개별 busy timeout50ms, rollback 뒤 새 transaction에서 현재 값을 읽고
원래 timeout을 복원한다. canonical connection pool checkout도 50ms로 제한한다. 이 값은
풀 포화 시 빨리 실패하는 비용을 감수하고 lease 작업의 무제한 대기를 막는 선택이며 기존
일반 SQLite busy_timeout 5000ms를 전역으로 바꾸지 않는다.

재시도 소진 뒤 한 runner가 DEGRADED로 신규 tick을 멈추고 작업을 drain한다. 자기 유효
owner/epoch는 실제 heartbeat 후 재개하며 만료는 새 generation, 다른 유효 owner는 대기한다.
1/2/4/8/10초 backoff는 stop으로 중단한다. supervisor의 별도 재시작 loop는 제거하여 recovery
소유자를 하나로 둔다. 완료 tick의 begin 장부를 보존해 finish 실패 뒤 효과를 재생하지 않는다.
보조 task가 실제로 끝나지 않으면 FAILED와 최초 오류를 유지하고 새 tick/runner를 만들지 않는다.
release 실패는 최초 오류와 별도로 기록하고 stale owner는 expiry/fence로 차단한다.

health는 scheduler READY 표시에 더해 유효 owner/epoch/expiry의 실제 heartbeat proof를 확인한다.
DEGRADED/FAILED/만료는503, 복구 확인 뒤200이다. projector 기존 정책은 유지한다. 진단은
단계·안전한 code·시도/queue/transaction 시간·owner/epoch만 기록하며 SQL/본문/키를 출력하지 않는다.
원래 incident의 잠금 소유 작업은 미확정이며 Chat이 원인이라고 추정하지 않는다.

사진은 기존 Media 서버 재검증/UoW를 보존하고 정확한 POST media/assets 요청만14MiB로 맞춘다.
World 네 POST는 기존8,262,144 bytes, 파일5MiB를 유지한다. 프런트 로컬 HEIF 변환은 서버의
원본 HEIF 수용이나 인식/생성 정책 변경이 아니다. schema/migration/과거manifest를 바꾸지 않는다.
[동시성 계약](../docs/architecture/l3-er2-sqlite-concurrency.md),
[사진 계약](../docs/operations/local-photo-codec.md),
[검증 기록](../docs/verification/creator-studio-copy-media-scheduler-20261010.md)을 참조한다.

## World 영속 삭제와 이미지 출처 설명 (2026-10-12)

Worlds의 `contracts_deletion`/`models_deletion`/`service/deletion`은 canonical owner membership,
소유자 ID, 기본 SNS binding, 저장명·row_version·명시 consent·idempotency를 확인한다. 삭제 의도와
admission 차단은 같은 UoW이며 receipt는 membership 정리 후에도 immutable owner만 읽는다.
명령 키와 확인 내용은 digest로 저장한다. 기본 SNS 이름·소개·태그·이미지는 계속 편집할 수 있다.

각 도메인의 `repository/world_erasure.json`은 검토한 정리 범위를 동결한다. Runtime은 이를
canonical SQL에 연결하고, 부모 정리 전 exact PK/file/index/checkpoint ID를 journal에 기록한다.
실행 중 공개 효과 정산 후 최대100개 단위로 정리한다. lease epoch CAS와 SQLite INSERT/UPDATE
fence는 오래된 reader/provider의 새 효과를 거절하며 FK/source 검증을 끄지 않는다. 운영 lease의
정산과 새 lease 획득을 구분한다. 타 World의 같은 Character·slot은 중지하지 않는다.

불변 `CharacterImportSnapshot`/origin·identity·owner·초기 이미지는 World별 현재 설정/기록과
별도로 보존한다. 마지막 World 등록이 사라지면 Characters 소유 함수가 원본으로 표시 캐시를
복구한다. 선택·복사·명시적 등록은 기존 ownership/eligibility 경로를 사용하며 가짜 home/actor,
현재 설정 재캡처·자동 등록·자율활동 ON·기억 이관을 만들지 않는다.

worker는 autonomy OFF에도 lifespan에서 실행하고 failed/retry_wait에 같은 cursor/fence를 남긴다.
timeout은 공개 효과의 정산 증명이 아니다. FTS/Vec1/graph와 SDK checkpoint의 정확한 제거를
확인하기 전 완료하지 않는다. 퇴역 SNS FTS도 기존 파일만 정리하며 검색 lane을 재활성화하지
않는다. Checkpoint SDK의 delete_thread와 content-free thread fence로 늦은 저장을 차단한다.
파일의 resolved root·symlink/junction·공유/최초 원본 참조를 검사하며 전체 root를 삭제하지 않는다.
공식 SQLite v37/Alembic `20261012_0114`는 빈 작업 테이블과 쓰기 fence를 추가한다. v36 source
manifest와 기존 사용자 자료는 migration에서 재작성하지 않는다. native graph schema는 유지한다.

현재 첨부 이미지가 있을 때 Supervisor/CRG 시스템 지침에 공통 영어 설명을 한 번 조합한다.
`untrusted_current_image_observation`와 frozen evidence의 kind `current_image_analysis`를 실제
현재 사용자 메시지에 연결하고, 발신을 촬영/피사체 신원의 증명으로 취급하지 않는다. 이전 이미지,
payload/hash/delivery·Vision·언어/사실/페르소나·호출 수 정책은 유지한다.

[통합 구현·검증 원장](../docs/verification/chat-world-lifecycle-integration-20261012.md)을 참조한다.

## ComfyUI 전송과 관리 키 보호 (2026-10-12, LOCAL)

Media의 순수 Partner 주소 정책을 Character/World 저장·새 실행 freeze·integration의 마지막 송신에
조립한다. ON은 검증된 HTTPS 또는 정확한 loopback만 허용하고, localhost HTTP 새 송신만 127.0.0.1로
일시 고정한다. 저장 주소·base path·port는 유지한다. OFF의 keyless HTTP와 소유/폐기/lease 조건을
충족한 receipt history/view는 신규 키 전송과 분리한다. 일반 서버 Authorization은 부활시키지 않는다.
HTTP는 TLS 검증과 redirect/downgrade 금지를 유지한다. 보안 규칙을 역사 DTO 읽기 전체에 넣지 않는다.

예시 config의 구 응답/파일은 유지하고 format=api_json만 순수 graph를 추가한다. sample/raw analyze는
credential/runtime/외부 통신 없이 수행한다. 보존한 binding/output 검사는 기존 workflow validator를
통해 수행한다. renderer/seed/CLIP/metadata 제거 Base64/output/receipt snapshot 의미는 유지한다.

`core/secret_file_access.py`는 중립적인 관리 파일 접근 helper다. Windows API는 지연 로딩하고,
현재 계정의 실제 read-open과 DACL/최종 물리 경로를 검사한다. 부족한 관리 key/필요 디렉터리만 보호한다.
최초/임시 파일은 첫 쓰기 전에 보호하고 완성된 파일만 overwrite 없는 atomic link로 게시한다.
부모 디렉터리 handle을 유지해 rename/reparse 교체를 막는다. 복잡한 ACL이나 미확인은 원본을 남기고
안전한 오류로 종료한다. 소유권 변경·DPAPI 전환·키 교체·전체 AppData ACL 변경은 하지 않는다.
helper는 contributor/sidecar 시작과 관리 키 migration에만 조립하며 활동마다 검사하지 않는다.
원래 키·암호문 AAD·명시 migration secret source는 유지한다.

패키징 metadata는 관리 key/temp·환경 파일·SQLite/private backup sentinel을 거절한다.
실제 설치의 key ACL은 읽기 전용 조사이며 소스/fixture PASS와 설치 반영은 별개다.
[검증·미측정 경계](../docs/verification/comfy-security-20261012.md)를 참조한다.

## Release readiness ownership corrections (2026-10-13, LOCAL)

`identity/service/world_credential_state.py` owns the common credential row reads,
revision preservation and sealed Comfy payload interpretation. General and image
credential services depend on it in one direction while retaining the caller's
Session, authorization, purpose, version and AAD checks.

Relationships exposes `service/social_context_evidence.py` as a supported pure
projection/validation operation for already authorized immutable social context.
Chat does not import Relationships' private policy. Its historical evidence read
port describes only the retained manifest values it consumes; Runtime supplies
the concrete Memory manifest and keeps proof/World checks. Memory's situation
binding value and policy constant live with its activity contracts; the binding
policy module depends on those values without a reverse type dependency.

Worlds owns `service/character_entry.py::lock_character_entry_world_write`, which
serializes an already authorized profile write with deletion admission in the
same transaction. It neither grants access nor increments the World version.
`runtime/world_deletion/canonical_erasure.py` is the concrete canonical erasure
adapter. The protocol stays in the World contracts. Application-level assembly
lives in `runtime/world_deletion_composition.py` above low-level persistence and
fence helpers. Cold migration fence installation can reflect existing SQL
descriptors; explicit domain erasure rules still determine scope and an
incomplete descriptor set fails. It does not register models through a reverse
dependency or infer deletion policy from newly discovered foreign keys.

## Vector projection pending work and short SQLite fences (2026-10-16)

Memory owns vector eligibility separately from durable work. SQLite v39 adds
work revisions/claims, mutation frontiers, validation epochs, direct source/prior
dependencies, finite maintenance cursors and generation-independent call budgets.
Work contains identifiers and safe state only, never source text, keys or vectors.
The v38 manifests and historical migrations remain immutable.

Runtime owns the cross-domain mutation catalog (`runtime/memory/vector_mutations.json`).
Its reviewed column-level SQLite triggers record identities and world/owner epochs
in the source transaction, including bulk SQL, FK cascades and rollback. They do
not traverse lineage, call providers or write derived indexes. New source/ACL
dependencies require updating this catalog, the frozen migration and scoped tests.
ORM after-commit notifications are hints; a five-second indexed pending/due read
recovers missed hints. Idle ticks neither take the canonical writer nor scan
completed registrations. World deletion and relationship manual-review polling
retain their existing lifecycle and cadence.

`vector_proof` performs existing source/privacy validation in an explicit SQLite
read snapshot. Only immutable observations cross into the final transaction.
Dependencies select affected work; they never cache an authorization decision.
Prior edges stay direct and bounded frontier expansion visits each node once per
causal root. Absence-sensitive access facts use world/owner revisions and explicit
parent signals. Future validity/expiry boundaries become due work, including OFF
scopes. Search still revalidates canonical version/hash/access independently.

The final effect holds the canonical writer only for claim/revision/epoch/time
comparison and a bounded Vec1 effect. Extension loading, source traversal,
credential decoding, provider calls and receipt fsync stay outside this fence.
Vec1 writer admission is 25ms; canonical admission remains the existing 250ms
policy. The lock order is canonical then derived; the derived connection can be
opened first but must hold no transaction. A valid identical vector is reused;
identical metadata causes no Vec1 update. Paid-call admission rechecks ownership
and the proof and renews only an owned active claim before the bounded request.

Received vectors stay in the bounded ResultJournal until their effect is durable.
Conditional receipt removal cannot unlink a newer receipt. Canonical attempt
budgets survive generation loss; readable legacy budgets are imported before
bootstrap. Missing pre-migration budget evidence blocks automatic paid recovery
instead of silently resetting the budget. Recovery never enrolls historical
unregistered memories. Explicit preparation uses the same claims and advances
only after its page effects settle. Staging promotion is restartable after the SQL
barrier; retired work is reclaimed in bounded pages without deleting retained files.

The 24-hour safety audit compares identities in two finite 64-item passes. Normal
entries trigger no deep validation, embedding or Vec1 write; mismatches become
work. Only its maintenance checkpoint is written. Bootstrap/audit cursors have
upper bounds. Ordinary mutations remain the primary freshness mechanism.

World erasure closes result admission and removes all retained vector generations
before `memory.repository.vector_erasure` clears exact item work/dependencies/budgets.
These operational tables deliberately have no cascading source FK: deletion intent
must survive long enough to erase derived effects. Global epoch fences and finite
frontier identities contain no content; epochs are not reset, which avoids an ABA
authorization race. Normal delivery stops on an accepted World deletion request.
Individual deleted-item completion erases its operational rows after the retained
effects are removed. Character originals and other Worlds remain outside this scope.

Local evidence and boundaries: [vector pending-work verification](../docs/verification/vector-index-pending-work-20261016.md).

## Opt-in memory pipeline observation (2026-10-16, LOCAL)

Recorder paths and atomic JSON replacement belong to
`runtime/diagnostics/observation_storage.py`. SNS, memory-pipeline recording and
reporting import that lower-level owner directly; memory recording does not
import the SNS lifecycle owner. Session-ID validation, file format and bounded
Windows replacement retries are unchanged. This storage helper owns no worker,
database transaction or observation-session lifetime.

`core/work_observation.py` is a neutral process-local port, not a persistence or
business owner. Domains and providers emit structural facts through it; only
`runtime/diagnostics/memory_pipeline_observation.py` owns the opt-in SNS session,
scope allowlist, bounded queue and diagnostic files. Business threads do no
diagnostic file I/O or JSON serialization. A bounded carry-in claim scope read
is performed outside the writer only while observation is enabled.

The recorder attaches only to an unexpired, non-stopped session. At cutoff it
closes memory-event admission and removes the process-local sink under a short
in-memory lock, then drains accepted events and attempts the final health write
once, outside that lock. Repeated flush/close and a server restart cannot reopen
or rewrite a finished session. A failed final write remains incomplete evidence;
it is not retried on every idle tick. Session-bound callbacks cannot put late
events into a later session. SNS finalization drains that session's accepted work
even when a following session has already replaced the active pointer.

Historical manifests, active.json, events and exports are retained. An unfinished
session can resume after restart, and a newly started session can attach in the
same process. Idle discovery retains its one-second read-only manifest interval;
expired heartbeat deadlines do not create a tight loop, scheduler sample or file
write. Completed session files also remain unchanged during runtime shutdown.

The existing SQLite helpers retain their admission/retry/cleanup contracts.
Their spans distinguish checkout, BEGIN wait, acquired writer, commit, rollback
and cleanup. Vec1/FTS spans use distinct database identities; nested holds are
not additive. Common helpers expose safe operation names for competing writers;
plain Session writes and other processes remain unobserved. Scheduler leases,
World deletion checks and manual relationship checks are unchanged.

The pinned Gemini async adapter observes actual HTTPX attempts via public hooks.
It does not switch transport, add retries, alter credential ownership, or infer
HTTP counts from stored vectors. aiohttp and other providers are explicitly
unsupported for this ledger. Frozen prepared membership, admission, receipt
preservation, current-vector reuse, final effects and acknowledgements correlate
by safe IDs. Raw payloads, headers, secrets, SQL parameters and vectors are excluded.

The read-only bounded probe uses canonical denominators plus derived identities;
no cross-database atomic snapshot is claimed. Pre-enqueue counters, sequence gaps,
loss and final watermarks determine evidence completeness independently of storage
correctness or AI quality. An auxiliary export failure leaves the existing SNS
export intact and marks memory evidence partial. Sources absent from a frozen
package are reported unavailable, not treated as a recorder crash.

Local evidence: [Home and memory observation verification](../docs/verification/device-home-memory-observation-20261016.md).

Lifecycle follow-up: [session finalization verification](../docs/verification/observer-session-finalization-20261016.md).
