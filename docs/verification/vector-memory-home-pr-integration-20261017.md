# Vector memory delivery and Device Home integration preparation

Date: 2026-10-17 (Asia/Seoul). This is the source-side preparation record;
hosted PR, merge and main checks are separate exact-commit evidence.

## Source and scope

- Branch: `feat/vector-index-pending-work`.
- Initial HEAD: `546f71c0e20051297930c57ea93d152bd8b5544a`.
- Refreshed main: `117dd3f7ab0359860c88833711c1cdd21200aa50`.
- Initial tree: clean; main-only commits: 0; feature-only signed commits: 6.
- Initial feature diff: 101 files, 8,172 additions and 436 deletions.
- No existing remote feature branch or PR at the initial read-only check.
- Rulesets require eleven checks and an up-to-date base; normal merge only.
- Initial CODEOWNERS paths do not intersect this change. Recheck after any CI fix.

The branch combines pending/revisioned vector work, bounded SQLite writes,
model-capability-aware situation embedding batches, v39 migration and sidecar
resources, retained Device Home content during refresh, environment ownership
coordination, and bounded opt-in observation with terminal-session detachment.
The two existing World-deletion/manual-relationship polling policies are preserved.

## Pre-publication architecture correction

The boundary checker reproduced one module cycle:
`memory_pipeline_observation` -> `sns_observation` ->
`memory_pipeline_observation`. Memory evidence used the SNS lifecycle module's
path and atomic-file helpers, while SNS instantiated the memory recorder.

Move the existing path validation and atomic JSON implementation to
`runtime/diagnostics/observation_storage.py`. All three consumers import the
actual storage owner; the memory recorder no longer depends on SNS lifecycle.
This preserves JSON layout, session-ID validation, atomic replacement, temporary
file cleanup and bounded Windows sharing-conflict retries. It changes no schema,
AI call, provider key, admission cutoff, event limit or recorder finalization.
Fault-injection tests patch the actual memory/reporting consumer after the move.
The generated import inventory is refreshed from source, with no policy exception.

The initial architecture check failed on that cycle; the corrected source passes
with 1,560 modules and 6,759 internal edges. Existing scope/expiry/loss/finalization
tests are rerun against the corrected owner. Validation results are recorded below
after completion, not inferred from the refactor.

## Verification boundaries

Earlier source-scoped evidence remains in:

- [Vector pending work and SQLite fences](vector-index-pending-work-20261016.md).
- [Home, environment and observation](device-home-memory-observation-20261016.md).
- [Observer finalization](observer-session-finalization-20261016.md).
- [Situation embedding delivery](situation-embedding-batches-20261016.md).

No operational Docker rebuild/restart, installed-app update, user-data mutation,
release/tag/package publication or external model call is part of this integration.
Focused tests use isolated fixtures with external networking denied. The initial
test invocation used the repository root and failed collection because `app` was
not on that Python import path; the corrected invocation runs from `backend`.
This invocation error is distinct from a product or test-assertion failure.

Hosted CI will use the existing impact classifier. The migration, persistence,
shared scripts/security and packaging changes require full backend and Windows
validation. Do not weaken checks, mix shard attempts or use old-SHA passes.

## Completed local preparation checks

- Observer lifecycle, memory evidence/reporting, SNS and situation observation:
  **78 passed**; two native cases initially skipped without the explicit fixture.
- Actual worker, verified Vec1 DLL, SDK MockTransport, official CLI and PowerShell
  collector: **2 passed** after setting the verified native resource. The combined
  selected set therefore has **80 distinct passed cases**, no unresolved skip.
- Fresh-process memory-recorder import is independent of SNS lifecycle and leaves
  observation disabled until an explicit session attaches.
- Backend import inventory/boundary, frontend boundary/design, deferred-runtime
  inventory, OSS boundary and secret-allowlist metadata: PASS.
- Current hybrid-memory inventory, L4 inventory, frozen memory predecessor,
  public route inventory and embedded migration contract against refreshed main:
  PASS. Hybrid-memory drift was 23 source-file records from existing branch
  changes, with no non-file contract change; L4 drift was three current import
  counts. Only generated facts were refreshed. Policy/legacy exceptions and the
  frozen predecessor remain unchanged.
- DCO for the six incoming commits: PASS. The preparation commit is also signed
  off, and the full outgoing range must pass again before publication.

These checks do not replace hosted full backend, frontend or installer results.
Raw isolated-fixture logs remain local under
`artifacts/vector-memory-home-pr-20261017/`; no operational observation records
are included in the contribution.

## First hosted result and correction

Draft [PR #382](https://github.com/angmoo-tree/angmoo/pull/382) initially used
`67ad2633f95b2120708accb8b8fffae68c99cded` and main
`117dd3f7ab0359860c88833711c1cdd21200aa50`.
Core impact run `38924235126`, attempt 1, reports full backend/full Windows,
checkout `e0f4a9812fd611267e16d93a5cd41b804c728715`. This is the PR merge checkout,
not the source HEAD or a main merge result.

Governance job `117051584728` in run `38924235148` failed one assertion with
238 tests passed: the exact credential-reveal boundary list still named vector
batch `_submit`. Instrumentation moved its existing adapter call into
`_submit_batch`; `_submit` now only scopes observation and delegates. The source
still resolves the admitted batch's credential immediately at the provider call.
Update that one exact function name, retain the equality assertion and all other
boundaries, and run the boundary tests plus batch transport/privacy regressions.
This does not widen the credential API, add another allowed caller or disable
secret scanning. The first failed SHA remains historical, never a final CI pass.

Focused correction checks: credential ownership/boundaries plus observed embedding
groups and transport, **26 PASS**, with external networking denied. No product
credential handling or provider execution code changed in this correction.

## Follow-up CI findings on 8c76f62b

- Core job `117053835529` expected six default-World preparation writes. The new
  Home lifetime deliberately reuses successful preparation on a failed list GET
  retry, so five writes are correct (initial entry plus four reloads). Preserve
  exact six list reads/five runtime reads, and add intermediate assertions proving
  that retry performs no second preparation write. Fresh production Next build and
  the focused browser scenario passed without retry. Only the generated spec hash
  changed in the design inventory; the design policy/counts are unchanged.
- Core shard job `117054173834` found two consolidation failures before an
  unrelated journal interruption. Local reproduction found seven failing cases:
  instrumentation had accidentally moved the `episode_v1`/`activity32` foreground
  return outside `if chat_is_active`. Restore the conditional return. This is a
  runtime correction, not an expectation change; active-chat deferral remains.
- The same shard's observer file-failure test patched every `.jsonl` open, also
  rejecting the CI plugin's progress journal before fixture teardown. Limit the
  injected failure to that session's exact event file and restore the patch when
  the flush finishes. The real `ExecutionCoverage` plugin now records all three
  phases of that test successfully; recorder loss assertions remain intact.
- Windows build job `117053910368`, run `38924731651`, exhausted bounded Vec1
  downloads with HTTP 500. No hash/TLS/version check was bypassed. A new source
  run must build and validate the installer; this failed run is not reused.

Focused backend validation: consolidation requests, activity batches and recorder
failure/lifecycle tests **28 PASS**; episode batch/restart/schedule-shutdown tests
**5 PASS**; the recorder case repeated with the actual CI journal plugin **1 PASS**
(a duplicate test case, not an extra unique case). External networking was denied.
Additional completed-shard findings and corrections:

- Chat soft deletion now emits two atomic OLD/NEW invalidations and advances its
  World fence. The preservation test compares every unrelated row and exact new
  notifications/revision, including idempotent replay, instead of treating any
  outbox write as data loss. The complete Chat deletion file passes **27 cases**.
- Privacy inventory omitted six new vector tables. Account/Character scrubbing
  now removes the selected memories' work, dependencies and attempt budgets in
  its existing transaction. Shared monotonic fences and generation checkpoints
  remain; source notifications survive until derived cleanup/fanout drains them.
  Scope, other-owner/Character preservation, commit and rollback are tested.
  Existing account/Character batch scrub cases also pass (**2 cases**).
- The v36-to-v37 migration test now requests that exact target and verifies the
  exact migration callable. Current v39-chain coverage remains in the migration
  suite. The core-module inventory records the neutral observation port; ER0
  inventories now reflect the actual SQLite source and Dockerfile. No historical
  manifest, exception or import policy is loosened.
- Static Home ownership is checked through its actual hook/controller, which
  owns the list API. Additional consolidation and relationship follow-up tests
  pass **28 cases**; privacy, migration and current-inventory tests pass **20**.
  The separately selected native Vec1, static-export and privacy-table coverage
  checks pass **24 cases**. Initial fixture failures in the new privacy test
  (required confidence/salience and closed memory-kind vocabulary) were corrected
  before its final four scoped cases passed; they are not product failures.

The Vec1 original source endpoint subsequently redirected to an HTML introduction
instead of C source. Keep revision `8fc7b115a4`, version 0.7 and its existing digest
`8571bb4f77f9547d11ad11e2f72e0de7d3b2ab44e7930151998bce9377ed4b86`.
The unchanged public-domain source was recovered from successful Core preflight
artifact `vec1-sources-ecb42e4aee293a245b804e0aa93c047ccf224f7b-1`, run
`38924731687`, and independently hash-verified. Track it under `scripts/vendor/vec1`
with provenance and exact-byte Git attributes. Every build/cache read retains
digest verification; missing/corrupt source fails closed. SQLite headers retain
their pinned official URL/hash. Windows and Docker compile their own binary.
Download/cache/bundled-source tests pass **19 cases**, and a fresh native Windows
build plus real SQLite extension tests pass. No dependency version changed.

Current backend boundary and frontend design gates pass. Generated inventories
contain only reviewed current source facts. Hosted final-SHA results remain
pending; superseded successes are not used as final evidence.
