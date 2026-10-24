# Chat Today manual-like delivery contract — local verification

Date: 2026-10-25 KST. Branch: `fix/android-photo-picker-input`.
Baseline: `eecd5c8590972e6e2ef00a44aa8c29f95853aa4e`, initially clean.
This record covers the source and tests in the commit containing this file.
It does not certify a released image, installed app, real provider or phone.

## Problem and resulting behavior

With memory enabled, a selected user like/unlike in Chat Today was rendered as
prose but then parsed as the structured SNS JSON record. The baseline reproduced
two pre-provider failures and six successful controls. Its `8 passed` means that
the expected failures were reproduced, not that the bug was absent.

Chat now binds each selected event to its own immutable Today entry through the
same projection used for assembly. Runtime constructs the existing private
`SourceEventBasis`, checks it against fresh canonical facts, and captures the
actual final payload fragment. SNS keeps its existing JSON adapter. Likes,
unlikes and eligible manual replies remain usable without promoting arbitrary
`audit_only` sources or changing their retrieval status.

- Private owner/World/subject/thread/request binding, event identity, revision,
  source/target/root/parent lineage and final text are checked before generation.
- Distinct Today events with identical prose remain distinct. Exact duplicates
  retain a complete item rather than mixing references and metadata. Existing
  item/count/character budgets remain in force.
- `parent_post_id` is private preparation information. Provider/inspector shapes,
  snapshot hash/version, manifest v2 and persisted receipt/proof formats remain
  compatible. There is no DB migration or new durable format.
- Source currentness failures retain `source_context_changed`. Deterministic
  binding failures use `situation_evidence_contract_invalid`, `CONTRACT_INVALID`
  and `retryable=false`. Provider failures retain their own classification.
- Capture uses `no_autoflush` and does not commit or roll back caller work.
  Dirty/deleted pending edits fail before refreshing ORM rows; unrelated pending
  inserts remain pending. The response UoW owns the write checkpoint.

## Relevant offline checks

All backend checks used synthetic data, isolated SQLite and the repository's
external-socket denial (`ANGMOO_DENY_EXTERNAL_NETWORK=1`). The actual final Chat
generation adapter ran with only external transport stubbed. No real AI or
embedding call, real user write, installation change or phone access occurred.

| Run | Result | Scope |
|---|---|---|
| `final-contracts.xml` | 76 passed | New binding/delivery/lifecycle cases plus existing receipt/Today contracts |
| `chat-related.xml` | 111 passed, 1 skipped | Response evidence, identity/display, Today scope/ownership/parent lineage |
| `durable-related.xml` | 41 passed | New-Session apply/recall/detail/currentness, proof/recovery, cancellation/deadline/replay |
| `sns.xml` | 87 passed, 1 skipped | Existing Inbox/Feed/Routine manual-event paths and Routine manual-comment repair |

Across these four runs: **302 distinct test cases passed, 2 skipped, 0 failed**.
Runs overlap; their individual pass counts must not be added as distinct cases.

The new tests exercise real user like transitions (including repeated state,
unlike and relike), nested reply targets, memory ON/OFF, selected/unselected
Today, CURRENT_CONTEXT/CLARIFICATION/CANONICAL/GRAPH/BOTH, exact payload tampering,
cross-scope rejection, and fresh source edits/deletion/privacy/block/invalidation.
They verify persisted receipts in a new Session through apply, private memory
recall, detail/hydration and revalidation. A source hidden after recall cannot be
reused. Missing auxiliary output preserves the assistant with a blocked receipt;
a receipt write failure rolls the assistant back. Replaying a committed request
does not generate or store a second answer.

Skips are existing environment gates, not newly added skips:

1. `test_bounded_input_and_relationship_read_costs`: preserved historical Git
   baseline required by that older comparison was not supplied.
2. `test_manual_situation_fts_vector_and_downstream_guards`: real Vec1 extension
   build was not supplied. FTS/vector extension integration remains unverified in
   this local run and must be covered by the release's extension-capable checks.

The actual frontend Chat transport parser and React failure component passed
six focused checks for the new failure code, rejection of private extra fields,
English/Korean fallback text and retry control. No frontend product code or
catalog changed; this was an offline consumer check, not a phone/browser test.

## Database and structural checks

| Selected events | Total capture SELECTs | Shared evidence batch | Existing per-event evidence reads | DML / flush / commit added |
|---|---:|---:|---:|---:|
| 1 | 17 | 1 | 1 | 0 / 0 / 0 |
| 12 | 105 | 1 | 12 | 0 / 0 / 0 |

These are deterministic fixture counts for the complete capture boundary,
including existing source/scope checks, not phone latency or peak-memory data.
Targeted reads are bounded by selected events; no event-history scan or global
cache was added. Identical duplicate items are removed before capture. Tests
also assert there is no actual SQLite write transaction across provider await;
a SQLAlchemy logical read transaction is not counted as a SQLite writer lock.

Architecture inventory and boundaries passed (1,605 modules, 6,970 internal
edges, zero legacy exception edges). The inventory was regenerated with its
normal generator; no boundary allowlist was widened. Changed/new Python files
passed Ruff F rules and syntax parsing, and `git diff --check` passed. Whole
backend/frontend suites, remote CI, main integration and deployment were not run.

## Evidence and limitations

Local detailed evidence is in workspace `.task-output/chat-today-like-contract-20261025/run-01/`:
`verification.md`, `validation-summary.json`, the four XML/log pairs,
`frontend-failure.log`, `architecture-final.log`, `lint-final.log`, and tested
source hashes. Initial test-fixture and architecture errors remain recorded there
alongside their corrections; final verdicts use the runs above.

The original phone, public 0.1.1 and historical failed requests are unchanged.
This result demonstrates the local source contract and offline regressions; it
does not claim real-AI quality, phone power behavior or a completed 0.1.2 release.
