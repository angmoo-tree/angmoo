# P8-L-H canonical read and private FTS5 recall

Status: **IMPLEMENTED · LOCAL TECH PASS · EXTERNAL GATES SEPARATE**

P8-L-H turns the P8-L-F/G canonical Memory schema and write lifecycle into a
bounded read surface. `app.domains.memory` owns the framework-free recall
contracts, allowlisted primitive registry, hard-cap validator, and application
service. SQLAlchemy hydration and the disposable FTS5 projection stay under
`app.runtime.memory`. No Router, Planner, provider, Character Response
Generator, Chat send path, or LadybugDB execution is introduced in this stage.

## Domain-first read contract

`CanonicalRecallService` accepts only a `CanonicalRecallQuery`; it never
accepts SQL, table names, column names, Cypher, labels, or arbitrary operation
strings. The closed `memory-recall.v1` catalog is:

- `search_thread_messages`
- `search_posts`
- `search_memory_items`
- `list_social_events`
- `canonical_event_details`
- `get_post_thread`
- `list_activity_episodes`
- `list_relationship_changes`
- `get_character_summaries`

The validator normalizes at most 1,000 text characters, caps results and
reference sets at 50, rejects inverted time ranges, and enforces the required
text/source/character input for each operation. The foreground call count for
LLM providers remains zero. P8-L-K/M may later let a typed Planner select these
operations, but the Planner cannot expand their schema or their scope.

Every request is bound to the exact owner + World + remembering
WorldCharacter. Optional counterpart and thread constraints are applied by the
projection and then checked again against canonical rows. If Memory is OFF,
the service returns `disabled / memory_opt_out` before reading the private
projection. Projection unavailability returns explicit `degraded` with no
silent canonical full-table fallback.

## Separate private projection

P8 recall never reuses or migrates the P5 public-feed index. The two paths are:

```text
P5 feed search
→ search/generations/v1/angmoo-search.sqlite3

P8 private recall
→ search/memory-recall/generations/v1/angmoo-memory-recall.sqlite3
```

The P8 database is non-canonical and contains no provider credential or secret
material. It stores only accepted Memory summaries and the canonical source
summaries referenced by their evidence rows. Document IDs are namespaced as
`memory-item:<item_id>` and
`memory-source:<item_id>:<evidence_id>`. Each document carries exact owner,
World, subject WorldCharacter, optional counterpart, optional thread, source
type/event reference, occurrence time, and bounded metadata.

SQLite `unicode61` is augmented by deterministic CJK bigram terms and a
normalized substring fallback. Query terms are always quoted before `MATCH`,
so user punctuation and FTS operators cannot become raw FTS syntax. The
fallback uses the same already-scoped projection rows and the same result cap;
it is not a canonical table scan.

## Build, promotion, tombstone, doctor, and rollback

Startup reconstructs the projection from registered canonical Memory items
and current evidence. A rebuild creates a staging database, writes a complete
deterministic document set, runs SQLite/FTS integrity and mirror/digest checks,
checkpoints the file, and only then promotes it with `os.replace`. The previous
verified generation is retained as one rollback image. Promotion failure
restores the previous file. `doctor()` reports generation, schema version,
SQLite integrity, FTS5 availability, document/searchable/indexed/tombstone
counts, deterministic digest agreement, rollback availability, and tokenizer
strategy.

Committed item/evidence changes are observed after transaction commit. A
current item is replaced from canonical source rows; deleted, superseded,
expired, source-invalid, or otherwise ineligible items are tombstoned and
removed from FTS immediately. Memory scope bulk updates receive a runtime-owned
full item rescan so an OFF transition tombstones every document for that
owner/World/subject scope, and ON rehydrates only currently eligible documents.
Rolled-back sessions discard their pending projection identities. A projection
failure occurs after canonical commit, marks recall degraded, and can never
roll back the successful canonical Memory write. The durable maintenance jobs
from P8-L-G plus deterministic startup rebuild close a crash between commit and
projection sync without turning FTS into a second source of truth.

## Canonical revalidation

An FTS row is only a candidate. Before a candidate becomes a
`CanonicalRecallRecord`, the SQLAlchemy adapter requires all of the following:

- the exact scope setting still exists and Memory is enabled;
- the item is active, not deleted, not superseded, and not expired;
- owner, World, remembering subject, counterpart, and thread match;
- the evidence row is still attached to the item;
- the source type and source identity match;
- the canonical source digest still equals the accepted evidence digest;
- the source operation actually succeeded;
- the source is still visible and observed by the remembering subject;
- participating WorldCharacter memberships are active;
- neither direction is blocked;
- event, direction, and document metadata agree with canonical values.

A changed message/post/event therefore makes a stale FTS hit disappear until a
new accepted Memory/evidence version is produced. Hidden/deleted sources,
cross-World rows, inactive memberships, blocks, invalid events, and forged
projection metadata cannot pass revalidation. Only the resulting bounded
canonical records may later enter an Evidence Bundle.

## Runtime composition and failure behavior

The official embedded runtime owns both projections independently:

```text
RuntimeComposition
├─ EmbeddedSocialSearchProjection        # P5 feed search
├─ EmbeddedMemoryRecallProjection        # P8 private recall
└─ CanonicalRecallService                 # domain read application service
```

Startup runs each rebuild separately. Failure of P8 recall cannot disable P5
Inbox/Routine/search lanes or canonical writes. Shutdown removes listeners and
closes both projection handles. This stage adds no Alembic revision, no
Embedded SQLite canonical table, and no change to the seven-table Memory v1
schema.

## Executable gates

`backend/tests/test_p8_l_h_canonical_recall.py` proves:

- the exact private path and byte-for-byte survival of a P5 index sentinel;
- Korean/CJK and punctuation-heavy query handling;
- owner, World, subject, counterpart, thread, and document-kind scope;
- staging verification, atomic promotion, doctor, and rollback;
- accepted Chat message and Memory summary recall through typed operations;
- direct canonical source detail reads;
- stale source-digest candidates are excluded by canonical revalidation;
- Memory OFF returns zero records and tombstones the projection;
- rolled-back item changes never enter FTS;
- re-enable rebuilds eligible rows and deletion tombstones them again;
- the primitive registry contains exactly the nine allowlisted operations;
- required text and the 50-result hard cap fail closed.

The generated successor artifact is
`p8-l-h-canonical-recall-inventory.json`. It freezes the normalized P8-L-G
inventory digest, proves that the canonical schema/migration set is unchanged,
records the P5/P8 path split and lifecycle, and keeps graph recall, Retrieval
Router/Planners, Evidence Bundle coordination, Character response streaming,
owner UI, and maintenance-provider work outside P8-L-H.

## Local verification evidence

The final local tree passed the complete backend suite with **1,594 passed,
22 skipped, and 25 warnings**. The architecture verifier passed with **592
modules, 1,406 internal edges, and 312 frozen legacy exact edges**. The P8-L-H
successor inventory and frozen P8-L-G predecessor inventory both reproduce
from source, and `git diff --check` reports no whitespace errors.

The first complete backend run after implementation reported **3 failed and
1,591 passed**. All three failures were fail-closed generated-contract drift:
the ER0 runtime inventory required regeneration, the L4 architecture count
fixture still held the predecessor totals, and the P8-L-G generator had not
yet switched to its frozen-successor mode. No recall behavior test failed.
After correcting those generated contracts, the focused correction bundle
passed and the complete backend suite passed as recorded above. This history
is retained rather than relabeled as an initial pass.
