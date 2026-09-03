# P8-L-R Today SNS Activity context

Status: implemented in the worktree; local, Hosted CI, installed causal proof,
user merge and post-merge Gates are separate. Issue #250 is a separate
successor to Memory owner-control Draft PR #249, not a correction of its
verified head.

## Ownership and layers

The existing L0 identity, L1 turn, L2 recent thread, L3 Hot Brief, L4 canonical
recall and L5 graph recall remain. L2.5 is deterministic same-day public SNS
context, not a new learned memory item. Memory OFF does not disable L2.5; it
still disables learned candidates, memory writes, Hot Brief and learned recall.

- Social owns factual activity kinds and the closed subjective-context
  catalog; its public surface exports database-neutral contracts.
- Chat owns the immutable snapshot, bounded Router view, evidence selection,
  sufficiency guard and generation fence.
- Runtime adapters own batched SQLite reads, source/ancestry/execution
  revalidation, action transactions and provider composition.
- Router, Canonical Planner, Graph Planner and Character Response Generator
  roles remain. Today assembly adds **zero** provider calls.
- The frontend uses the same features/memory inspector and workspace on
  Next, static and Tauri. No route, screen, asset or dependency is added.

## Canonical action provenance

The social_action_subjective_contexts table stores
social-action-subjective-context.v1 only when an explicit action-decision
declaration is linked to the exact successful SocialEvent and
AgentPublicActionExecution. World, actor, source and evidence bindings are
validated; each event/execution has at most one row. The caller's transaction
owns the commit, so rollback cannot leave an active declaration.

Motivation and emotion catalogs are closed; each text is at most 280
characters and intensity is an integer from 0 through 100. Unspecified emotion
cannot carry text or intensity. Generic planner briefs, Character mood,
provider payloads, hidden reasoning and post-hoc inference are not substitutes
for an explicit declaration. Legacy rows receive no inferred backfill.

Read-side validation repeats version/catalog, successful execution, exact
binding and declaration digest checks. Only the responding Character's own
declaration is exposed; another actor's public reply conveys no private motive.
The declaration describes subjective intent, not proof of an external fact.

Alembic revision 20260904_0088 and consecutive embedded migration v7 → v8 add
one empty table. SQLite v8 has 96 canonical tables and source migration count
87. The v7 manifest remains frozen. Downgrade removes only the new table;
copy-on-write upgrade and rollback retain existing source data.

The supported installer fixture matrix covers every predecessor v1–v7,
including existing v7 default/override model bindings. Character/account
scrubbing removes scoped declarations before their action executions. No
installed user database is read or mutated by these synthetic gates.

## Factual read, completeness and bounds

Same owner, World and responding WorldCharacter are mandatory. Active
membership, public/unlisted visibility, deletion, moderation hiding, both
block directions, source actor, event success and execution linkage are
checked. A hidden or missing ancestor cannot grant access to a descendant.
Failed/invalidated event sources cannot re-enter through legacy Post fallback.

Authored posts/replies and direct replies received today are read from
canonical Post rows; successful events additionally provide mentions,
reactions, reposts and follows, including removal events. Direct parent and
bounded root context preserve focal conversation meaning. Unrelated sibling
branches and private Chat messages are excluded.

World timezone is the canonical day anchor. One attempt fixes day start and
complete-through before Router execution. Invalid timezone/read state makes
Today context unavailable; it does not invent a timezone or disable Chat.

| Bound | Initial implementation |
|---|---:|
| Candidate scan per source query | 2,048 rows |
| Batched identifier query | 512 IDs |
| Ancestry depth | 8 edges |
| Snapshot detail records | 96 |
| Router entries / serialized characters | 12 / 12,000 |
| Canonical body excerpt | 900 characters |
| Direct parent / root body | 300 / 180 characters |
| Per-entry content plus subjective text | 1,400 characters |
| Final evidence | existing 12 items / 2,000 per item / 8,000 total |

Queries are batched, not executed once per activity. Counts are exact over the
validated candidate set; if a scan or ancestry limit prevents an exact
inventory, counts_exact=false and coverage is partial. Such counts are lower
bounds and cannot justify “no activity” or an exact ranking. Detail overflow
preserves known counts but marks affected coverage partial. Router omissions
and text truncation are explicit. High-activity latency and model quality
require the installed/held-out Gate; these caps are not a measured p95 claim.

## Router and response

The Router receives a provider-safe manifest with counts, coverage, short
excerpts and an opaque snapshot hash. CURRENT_CONTEXT may preserve entity,
time and aggregation focus; the route catalog itself is unchanged.

The code guard upgrades an incomplete Today view to CANONICAL. It may select
CURRENT_CONTEXT for complete self-activity or a genuinely complete empty
inventory, but does not override Graph/Both/Clarification or reinterpret a
Canonical entity/relationship question. Exact missing content remains typed
retrieval. Normal full-path caps remain 2 / 3 / 3 / 4 / 2; one request-wide
repair remains the only extra foreground repair allowance.

Question-relevant Today entries join the frozen Evidence Bundle. The CRG gets
the same snapshot hash and completeness manifest, uses only recorded own
motivation/emotion, and must not claim an empty day from partial/unavailable
coverage. Event names distinguish adding a reaction/follow from removing it.
The response manifest separately reports included_detail_counts and
detail_omitted_count after the final evidence budget, so an omitted detail
cannot be treated as an absent activity. Snapshot scope must match the request,
and using a snapshot without a revalidator is rejected.

Snapshot mappings are immutable. Before CRG and before response commit,
runtime rebuilds at the **original** complete-through, compares the hash, and
rejects a changed/hidden/blocked source with retryable source_context_changed.
Later activities are not inserted into the current attempt. A new explicit
retry builds a new snapshot.

## Inspector and design provenance

The today_sns_activity kind is labelled “오늘 SNS 활동”; learned items remain
“저장된 기억”. The owner inspector revalidates exact composite source/ancestry
revision and hides stale excerpts and links. Memory OFF copy explicitly
permits current-thread and today's World SNS awareness.
The composite revision includes the validated subjective digest; invalidating
that declaration also hides a previously stored inspector excerpt.

Reference use: **DIRECT** for the existing Memory workspace, Chat evidence
Dialog and semantic tokens; **ADAPTED** for provenance and OFF copy; **LOCAL**
for Today source semantics; **REJECTED** for raw query, source ID, provider
diagnostics, hidden reasoning and another Character's private state.

## Verification and remaining Gates

The executable corpus covers exact action linkage, idempotency, catalog
rejection, failed execution and hidden ancestry, same-scope filtering,
subjective digest tampering, immutable hashes, late source changes, midnight,
bounded payloads, source revision inspector, constant batched-query shape and
reversible v7 → v8 migration. Existing route-call and fenced response-commit
tests remain required.

J–R predecessor inventories remain byte-for-byte unchanged. Their checkers
validate frozen digests once the Today successor is present; the Today
inventory owns the current v8 code, while the L4/architecture inventories
remain current-tree inventories. This is not a retroactive historical PASS.

Full backend, architecture/generated inventories, Next/static production
builds, browser/Tauri/Rust checks, installer upgrade, security and exact-head
Hosted CI are separate Gates. The user must still validate Post → Chat,
reply → inbound reply → Chat, motivation/emotion grounding and Memory OFF on
the produced installer. This patch does not declare P8-L-S or P8-L FULL PASS.

Local verification on 2026-09-04: backend **1,791 passed / 22 skipped**;
Next browser **21 passed**; static/Tauri browser **67 passed**; Local Settings
browser **2 passed**; Rust **34 passed**, fmt and clippy. Frontend lint,
typecheck, proxy smoke, Next/static production builds, architecture/design,
source migration, v1–v7 installer fixtures, dependency audit and license/notice
checks passed. Architecture counts are 669 modules / 1,764 internal edges /
2,233 external imports, with the existing 312 frozen legacy edges unchanged.
Initial local failures were v8 schema/fixture expectations and inventory
lineage drift; the final full suite above passed after their corrections.

Exact-head Hosted CI, its pinned Noble visual and actual Windows installer
runs, user installed causal proof, real PostgreSQL Alembic/concurrency and
held-out model quality/latency are not implied by those local results. Do not
merge the stacked branch until #249 is merged and the exact main base is
reconciled and verified. No release or production action is authorized here.
