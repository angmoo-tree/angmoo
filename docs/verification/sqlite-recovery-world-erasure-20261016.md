# SQLite recovery, memory and World erasure — execution evidence

Status: LOCAL IMPLEMENTATION VERIFIED; PR/main integration pending. This document records implementation and measured checks;
the implementation plan remains the complete I00–I79 / R00–R08 contract.

- Base: `5227db9e0fddbb8588b19365c77e9b1a9a88cfdb` (main / PR #375).
- Worktree: `angmoo-sqlite-recovery-world-erasure`.
- Branch: `feat/sqlite-recovery-world-erasure`.
- Authorization: implement I00–I79 including I23-1–I23-8, publish, PR,
  applicable CI and fixes, normal main merge and post-merge main CI.
- Preserve production Docker / installed-app data and schedules. The user owns
  retrying the historical failed deletion. No release, image publication, paid
  provider experiment or installed-app replacement is part of this work.
- Follow backend/ARCHITECTURE.md, frontend/ARCHITECTURE.md, frontend/DESIGN.md,
  applicable AGENTS.md, CONTRIBUTING and CODEOWNERS. Do not weaken assertions,
  authorization, source checks, lease fencing or required CI to obtain a pass.

## Transaction ownership and units

| Area | Existing owner | Target boundary |
| --- | --- | --- |
| Common SQLite | core/sqlite_concurrency | bounded admission, commit/rollback and timeout restoration before pool return |
| Situation application | Memory repository / Runtime | immutable preparation; one receipt and its cursor/evidence per commit |
| Relationship review | Relationships / Runtime | read-only preparation; complete target/period root and receipts per commit |
| Projection | Runtime outbox worker | short claim/ack; graph effects outside canonical writes |
| Environment | Identity service | committed report separate from response read; rollback-confirmed busy only |
| Scheduler | existing resident scheduler | same lease recovery owner, epochs and heartbeat proof |
| World erasure | existing deletion worker / scoped adapter | explicit media references, exact journal identities, fenced effects and ack |
| Embedding | existing vector projection / provider registry | bounded scope/revision group, HTTP without Session, item-by-item validated storage |

## Execution ledger

- I00–I01: repository, clean main, remote main, worktrees and instructions checked;
  isolated branch created. The Codex managed-worktree tool could not resolve the
  documentation root as a Git repository; normal `git worktree add` was used in
  the actual product repository. No other checkout was switched.
- I02–I78: implemented and verified by the scoped checks below.
- I79: three signed implementation commits separate shared recovery, memory/World
  delivery and HTTP/UI diagnostics. The checkout is clean before publication.
- R00–R08: pending.

## Implemented contracts and validation map

| Plan | Implementation / evidence |
| --- | --- |
| I02–I15 / V00–V07 | Real temporary file SQLite/WAL, typed extended BUSY vs LOCKED/pool/defects; physical connection restoration, post-commit no-replay, owned queue drain. `test_sqlite_recovery_contracts`, `test_recovery_workers`; baseline common regression 11 PASS. |
| I16–I23 / V08–V13 | One receipt per commit, binding-flush then fresh batched validation; owned queue released between at most 16 fast receipt turns. Prepared-page, proof/parent/receipt recovery and application tests. The old test helper now drains the one-receipt API instead of assuming one call drains 50 receipts; result assertions remain unchanged. |
| I23-1–I23-8 / V52–V65 | Optional model-declared batching, current Gemini embedding-2/768 profile, same scope/setting/key revision groups, pending-only and current-vector reuse; single-only adapter fallback. Actual pinned SDK HTTP mock checks N=1/10/20 each one request, independent Content/vector alignment, wrong cardinality/dimension/NaN/Inf, timeout/503 without fallback. Runtime N=0/1/10/20/21 requests are 0/1/1/1/2; provider wait permits another real writer. Explicit preparation and late credential/content/erasure guards use the same path. |
| I24–I31 / V14–V18 | Complete cutoff keyset read before target root, pure exclusions, fresh target writer, existing manual/root/partial/reduce ledgers. 152-input page-boundary and consent-race tests; provider result WAL busy/restart replay with zero extra calls, expired lease adoption only for the exact attempt, new attempt/manifest rejection. |
| I32–I39 / V19–V21 | Claim/ack/finalize contention keeps the graph owner alive, processing lease replay does not consume another poison attempt, readiness waits for real unfinished backlog; all futures/drain before disposal. Existing graph/runtime 48 PASS; final core-worker set 48 PASS. |
| I40–I47 / V22–V23, V43–V51 | Existing scheduler epoch/heartbeat and SNS settlement owners retained after review and scoped tests. Image results distinguish local typed contention from nonbusy storage errors. Shared HTTP diagnostic regressions 71 PASS; no longer timeouts, automatic generation, provider or prompt changes. |
| I48–I55 / V24–V28 | Environment caller-owned transaction, rollback-confirmed 503/Retry-After; client 3 total POST attempts/8s round, fresh GET/detection, sequence and cancellation guards. Node environment suite PASS, UI error contracts 53 PASS, locale catalog 16 namespaces/2609 keys PASS. Both schedule advice and unchanged time/save behavior verified in 12 KO/EN Next/static cases. |
| I56–I71 / V29–V42 | Explicit image selectors exclude embedding profile strings; original/draft/shared assets preserved, invalid actual image JSON fails before unlink. Request/epoch/file generation fence, independently acknowledged external effects, same failed request explicit retry. World lifecycle browser 32 PASS (Next/static, KO/EN); historical production request remains USER CHECK. |
| I72–I78 | Cross-owner real WAL contention with World erasure, Memory/Relationship writes and environment report: bounded rejection while held, successful resumption after release, other World survives. Privacy erasure also closes retained result admission when no vector generation exists. Separate canonical/projection/file boundaries and limits documented in ARCHITECTURE and operations guide. |

## Measured tradeoffs (not real-provider performance)

Same Windows host, CPython 3.13, SQLite 3.50.4, temporary file WAL, same synthetic
inputs, before=`5227db9e`, after=current implementation. The reproducible script is
`backend/tests/memory/receipt_recovery_probe.py`. SQL count includes the competing
probe writer; total time excludes schema/fixture construction. Result rows and
applied counts were equal. Milliseconds are observations, not pass thresholds.

| Fixture | Before | After |
| --- | ---: | ---: |
| 32 receipts, 1 source each: commits / receipts per commit | 2 / 16 | 32 / 1 |
| SQL statements | 1,238 | 1,846 |
| Maximum writer hold (ms) | 277.124 | 61.223 |
| Competing writer completed commits / maximum wait (ms) | 20 / 309.037 | 25 / 331.582 |
| Total completion (ms) | 724.725 | 1,538.759 |
| 2 receipts, 256 distinct proofs each: commits | 1 | 2 |
| SQL statements | 5,199 | 134 |
| Maximum writer hold (ms) | 2,492.249 | 103.114 |
| Competing writer commits / maximum wait (ms) | 1 / 2,645.032 | 9 / 161.732 |
| Total completion (ms) | 2,651.729 | 321.429 |

Small receipts trade additional commits and aggregate time for shorter individual
writer occupancy. Their maximum competing-writer wait did NOT improve in this
sample; no broad speed claim is made. High-source receipts eliminate repeated
proof lookups and show both shorter occupancy and fewer SQL statements.
Relationship preparation froze all 152 inputs across the 100-item boundary in one
target writer measured at 68.214ms; an independent writer entered during read
preparation. Changed consent prevented root creation. These measured fixtures do
not justify an additional validation/staging schema (§6.4/§7.4); considerably larger
production inputs should be measured before adopting that extra complexity.

The batch-provider fixture proves request count reduction and per-item completion,
not Gemini latency, vector quality or billed cost. There were no real provider/GPU
calls. Token usage absent from the provider remains null; one request's usage is
never multiplied by its item count. Generation model lists, runtime dependencies,
768 dimensions, document/query prefixes and existing vector profile are unchanged.

## Failure corrections and checks

- Initial local test failures involved fixture ownership/admission (the fixture
  had uncommitted setup before a clean-writer boundary), the World owner field,
  old graph fixture lease/field assumptions and a read-only Settings property.
  They were corrected to construct valid states; assertions were not relaxed.
  In the final provider-delivery run, 49 cases passed and only the read-only
  `media_root_path` fixture failed; it was corrected to set `MEDIA_ROOT` and passed
  in the two-case cross-owner/privacy rerun. Earlier failure XML is retained.
- Backend/frontend architecture boundaries, compileall, frontend typecheck and
  changed-component ESLint passed. Next and static production builds passed.
  The isolated World browser build changed tsconfig automatically; only that
  generated change was restored. No product configuration change was required.
- The design baseline refresh changes only the hash of the shared generation
  status component; rules, exceptions and screenshots are unchanged. The current
  hybrid-memory inventory is refreshed after reviewed implementation changes;
  the frozen predecessor and schema manifests are not rewritten.
- Selected World erasure regression: **53 PASS / 2 SKIP**, 697.38s. Both skips
  require the real Vec1 extension, which was not supplied in this local run.
  Hosted Core CI builds the pinned extension and exercises those cases separately.
  Cross-owner contention/privacy: **2 PASS**; retained-index/privacy rerun after
  moving erasure ownership to Hybrid Runtime: **4 PASS / the same 2 SKIP**.
- Situation/proof/receipt recovery, manual relationship preparation and actual
  scheduler/SNS settlement: **121 PASS**, 907.29s. Final vector admission,
  delivery, lifecycle and explicit preparation: **18 PASS**, 186.69s. The latter
  includes no-attempt-consumption on real projection DB contention and isolation
  of a corrupt receipt from unrelated pending items.
- Final common/graph/runtime/review subset: **48 PASS**, 82.49s. A focused review
  delivery follow-up (**9 PASS**, 23.74s) also checks that a lost durable result stays outcome-unknown
  and never silently resubmits, even if its submission marker is later absent.
- PR/main results remain pending below; starting a pipeline is not a PASS.

## Retained-result lifecycle and remaining boundaries

Each private journal namespace allows 512 files / 16 MiB per World and 256 KiB per
record, with digest checks, atomic writes and per-World publication/erasure locks.
Successful delivery removes the result; World or individual privacy erasure
removes content and leaves a content-free late-write fence. Corruption and quota
do not grant a new paid request. In-process received buffers remain bounded; a
crash before durable write can still lose the response. Relationship submission
markers identify that boundary as outcome-unknown rather than automatic replay.
No new canonical migration is introduced. The existing disposable attempt table
and work/request receipts remain the only progress ledgers.

Managed file generations are matched exactly before deletion and live references
are checked under the canonical writer. A pre-existing path-only journal entry
with an existing file is retained because its generation cannot be proved. This
can leave a legacy unreferenced file, deliberately preferring preservation to
deleting a replacement asset. It is not reported as an unlinked file.

The production deleted-World request, installed app, Docker checkout, real AI
quality and real embedding latency were not exercised or changed. The owner can
retry the historical request after deploying corrected code; that USER CHECK is
independent of this branch's synthetic tests and future main integration.

## Evidence boundaries

Local regression, synthetic performance, remote PR CI, merge/main CI,
deployment, real provider performance and direct user checks remain separate.
No current installed-version or user-database health claim is made here.
