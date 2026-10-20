# Memory search and image settings stabilization — 2026-10-20

## Implemented contracts

The baseline is `5bdd07a6a0d57735b0b9ad6bda1d3cabf3f1325d`. This change
addresses repeated search-process startup, lost search failure details,
image credential/policy revision conflicts, vision-key prerequisites and
Google's rejection of a Routine structured-output schema.

- `MemoryHybridRuntime` owns at most two FTS and two vector processes, shared
  across characters. Each process executes one request at a time and is reused
  only after a matching result and request-cleanup acknowledgement.
- Preparing, queued, busy, retiring and quarantined ownership are distinct.
  An uncertain exit does not release capacity. Blocking process control uses a
  four-thread executor; shared preparation concurrency is two. Preparation has
  30-second individual and 60-second round limits, with a 30-second cooldown
  followed by new demand, rather than an automatic respawn loop.
- Preparation starts for an authorized, visible, memory-enabled Chat thread or
  an admitted SNS activity using memory. App startup and Home/Feed rendering do
  not start search workers. Preparation makes no AI call or memory query.
- Newly admitted social-hybrid Chat uses at most 20 seconds, retaining the
  upstream response reserve. Old admitted 10-second snapshots and other
  4-second paths remain intact. SNS selections share one 30-second deadline,
  including the existing two-target concurrency wait; final reserve is
  `min(3 seconds, 10% of remaining budget)`.
- FTS and vector connections remain request-local and read-only. Idle workers
  retain code, not search results, DB transactions or authorization decisions.
  Canonical scope/currentness validation remains mandatory.
- SNS diagnostics preserve bounded axis failures and distinguish timeout from
  I/O errors. Summaries contain at most two axes, 32 stages and 8 KiB, are
  excluded from model context, and add no per-stage database writes.
- Image credential operations use confirmed metadata revisions, including
  deletion. Image-only transport options cannot overwrite revision/provider/
  model fields. A policy conflict returns the existing typed HTTP 409;
  unrelated programming errors are not relabeled.
- Credential mutation outcomes coordinate reads explicitly. Drafts survive
  configuration refresh and real conflicts. An ambiguous write is never
  automatically resent.
- Vision activation requires a server-confirmed stored key. Loading, failed,
  missing and saved metadata remain distinct; turning recognition off remains
  available. Both Korean and English explain the prerequisite.
- Only the Routine Google wire projection removes the nested
  `source_event_effects.maxItems`. The server still enforces maximum eight,
  uniqueness, supplied/used event membership and state bounds. Existing
  admissions retain the old wire profile. The general provider adapter and
  other structured-output fields are unchanged.

## Focused local checks

Local checks use synthetic fixtures and isolated loopback servers. They do
not operate the user's product containers, installation or databases.

| Check | Result / scope |
|---|---|
| Combined backend regression | 161 nodes: 160 passed initially; one real empty-index diagnostic regression was fixed and that node passed afterward |
| Native memory consumers | Real pinned Windows Vec1 and SQLite FTS fixtures; pipeline, embedding preservation, episode and canonical guards exercised |
| Pool lifecycle | Reuse, request isolation, bounded FIFO, cancellation, deadline, partial IPC, quarantine, generation transition and shutdown |
| Security/composition | New route included in both route inventories; authentication, Origin, scope, strict body, disabled state and no-write preparation |
| Routine output | Actual full combined envelope, SDK final JSON schema, valid 0/1/3/5/7/8 effects and invalid count/duplicate/reference/range rejection |
| Image credential router | Actual 409 response, rollback, subsequent metadata GET, provider-specific deletion and generic-error distinction |
| Frontend | Changed-file ESLint, TypeScript consumers, KO/EN catalog, transport/reconciliation and preparation fixtures |
| Browser fixtures | Actual React credential/vision controls in KO/EN; these fixtures are unstyled and are not a full product visual acceptance test |
| Next proxy fixture | Actual isolated Next proxy: normal 409, socket failure, header/stream/upload cancellation, one terminal record and no mutation replay |
| Architecture/design | Backend and frontend boundary checks passed; no added legacy exceptions; design baseline remains 1,129 raw colors / 34 files / 18 surfaces / zero route gaps |

The new API increases the explicitly inventoried protected mutation count from
152 to 153. The inventory assertion also names the new route; it is not relaxed
to accept an arbitrary count. Generated current import and hybrid inventories
are refreshed; frozen predecessor inventories remain unchanged.

Useful focused commands, from the indicated directory:

```powershell
# backend
uv run python -m pytest tests/memory/test_search_worker_pool.py tests/memory/test_search_generation_lifecycle.py tests/memory/test_search_import_boundary.py tests/memory/test_search_diagnostics.py tests/memory/test_search_worker_transport_cancel.py tests/chat/test_hybrid_admission.py tests/chat/test_hybrid_canonical_guards.py tests/chat/test_search_preparation.py tests/memory/test_sns_recall_summary.py tests/routine_posts/test_output_contract_v2.py tests/routine_posts/test_generation.py tests/routine_posts/test_google_wire_projection.py tests/media/test_world_image_policy.py tests/identity/test_world_credentials.py tests/identity/test_world_image_provider_vault.py -q

# frontend
node scripts/test-chat-search-preparation.mjs
node scripts/test-image-credential-transport.mjs
node scripts/test-proxy-lifecycle.mjs
node scripts/test-proxy-disconnect.mjs
node scripts/test-entry-settings-browser.mjs --settings-only
node scripts/check-ui-catalog.mjs

# repository root
uv run --project backend python scripts/ci/check_architecture_boundaries.py
uv run --project backend python scripts/ci/check_frontend_architecture_boundaries.py
uv run --project backend python scripts/ci/check_frontend_design_contract.py --check
```

Native fixtures require the verified pinned Vec1 extension through
`ANGMOO_TEST_VEC1_EXTENSION`. No local full backend/frontend suite was run merely
as a blanket completion condition. Required remote CI remains a separate gate.

## Same-budget performance evidence

`scripts/benchmark_memory_workers.py` ran against both the archived baseline
and the changed checkout using the same Python 3.13 Windows x64 host, 34
synthetic memories, 768-dimensional fixed vectors and a 10 ms fake embedding.
Each warm condition has 30 samples. Canonical revalidation here is synthetic
read-only SQL, not the complete production hydration pipeline.

| Budget | Baseline median / p95 | Reused worker median / p95 |
|---|---:|---:|
| Chat 10 s | 1,060.8 / 1,200.2 ms | 110.8 / 155.1 ms |
| Chat 20 s | 1,026.6 / 1,195.0 ms | 117.5 / 133.9 ms |
| SNS 15 s | 1,077.6 / 1,230.5 ms | 130.3 / 178.1 ms |
| SNS 30 s | 1,041.0 / 1,272.1 ms | 123.6 / 140.2 ms |

These distributions demonstrate a warm execution improvement independently of
the timeout increase. They do not predict ARM64 emulation, native ARM64,
Android/PRoot or real embedding-provider latency.

Costs and additional observations:

- Cold request: baseline 995 ms, new 1,906 ms in these runs. The pool prepares
  additional reusable capacity; demand preparation moves that cost before
  many first searches but cannot eliminate it.
- Four idle workers retain approximately 148 MiB RSS in this fixture.
  Across 100 additional requests the total grew by under 1 MiB; each worker
  retained 139 handles. The parent grew by approximately 1.8 MiB while retaining
  detailed benchmark records. Peak observed search processes remained four.
- Three-target and mixed Chat/SNS requests completed. Killing one idle worker
  produced a legitimate partial result from the other axis, followed by a
  normal ready result. This was not mislabeled as an empty result.
- Synthetic independent writes succeeded both between searches and while a
  search request was in progress. New-run idle writer wait was below 0.05 ms;
  the concurrent canonical write waited 6.67 ms and FTS write 0.24 ms.
  Observed transaction holds were 3.49–13.27 ms. Every measured checkpoint
  returned `[0, 0, 0]`; no persistent idle read transaction blocked truncation.
- The concurrent-writer fixture establishes request-level overlap, not a
  deliberately prolonged native SQL transaction or a production load guarantee.
- Baseline and new peak process counts are equal, but persistent memory cost is
  higher. CPU totals include different auxiliary sample counts and must not be
  compared as identical-duration throughput measurements.

Detailed receipts remain in local task output (`perf-baseline-02`,
`perf-new-02`); no real queries, memories, keys or diagnostic tokens are committed.
An earlier baseline harness run ended on a missing legacy cleanup API and is
not used as performance evidence.

## Google and deployment gates

`scripts/verify_routine_google_acceptance.py` builds the actual combined
Routine request with synthetic data. Offline mode sends nothing. Explicit
execution requires a caller-supplied key file and a durable six-attempt ledger.
Each count (0, 1, 3, 5, 7, 8) is reserved before transmission; unknown outcomes
cannot be retried. SDK retries are disabled. The ledger records hashes and safe
outcomes, not the key, its file path or request/response prose.

After the implementation checkpoint, Google acceptance ran exactly six times
against source `4311a22fa58348ff877b4de5ee2a0b6e076e9d98` and passed all
0/1/3/5/7/8 conditions with `gemini-3.5-flash-lite` (medium, 8,192 output tokens,
one SDK attempt). Every response passed JSON and server validation. The local
receipt binds the full schema and implementation hashes; a later source can
reuse it only while all fingerprinted implementation files remain unchanged.
No request was retried. Main merge and candidate generation also require the
repository's latest-head checks.
The acceptance probe supplies a permitted synthetic output example; it verifies
schema acceptance and server validation, not spontaneous narrative quality.

PR browser CI exposed a consumer fixture still forbidding the newly approved
Chat preparation POST. It now checks exactly one scoped preparation with an
empty body and no further mutations during diagnostic selection/export. A Home
PWA fixture now waits for the existing asynchronous ensure effect; it retains
the exact one-request assertion instead of treating shell visibility as readiness.
Both focused browser cases passed locally, and the next PR frontend CI completed
successfully. The design inventory updates only that fixture's content hash.

The full backend CI also identified two older route consumers: the public API
operation count and the P8-L-D later-route allowlist. They now explicitly include
the protected preparation POST (238 paths / 293 operations). The frozen
P8-L-A/B/D identity and migration evidence is unchanged. Five focused public-route
and historical-inventory tests passed after this correction; forbidden routes
and exact-count checks remain enforced.

Two temporal-recall fixtures retained a historical event date as their execution
deadline. Their fixed event-time semantics remain unchanged; the execution
deadline now uses the live clock so the production response-generation reserve
is exercised. The ER0 inventories were regenerated to update the hashes and line
locations of changed sources; no storage, compatibility or parity allowance was
broadened.
The combined temporal-recall, ER0 inventory, public-route and P8-L-D regression
selection passed all 28 cases locally.

PR CI, main CI, fixed P3 artifacts, fresh-volume command preparation, actual user
testing and official publication are separate statuses. No official publication
or user-environment startup is part of this implementation check.
