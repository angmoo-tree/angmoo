# 0.1.0 release readiness integration

This integration publishes the existing `feat/0.1.0-release-readiness` branch for
normal merge into `main`. The starting implementation is
`a26488e219e4041642e9783963c525f1471481ab`; it contains 62 commits after the
initial base `8e6e89d69bd9e98938ef587adfc143bc3fc1ec40`. GitHub PR and main CI
are separate gates and remain pending when this report is first introduced.

## Resulting behavior and scope

- Device preferences retain Korean/English UI and accepted-job language/timezone
  inputs. The shared product viewport supports Phone and wide layouts; Windows
  uses the native window frame and operating-system resize behavior.
- World SNS preserves title/body/image composition, the left-aligned `게시글` /
  `Post` detail header, and replies before the user reply composer. Likes apply
  the server-confirmed count and viewer state to the affected post while
  preserving content, images, drafts, pagination and scroll.
- World Chat diagnostics use the centered shared dialog. Chat list and room
  delete actions use the owning soft-delete workflow and admission checks.
- The World character directory uses the shared management card display,
  current-World membership and user-first ordering. Management profile/status/
  settings and edits use the current World instance. The relationship action
  precedes the message action; graph nodes use profile images and common
  fallbacks. Profile activity statistics stay within the profile content.
- Character imports start from an immutable creation/restored/legacy-transition
  origin. World instances retain independent configuration and autonomy; new
  imports start OFF. Accepted work uses frozen inputs and existing resource,
  permission, revision and execution-lock checks.
- SQLite remains canonical. The formal v29 staged migration recognizes both
  attested early v28 and final v28 sources, validates the target before promotion
  and preserves the previous generation. See the separate
  [SQLite recovery report](2026-10-06-sqlite-v28-startup-recovery.md).

This is an integration of the recorded implementation. It does not claim that
all remaining UI decisions, real-provider quality, installed-app validation or
direct user review are complete. Older global management screens remain
available as references for later status/settings design work.

## Additional compatibility correction before publication

The legacy local character dashboard could return HTTP 500 after a saved profile
with `http://localhost:3000/icon.svg` or its old local-preview equivalent entered
the new typed import/World configuration reader. Synthetic data reproduces the
same `configuration_media_invalid` failure; it is independent of PostgreSQL.

The owning Characters import configuration validator now preserves exact
historical HTTP loopback references only for the shipped `/icon.svg` and the
existing public managed media paths. It does not fetch the URL or rewrite the
stored profile, origin payload or digest. External HTTP, nonpublic local routes,
credentials, query/fragment data, traversal and invalid ports remain rejected.
Profile writes still use the existing owned-media workflow. Existing HTTPS and
relative managed-media contracts remain in force.

The Device dashboard shows counts and the empty-state prompt only after a
successful read. Failed reads show the shared error/retry component and retain
previously loaded cards instead of presenting a confirmed zero-character state.
No additional UI copy, color, dependency, endpoint or database version is needed
for this correction. The implementation follows `frontend/ARCHITECTURE.md`,
`frontend/DESIGN.md` and `backend/ARCHITECTURE.md`.

## Executed local evidence

Evidence lives in the ignored `artifacts/release-readiness-20261006/` directory.
Only synthetic SQLite fixtures and fake/offline browser responses were used.
The existing offline Python guard blocks nonloopback provider connections and
implicit user dotenv/key loading. No operational or installed database was read
or changed during this integration verification.

| Check | Observed result |
| --- | --- |
| Before-fix compatibility regression | 7 failed / 16 passed; expected failures identify the compatibility defect |
| Final focused `test_legacy_configuration_media.py` | 24 passed / 0 failed, including actual agents list/detail and World dashboard/settings routes, immutable origin and stored profile preservation |
| Existing World configuration/import-copy/social-input suites | 36 existing cases passed in the combined run; that run also contained one subsequently corrected new test-fixture failure and is not reported as an overall pass |
| Korean/English browser error-to-success transition | Next 2 passed / 0 failed and static export 2 passed / 0 failed; failed read has neither summary nor empty state, retry then confirms a genuinely empty result |
| Frontend lint, typecheck, Next build and static export | Completed successfully on the final source; hosted CI must validate the final committed candidate again |
| Backend/frontend ownership boundaries and derived inventories | Passed; the derived import inventory adds only the standard-library `ipaddress` dependency, and the design inventory refreshes the changed source digest without raising color budgets |
| Current-tree secret scan | Fatal findings 0; binary/source asset audit notices retained |
| Complete Git-history secret scan | Fatal findings 0; 49 audit notices, including historical model/screenshot assets, remain visible |
| DCO | Initial branch ancestry passed; final appended commits require signed-off verification before publication |

The additional pre-publication inventory regression initially reported four
failures and fourteen passes. Ten new World-management/Chat-delete operations
were missing from the security inventory, and the current L4/hybrid inventories
still described earlier source/schema state. The owning routes were inspected:
dashboard/management reads require authenticated World access, settings and
mutations retain owner checks, and mutations retain the local-frontend guard.
The inventory now records those ten operations with their actual endpoint and
access class; the public derivative also includes the already-inventoried like
PUT/DELETE operations. Current L4/hybrid reports are generated from actual
source and schema v29, with their historical predecessor digests unchanged.

The security harness retains all previous predicates and explicitly includes
the seven new protected mutations, bringing the exact current session-mutation
count from127 to134. The hybrid current-schema assertion follows the approved
v29 migration. Those narrow transitions are recorded against their actual
implementation commit; no historical assertion is edited in its evidence.
The same inventory/security/hybrid test group then passed all18 cases with
zero failures. Public route generation, L4 generation and frozen-memory/current
successor checks also pass. The superseded pre-metadata contract-only run was
stopped after source changes; it is not counted as a successful final check.

The new historical fixture seeds a persisted legacy row through SQLAlchemy Core
before exercising reads. The application's immutable snapshot update guard
remains unchanged. The first combined attempt correctly rejected an ORM update
to that immutable row; the fixture was corrected instead of weakening the guard.

Source/checkpoint/node preservation uses the repository's committed, append-only
introduction and exact product-delta records. Frozen checkpoints, test
assertions, original records, CI policies and validator checks are not replaced
to obtain a passing result. Collection/preservation is distinct from executed
tests. Hosted CI, Windows/platform-shell review, PR merge and the exact merged
commit's main CI must be recorded separately in the execution ledger.

## Corrections found during the first PR CI

The first published candidate is `e2ae995b41910ce0ec0395b21c2e0d405ca2b42a`
in [PR #361](https://github.com/angmoo-tree/angmoo/pull/361). Its frontend and
Gitleaks jobs failed. Successful checks on that candidate do not replace the
required checks on the eventual final head.

- Cold-start registration tests still expected schema v27 and 149 tables. The
  current v29 registry has 153 tables, adding exactly the four import-origin/
  snapshot/World-configuration tables and removing none. The tests now require
  those additions explicitly. The focused registration, daypart runtime and
  installer fixture suites pass all 38 cases.
- Historical installer fixtures incorrectly retained the new World tables and
  admission/run input columns. Only the isolated fixture builder now removes
  those later additions for v1-v27 sources before validating each source against
  its original frozen manifest. Final v28 retains the current shape. Production
  migration code and frozen manifests are unchanged. The existing real NSIS
  matrix is extended from v1-v26 to v1-v28, retaining hosted-runner sentinels,
  failure recovery and the final idempotent reinstall. Local fixture validation
  does not count as hosted Windows installer execution.
- The old frontend parity harnesses lacked HTTP headers and current request
  scope helpers. Their historical commit pins, endpoint/payload checks, parsing
  checks and auth/storage comparisons remain in place. Exact message transitions
  approved in the earlier multilingual/typed-error implementation are listed
  separately; unknown differences still fail comparison. Identity, Characters,
  Social and 3 x 22 feature-error cases pass. The existing independent typed-error
  suite passes 53 checks in both languages, and the environment/session suite
  passes its 12 late-response transitions. Runtime transport code is unchanged.
- All 13 Gitleaks directory findings are public source Git blob IDs in the two
  append-only provenance manifests. Each of the 11 distinct source/blob pairs
  was independently checked against its actual signed source commit and
  ancestry. One exact rule/path/full-line review group distinguishes these
  values. Ten review regressions require the original objects and reject changed
  hashes, keys, paths and appended data. The same pinned scanner then reports
  zero findings for the first candidate's tracked tree and all 1,034 ancestor
  commits. This does not exempt arbitrary hashes, whole JSON files or credentials.

The final-candidate scan also detects the same 13 public source proofs embedded
as tuples in the review regression itself. A second exact rule/path/full-line
group distinguishes only those attested test tuples, including source commit.
The existing negative test additionally checks every tuple, changed value,
appended data and the sole allowed test path. All 10 review regressions still
pass; both review groups remain limited to independently verified public data.

The current L4 and hybrid reports are regenerated from these source changes.
The original introduction and product-change records are retained; new source
and assertion transitions must be appended against the actual committed fix.
Final candidate tree/history, preservation and hosted CI remain independent
completion gates after that commit.

## Notice drift found during the second PR CI

On candidate `49e46d6a5ed885cdd72c2d6ca5c57306a2b4e478`, the dependency-license
job passes both vulnerability audits and the GPL/policy checks, then rejects
the stale third-party notice. The locked dependencies already include six new
Python packages for configuration/language validation and six JavaScript
production inventory entries for the earlier translation implementation and
its peer dependencies. The notice still lists 79 Python and 60 JavaScript
packages rather than the current 85 and 66.

The deterministic notice is regenerated using the existing checker and policy.
Every installed Python version agrees with its lock entry, the pnpm 10 and
CI-pinned pnpm 11 inventories agree on all 66 JavaScript rows, all four exact
conditional dependency reviews remain valid, and the regenerated notice passes
the same strict comparison. This correction changes only the notice and this
report: no dependency version, lockfile, license policy, audit rule or workflow
is changed. The next published candidate must still pass hosted checks on its
own SHA.

## Current World browser contracts and hosted-runner incident

Candidate `b251c11167fd03359fbe5bd88228db4796cccf41` passes the hosted
dependency-license, architecture-boundary and embedded-data-migration checks.
Its frontend job instead exposes seven older browser assumptions: a non-null
World chat cap, profile-only fixtures without the management read, a closed
diagnostics dialog queried without opening Settings, aggregate likes rendered
as the viewer's own like, and pre-v2 nested post thread fixtures/selectors.

The existing Next and static tests now share typed fixtures for the current
management and selected-post thread contracts. They retain exact World/owner
scope, selected evidence and parent navigation, later-page descendants,
social counts/tabs, letter admission, model/request/stream/evidence checks,
write idempotency and the no-provider assertions. They open/close the actual
centered diagnostics dialog and check the header/message identities rather
than removed role captions. The profile edit assertion matches the approved
owner capability. Invalid owner and unrelated-root negative fixtures still
exercise the v2 boundary rather than failing only on an obsolete schema.
Korean-only static continuity fixtures explicitly declare the owner's Korean
language instead of depending on the browser's environment fallback.

After these corrections the complete local continuity profiles pass:
Next **35 passed**, with **10 existing real-AI opt-in cases skipped**, and
static **77 passed**. No test is renamed or newly skipped, and no timeout,
production validator, runtime implementation, frozen baseline, snapshot image
or CI policy is changed. The six existing browser files require an exact
append-only record against the committed source before publication. Earlier
failed attempts are retained as diagnosis evidence and are not counted as
passes. Task-owned preview servers stop when these test processes finish.

Separately, GitHub's Actions incident `3q1yb5m7ltvb` starts on October 5 at
19:11 UTC. Its October 5 20:39 UTC update still reports failures and delays in
hosted-runner assignment. The affected backend, OSS, Local Smoke and three
CodeQL analyses have explicit annotations that no hosted runner acquired the
job after multiple attempts. These failures are infrastructure evidence, not
passing product checks. The final candidate must still complete its actual
required and additional checks; the incident does not authorize bypassing a
check. Source: [GitHub Actions incident](https://www.githubstatus.com/incidents/3q1yb5m7ltvb).

## Korean defaults and subsequent frontend CI checks

The next hosted frontend run passes the current World browser continuity checks
but fails its two Local Settings cases: Korean locators have an owner response
without a saved UI language. The settings fixture and existing daily/static
creator detail fixtures now explicitly supply `ko` and a preference revision.
The card upload test saves `ko` through the real authenticated preference API
with the actual owner revision before opening its Korean creation controls.
Static daily checks acknowledge the existing environment GET/POST separately,
asserting the detector language, timezone and revision. Their original settings
write and absence-of-activity-write assertions remain unchanged; actual lease,
CAS and authentication tests are not replaced by this synthetic detector reply.

This exposes a runtime defect in the Korean new-SNS template: its saved setting
and daily descriptions are shorter than the existing World readiness minima,
so a new Korean default World is `not_ready`. The new language-parametrized
creation regression reproduces **1 failed (ko), 1 passed (en)** before the fix.
The Worlds policy now supplies complete Korean descriptions. The readiness
validator, minimum lengths, English template, schema and provider paths are
unchanged. Existing World definitions and user databases are not rewritten.
The complete local Creator backend file passes **16 tests**, including both
owner languages; synthetic card upload and duplicate registration through the
real isolated Next/backend pass **2 tests**, including pending preparation,
initial OFF, missing-key rejection and original-byte preservation.

Additional local frontend checks pass: settings **2**, shared creator Next
**12** / static **12**, daily Next **2** / static **2**, image flows in both
profiles **40**, and static Memory/native lifecycle **2**. Earlier locale,
detector and Korean-readiness failures are retained separately. No test is
renamed or newly skipped, no screenshot is recaptured, and no CI or production
validation rule is weakened. New backend test nodes and the exact template and
browser transitions require committed, append-only preservation evidence.

## Preservation and publication boundaries

At integration start there are no running Docker containers and the user has
ended the observation session. An isolated frontend preview is task-owned and
stopped after validation. Docker images/containers/volumes, user data, backups
and the Windows installation are preserved. No PostgreSQL test resource is
created and no real LLM, image or embedding request is submitted.

The branch is published with a normal upstream push and a Draft PR. Source
provenance commits are preserved by a normal merge commit; no force push,
history rewrite, administrative protection bypass or direct main push is used.
For native/platform changes, `.github/CODEOWNERS` requires successful target-OS
CI and the user's explicit review for the final candidate before Ready/merge.
The final merged SHA must be reachable from remote main and its main push CI
must finish successfully. UI user checks, installed-app state and real AI
quality remain separate from this Git/CI integration outcome.
