# P8-L-R Memory batch runtime

Issue [#257](https://github.com/angmoo-tree/angmoo/issues/257), branch
`feat/p8-l-r-memory-batch-runtime`, exact base
`65a4b5428f6f2d5644602b8188bfd7c8243b558e` (Today SNS PR #251 merged).
Implementation, local tests, PR-head Hosted CI, real-provider quality,
installed user verification and merge are separate Gates. See the PR for
exact-head results; this document describes the implementation contract.

## Outcome and unchanged boundaries

Successful SNS/Chat sources now have durable, code-only delivery into the
existing Memory candidate lifecycle. An opt-in worker selects retained or
skipped memories at a WorldCharacter's daily schedule or whole-app shutdown.
The same worker resumes previously authorized, unfinished work after restart.
Selection is not invoked for each activity and startup does not authorize
untriggered candidates. Normal skip is a successful outcome with zero new items.

Today SNS remains bounded L2.5 current context assembled from canonical records.
It is not consolidation input. Router, both retrieval planners, Character
Response Generator, five routes and foreground budgets `2/3/3/4/2` are unchanged.
All new paid behavior is opt-in, separately from Memory ON and legacy
`provider_mode`. Existing summary-only/provider-free v1 remains a distinct
explicit service; it cannot claim v2 jobs or accept-all after a v2 failure.

## Ownership

| Boundary | Responsibility |
| --- | --- |
| `domains/memory/domain` | selection v2 schema, time-zone policy, caps |
| `domains/memory/application` | source validation, AI proposal, fenced accept/skip |
| `domains/memory/ports` | durable repository, source reader and provider contracts |
| `domains/memory/infrastructure` | SQLite mappings, queue, consent/version/lease fences |
| `runtime/memory` | source-domain composition, reconciliation, worker and shutdown |
| `integrations/llm/memory_selection.py` | one physical provider attempt, strict opaque-ref output |
| `features/memory` | saved scope settings, consent, daily time, status and explicit retry |
| shared desktop shell / Tauri | authenticated exit handshake and accessible closing Dialog |

## Durable delivery and privacy

Runtime session hooks capture delivery markers with successful post, reply,
reaction, eligible SocialEvent, observed source and committed Chat transactions.
Post/event duplicates map to one canonical activity identity. Memory marker
failure uses a savepoint: a successful activity is not rolled back because
Memory failed. The periodic canonical anti-join scanner repairs missing markers
within recorded ON epochs; its per-epoch scan timestamp rotates bounded work
fairly and is not a source-completion watermark. Marker sequence plus persisted
trigger time admits holes without admitting newly created activity after cutoff.

Source `created_at` is assigned at ORM admission with microsecond precision if
unset; recovery does not rely on SQLite's second-resolution default at an ON
boundary. Existing source timestamps and pre-upgrade history are not rewritten.
Only actual canonical success within a known ON epoch is eligible. OFF gaps and
pre-upgrade periods without provable ON consent are never inferred/backfilled.

Sources are revalidated before candidate admission, before provider use and
again at commit. Owner, World, active membership, block/visibility, observation,
actor/direction and private-thread rules remain authoritative. Public sources
and private Chat, and different private threads, never share a provider prompt.
Only the subject's own validated action-time motivation/emotion declaration can
accompany a source. It is explicitly subjective, not proof of another actor's
motives. Unknown legacy motives stay unknown. Source/digest changes fail closed.

Model input consists of bounded canonical excerpts, not a whole-day transcript.
Original sources remain linked for later recall. `candidate-N`/`source-N` and
supplied subjective refs replace metadata IDs. The model cannot choose an owner,
World, actual source ID, retention, permissions or an existing-item mutation.
No raw prompts, source bodies, keys, provider exceptions or reasoning are logged.

## Selection and atomic commit

`memory-selection.v2` requires exactly one decision per input candidate:

- `retain`: a concise grounded summary, that candidate's evidence ref and only
  supplied subjective refs;
- `skip`: normal terminal reason and `memory=null`;
- invalidated source: code-owned rejection, not an invented AI skip.

Unknown/extra fields, missing/duplicate decisions, bad refs or incomplete output
reject the entire proposal. Structural validation does **not** prove semantic
grounding; held-out real-model assessment remains a user/quality Gate.

After a successful proposal, accepted items/evidence, candidate decisions,
selection audit, job terminal state and a dirty-brief marker commit in one
transaction. The queue lease and scope, consent/settings and installation model
versions are rechecked. OFF, account deletion, source deletion/change, model
change or a stale provider result cannot bypass the fence. Canonical duplicate
commits are prevented; an external provider call cannot be promised exactly once
across a crash. Its attempted budget is persisted before the call.

Hot Brief is rebuilt separately with code only, from at most 24 currently valid
items. Brief-only failure retains a dirty flag without repeating AI selection.
If an old active item's source is stale, rebuilding stays deferred until the
source/lifecycle is resolved; an old brief cannot bypass read revalidation.
Owner pin/correction/deletion is never silently overwritten. Account scrubbing
removes the exact owner's canonical Memory children, new queue/audit/epochs and
settings, preserving other owners and fencing in-flight responses.
Character scrubbing likewise removes that subject's Memory roots and private
thread items without removing another character's schedule or the installation
model. Bulk item deletion emits exact-ID FTS tombstones only after commit.
Departed/unavailable scopes are rejected before paid calls and cannot prevent
healthy scopes later in the bounded queue from processing.

## Budgets and implementation decisions

| Bound | Implemented value |
| --- | ---: |
| Extra Memory calls at activity/candidate registration | 0 |
| Candidates per provider batch | 1–2, adaptive to input size |
| Source text plus subjective input | 12,000 characters **and** 12,000 UTF-8 bytes |
| Complete prompt/schema normalized byte-token bound | 16,384, including 512 control-token reserve |
| Output ceiling / retained summary | 2,048 tokens / 120 characters |
| Provider calls / hidden retries or repairs | 1 per durable attempt / 0 |
| Durable automatic attempts | 3, with backoff; exhaustion persists across restart |
| Installation-wide background AI concurrency | 1 |
| Provider timeout | at most 30 seconds, shortened by shutdown deadline |
| Whole-exit memory wait / drain | 30 seconds / at most 8 batches |
| Final process cleanup | existing separately bounded approximately 8-second path |

The plan's 32-candidate value is an upper limit, not a mandatory batch size.
This initial implementation lowers it to two because every candidate needs a
decision and Korean retain text within the 2,048-token ceiling. More activities
therefore require more calls; one app exit does not mean one provider call.
Model HIGH thinking shares provider output constraints: truncation is rejected,
not silently accepted. Real-model latency/completion/grounding is not inferred
from fake-provider tests. Evaluate caps before increasing them.

The tokenizer-specific preflight requested by the plan is implemented initially
as an **offline conservative normalized UTF-8 byte-token admission bound**, not
a native Gemini token count. This explicitly avoids tokenizer downloads or an
extra token-count API call during shutdown. Full prompts and JSON schemas are
included, not just source length. Measured provider input/output/thought token
usage is recorded separately after a call. A model-native local tokenizer can
replace this approximation in a reviewed follow-up; byte bounds must never be
reported as measured tokens. Oversize input is rejected before call reservation.

## Schedule and consent

`(owner, World, remembering WorldCharacter)` selects settings. AI selection has
no upgrade default consent. The UI explains API cost and source-excerpt transfer.
One explicitly selected installation model uses the existing MESSAGE credential
catalog/resolver; saving checks readiness but does not generate. Changing the
model applies to the next attempts for all characters; no silent model fallback.

Daily scheduling is optional, default OFF, one strict `HH:mm` in World IANA time.
Saving a past time starts tomorrow. DST gaps move to the first valid minute;
overlaps use the first occurrence. A consumed local date is not replayed after
clock/timezone/settings changes. Missed dates coalesce into one authorized
catch-up cutoff; there is no OS wake, cron job or app-off background service.
Schedule disable cancels unstarted scheduled work; shutdown/explicit triggers
remain independent. Each source's assigned durable run prevents failed heads
or settings changes from silently minting an unlimited retry budget.

The worker runs every five seconds while the embedded runtime is alive. No
trigger means code-only delivery/brief work, not AI selection. Memory/AI OFF
pauses the scope. Exhausted work stays in attention until a distinct user retry,
with the previous run's attempts retained and repeated clicks deduplicated.

## Whole-app shutdown

Main host close and `ExitRequested` enter one idempotent native workflow.
Child-window close, navigation, browser unload and hiding are not triggers.
The UI stays responsive: Rust's event handler returns while a background thread
polls the authenticated sidecar `prepare/status/skip` endpoints. They are not
public anonymous exit APIs. Contributor mode without an owned sidecar does not
terminate an external Docker/backend process.

`RUNNING → QUIESCING → PREPARING → CONSOLIDATING → FINALIZING → EXIT_READY`

Quiesce stops new mutation admission and scheduler ticks, bounds active work,
and leaves the canonical store alive. `끄는 중…` plus `지금 종료` is displayed
through the shared accessible Dialog. The existing eight-second process stop
starts **after** memory preparation, not concurrently with it. Immediate exit,
deadline, provider failure or DB error preserves/reconciles durable leftovers;
late responses cannot commit an abandoned lease. Forced OS kill cannot promise
the Dialog or finishing AI, but recovery never resets persisted attempt counts.

## Schema and APIs

Embedded SQLite v8 → v9 is additive: six empty tables, 102 canonical tables,
source revision `20260904_0089`, source migration count 88. Frozen v1–v8 manifests
are unchanged. Historical Alembic revision parity is recorded; it is not a claim
of tested PostgreSQL runtime/cycle support. Installer upgrade fixtures cover
every predecessor v1–v8 and copy-on-write failure recovery.

New tables: `memory_batch_profiles`, `memory_batch_settings`,
`memory_activation_epochs`, `memory_source_deliveries`, `memory_batch_runs`,
`memory_selection_decisions`. Runs extend, rather than replace, the existing
`memory_maintenance_jobs` queue. Per-candidate terminal decisions, not MAX(ID),
determine completion. Legacy threshold/summary-only tests remain intact.

Owner API under `/worlds/{world_id}/world-characters/{subject_id}/memory`:
GET/PUT `batch-settings`, POST `batch-retry`. Mutations require local-owner scope,
CSRF, expected versions and idempotency. GET does not create settings or call a
provider. The response includes safe counts/status/time/model choices, not keys,
source IDs or original provider errors.

## Verification and user check

Synthetic tests cover actual SQLite source → delivery → candidate → fake AI →
item/evidence → Hot Brief → restart, all-skip, ON epochs/OFF gaps, late changes,
lost delivery recovery, backlog tails, daily missed slots, retry exhaustion,
privacy cleanup, concurrent claims and bounded shutdown. Next/static tests
exercise the same feature UI and saved consent/model/time settings. Real user
data and real provider calls are not needed for these gates.

Installer user steps (after the PR-head installer is available):

1. Open Memory, select one World/character, enable Memory. Separately enable AI
   selection, choose the existing message model and consent; save.
2. Set a future daily time a few minutes ahead. Make a new successful SNS post
   or Chat while ON. Verify pending work appears without immediate AI memory.
3. Let the time arrive; check completion and, if retained, item source links.
   All-skip is valid; use a meaningful real event for a positive source Gate.
4. Create another event, close the **main app**, inspect `끄는 중…`, reopen and
   confirm retained items or bounded deferred recovery without duplicates.
5. Repeat using `지금 종료`, Memory OFF, a child window close and an invalid
   provider configuration. Verify no accidental new paid work or lost source.
6. Check later Chat grounding through the evidence inspector. Merely seeing
   an item does not prove causal recall or model factuality; close that in S.

Do not mark installed/live-provider/causal, user merge or post-merge gates PASS
from mocked tests, a Draft PR or an installer build alone.
