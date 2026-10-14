# SNS recovery consistency verification

Implementation base: `ea8136844a8c491133186a31d52b5e23b3a32731`, branch
`fix/sns-recovery-consistency`. This record distinguishes source regression from
remote CI and deployed/installed behavior. The implementation follows backend
ARCHITECTURE and frontend ARCHITECTURE/DESIGN; no schema migration is introduced.

## Implemented contracts

- T01 reserves four result slots before submission (each at most the existing
  Media-owned 24 MiB input limit). Immediate handoff uses immutable job/attempt
  binding; no eviction, no Session/credential in the result journal. Hashing and
  serialization precede the writer. The fenced atomic journal contains bytes,
  binding, length/hash and version; only a verified journal permits durable
  `result_received`/`result_pending`. Legacy `.json`/`.pixels` are still readable
  for proven submitted attempts. Media normalizes outside the writer, then fresh
  scope/claim checks guard registration. Ambiguous commits retain registered
  assets; stale attempts cannot remove another journal. Cancelled prepare work
  reconciles only a proven never-submitted reservation.
- T02 validates current identity/World/owner and execution claims before reading
  committed effect/state/situation receipts. Exact action signatures, source
  bindings and expected/resulting state versions drive replay; `origin` or a
  guessed increment does not. Already committed effects are reused; partial
  writers omit proven completed tasks. Historical success and newly executed
  counts remain separate. External state changes cannot authorize new effects.
- T03 prepares immutable admission/context/checkpoint material with a closed read
  Session before applying a page of at most 16. A fresh writer batches material
  checks and retains current source/ACL/epoch/result/parent validation and
  savepoints. Whole-prefix rollback preserves cutoff/cursor; stale preparation
  gets at most two extra prepares before deferral. Existing document/source
  bounds, SQLite 4-attempt/0.25-second policy and projection invalidation remain.
  Heartbeat retries only exhausted BUSY, at most two extra calls (50/100 ms),
  within two seconds including queue and the last committed lease/drain margin.
  TTL 45 seconds, interval 10 seconds and drain 20 seconds remain unchanged.
- T04 freezes `situation-target-output.v2` only at new admission. Routine permits
  `routine-post`, social planners their admitted targets, writers their assigned
  targets. Empty targets allow an empty array without an empty enum. Invalid
  hints leave the base action intact and authorize no repair call. Previously
  frozen requests keep their old schema/digest; blocked history is not rewritten.
- T05 separates actual fact/version/view/access changes from canonical deadline,
  BUSY and other read/database failures, retaining safe type/code metadata. One
  guard batches canonical references under the existing shared deadline; every
  later provider/effect guard reads again. Only an independent, not-yet-submitted
  lane can be removed, with one rebuild through the existing single-lane path.
  Shared authority/input or submitted-envelope failures remain common failures.
- UI uses the existing Media component, Button and tokens (**LOCAL**). KO/EN
  distinguish durable saving from an unknown result and explain that recovery
  requires existing output. Server flags determine actions. The neutral auth/
  runtime identity hook resets the component lifetime; stale polling/mutations
  do not update a different scope. Next and static share the same component.

## Relevant local evidence

The first receive regression failed against the original implementation: the
provider returned once, DB processing and the failure handler failed, and the
buffer had zero results. The fixed test retains the bytes and recovers with one
submission. Disk fsync/replace, commit rollback and ambiguous successful commit
are injected separately. Real child processes exit after journal, asset commit
and attachment; restart creates one asset/attachment/attempt without a new call.

New cases reside in:

- `tests/image_integration/test_received_result_recovery.py` — first DB failure,
  failure-handler failure, full buffer, disk/commit failures, different attempt,
  owned-future cancellation and actual process exits.
- `tests/runtime/test_activity_committed_resume.py` — exact 307→308 receipt,
  repeated settlement and wrong expected version/source/activity/actor rejection.
- `tests/memory/test_situation_prepared_page.py` — receipt/manifest/cursor mutation
  rollback and an independent real SQLite writer during parsing/hashing.
- `tests/runtime/test_sns_heartbeat_budget.py` — bounded BUSY retries/margins and
  real held-writer release with the same owner/epoch and drained executor.
- `tests/memory/test_situation_target_schema.py` — exact/empty target enums,
  independent invalid hints and legacy/new frozen contracts.
- Expanded relationship/selection regressions — safe SQLite error classification,
  one batched read followed by a fresh version guard, independent pre-submit lane
  failure and common/submitted failure protection.
- `tests/runtime/test_sns_shared_sqlite_writers.py` — two Worlds in one real
  SQLite DB, concurrent image reception, situation application, SNS state
  settlement and heartbeat on independent connections, with scoped results.
- `browser-tests/image-integration.spec.ts` — KO/EN × Next/static, narrow viewport,
  keyboard retry, saving/unknown/completed status and late mutation after runtime
  identity change. Four selected browser cases passed; no model calls occur.

Relevant existing lifecycle, World-erasure, activity settlement/checkpoint,
situation application/schedule/proof/parent-binding, SQLite concurrency and
combined generation/delivery/failure/graph suites were selected. Whole backend/
frontend pytest/browser suites were not the local default. Full source/type/
catalog/lint/import/design checks are distinct from those feature regressions.
Generated import/design inventories use their official generators; no exception,
skip, time limit or visual threshold was weakened.

Exact local JUnit/report artifacts and command outcomes are kept under ignored
`artifacts/sns-recovery-20261014`; they contain isolated fixture data and are not
public payloads. Intermediate failures were fixed: an obsolete single-read test
hook, an incomplete receipt fixture, a writer-only fixture without recovery data,
the browser retry URL fixture, and early cancellation reservation ownership.

## Measurement and limits

Five samples per mode, each with 16 synthetic receipts on the same local machine:
legacy admission parsing in the writer had p50 **188.8 ms**, nearest-rank p95
**212.7 ms**; prepared/batched application had p50 **172.1 ms**, p95 **293.2 ms**.
Admission hashes performed in the writer changed from **32 to 0**. The second
connection barrier separately proves that preparation does not own the writer.
This small sample supports reduced repeated work, not a tail-latency or CI-time
guarantee; current source checks, fsync and final fencing still cost time.
Other local regressions ran concurrently, so these five-sample tail figures also
include local scheduling noise. The current guards were retained throughout.

No paid provider/image generation, production DB edits, old failed-job replay,
Docker deployment, installed-app update, natural SNS quality observation or USER
CHECK is claimed. Before durable journaling, simultaneous disk/DB failure and
process death cannot guarantee recovery. Unknown results do not authorize a new
automatic paid submission. Persistent contention or lost authority still stops
work. PR/main integration and their actual runs are recorded separately in the
execution plan and PR evidence; local source checks alone are not merge/deploy
proof.

## First PR CI and fixture correction

PR #374 first head `55a82576`, Core run `38570276227` attempt 1 collected
6,430 backend cases: 10 failures and 66 pre-existing skips. The failing parameter
cases were old fault seams/state expectations and incomplete fixtures: image
format recovery injected `upload` although generated assets now use
`store_prepared`, buffer-only spool failures expected durable pending, daily
policy execution omitted its actor, and partial Inbox replay wrote a fabricated
signature without World/actor/result metadata. Fixtures now inject the actual
owner phase, assert submitted plus retained bytes without a journal, and record
the real action signature and scoped completion witness. Format/byte preservation,
one submit/attachment, denial of disabled actions and partial replay assertions
remain. The three related files/nodes passed **89 local cases**, no failure/skip.
No required check, product guard, timeout or test retry policy was weakened.
The updated head requires its own complete CI evidence before merge; first-head
successes are not combined with its later partitions.
