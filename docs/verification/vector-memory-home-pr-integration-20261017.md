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
