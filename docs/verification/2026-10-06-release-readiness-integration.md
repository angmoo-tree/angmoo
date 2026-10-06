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
renamed or newly skipped. These locale/template fixes recapture no screenshot
and weaken no CI or production validation rule. New backend test nodes and the exact template and
browser transitions require committed, append-only preservation evidence.

## Design report source freshness

After hosted runners resumed, architecture CI detected a stale deterministic
design report. The approved product-shell fixtures and explicit Korean settings
fixture changed three spec digests. The existing generator updates exactly
those three SHA-256 fields in `frontend-design-baseline.json`; a recursive
before/after comparison confirms every other field is identical. No product
PNG is recaptured, no raw-color budget or visual expectation changes, and the
policy and validator remain intact. The canonical checker passes with 1,215
raw colors in 36 files, 18 surfaces, zero route gaps and 36 screenshot calls.
The next candidate still requires its actual hosted architecture result.

## Frontend runtime security packages

The first fully acquired container Gate finds seven fixable high/critical Perl
issues in the frontend Debian Bookworm runtime. Its `perl-base` is
`5.36.0-7+deb12u3`; Debian records `5.36.0-7+deb12u4` as the fixed security
version ([Debian tracker](https://security-tracker.debian.org/tracker/source-package/perl)).
The frontend runtime now follows the existing OS-package repair pattern:
upgrade only installed `perl-base` alongside PCRE2, assert the minimum fixed
version with `dpkg --compare-versions`, and remove APT lists in the same layer.
The pinned Node base, application lockfile, runtime user, image labels and
healthcheck remain unchanged. Trivy severity, fixable-finding policy and secret
rules are retained; the rebuilt exact-candidate image must pass the real Gate.
Local Docker asset, runtime and release contract checkers pass, together with
their 20 existing regression tests. Image package and scan evidence is recorded
separately from these source-contract checks.

## Approved relationship-avatar visual expectation

The old ready-graph PNG still displays the full name inside a pink node. The
approved World profile contract instead uses the common profile avatar, with
its existing initial/color fallback when the fixture has no photo. The pinned
Playwright 1.62.1 Noble environment reproduces the same 1,558-pixel difference
in Next and static. The expected, actual and difference images are inspected;
the difference is confined to the avatar node and the existing direction
marker revealed at its boundary. IDs, layout, edges, labels and accessibility
remain owned by the existing implementation.

Only `relationship-graph-ready-1440x900.png` is refreshed from that approved
contract. The degraded PNG is byte-identical. The screenshot tolerance,
fixtures, assertions, policy and remaining PNGs are unchanged. The complete
Next/static corpus passes **36 tests** in the pinned environment after the
single image update. Its exact committed binary before/after hashes require
append-only frontend-asset evidence; this automated result remains separate
from the final candidate's explicit user review.

## Backend CI preparation and private import-state erasure

The earlier complete hosted backend run reports failures before reaching its
60-minute limit. Its exact 5,411-node collection and timestamped progress identify
46 failed nodes before cancellation; cancellation is not a successful test run.
Existing activity/name/memory fixtures now initialize their synthetic World
configuration through the same explicit creation/entry unit of work as the
product. Historical tool-run doubles explicitly carry `input_snapshot=None`.
Production readiness, immutable-input and retry rules are not weakened.

The World shell contract now checks the approved management screen, and the
public API test checks the approved 206 paths / 255 operations including scoped
management and thread deletion. Existing private-route exclusions remain.
The official embedded inventory generator refreshes actual source hashes and
historical SQL markers; it starts no PostgreSQL server or compatibility test.

Privacy review exposes an actual omission: import origin/configuration records
and idle-slot accepted input were absent from existing erasure paths. The
existing privacy transaction now removes the deleting actors' World settings
and origin/draft links, then deletes only snapshots with no remaining World,
origin or draft references. Another live independent World keeps its settings
and immutable basis. Ordinary editing still cannot mutate or delete snapshots.
Character/account erasure also clears idle-slot `admission_metadata`.

Four new file-backed SQLite tests pass for single-instance preservation,
last-reference erasure, rollback and account deletion including slot input.
The existing authorization/deletion tests and privacy inventory check pass.
Related fixture regressions pass in the isolated Windows replay: the initial
62-test group, 95 tests in the revised runtime/privacy/inventory group, the four
remaining activity/tool fixtures, and all 17 public-runtime tests. A Windows
contention failure in the combined diagnostic run is retained; the unchanged
bounded-write/performance checks subsequently pass in focused execution.
The complete backend suite and final hosted candidate CI remain required.

## Newly reported backend dependency advisories

The b12e2fd8 hosted dependency audit reports two newly published advisories:
`langgraph-sdk 0.3.15` (GHSA-fvww-7h3r-vfhp) and `Mako 1.3.12`
(CVE-2026-102991). The actual lock moves to the upstream fixed versions
`langgraph-sdk 0.4.4` and `Mako 1.4.2`; no advisory is ignored or waived.
The former SDK constraint in LangGraph 1.2.2 excludes SDK 0.4.x, so the resolver
also updates LangGraph to 1.2.13, langchain-core to 1.6.6 and langchain-protocol
to 0.0.19. Other locked package versions stay unchanged. Frozen installation,
the license policy and vulnerability severity gates remain enforced.

The updated lock audit reports zero known vulnerabilities among 85 packages.
Runtime compatibility, license notices and final candidate CI are checked
separately; an audit success alone is not a complete runtime verification.
Upstream references: [SDK advisory](https://github.com/advisories/GHSA-fvww-7h3r-vfhp),
[SDK fix release](https://github.com/langchain-ai/langgraph/releases/tag/sdk==0.4.4),
[LangGraph release](https://github.com/langchain-ai/langgraph/releases/tag/1.2.13),
[Mako changelog](https://raw.githubusercontent.com/sqlalchemy/mako/main/doc/build/changelog.rst).

The b12e2fd8 backend preflight also detects a stale current hybrid-memory
inventory hash for the deliberately updated canonical World fixture in
`test_p8_l_q_memory_read_inspector.py`. The official generator changes only
that file's digest; frozen predecessor, schema, bounds, policy and all other
fields remain unchanged. The official Memory-batch successor check passes.
The exact b12e2fd8 architecture, boundary, L4 and complete backend preservation
checks pass, with 5,415 protected test lineages and all 37 preservation items.
The new locked Windows environment passes all 214 existing graph/checkpoint
and SQLite migration regressions in 356.67 seconds, including contributor
health after v28 recovery, fixed admitted input, rollback and production
upgrade preservation. Installed-package compatibility and the unchanged
license policy pass; official notices cover Python 85 / JavaScript 66 /
conditional reviews 4. The complete execution and new lock's final hosted
CI remain required.

## Preservation and publication boundaries

The 4516b2c9 candidate passes all Windows checks, including the 29 supported
upgrade cases (legacy plus SQLite v1–v28), clean installation and failure
recovery. Its backend run 37394042290 is cancelled at the 60-minute job limit
after 5,256 of 5,415 nodes (97%); eight failures are reported. Cancellation
and this partial execution are not a suite PASS. Exact collection maps all
eight failures, and they reproduce in an independent Git checkout using the
same locked Python 3.13 environment without user data or provider calls.

Three failures expose changed worker cancellation after a durable graph step.
LangGraph 1.2.13 wraps node-raised cancellation in `NodeCancelledError`, carrying
the original `CancelledError` as its cause. The Runtime adapter unwraps that
specific cause and propagates it to the lifecycle owner; unrelated exceptions
retain their failure behavior. Concurrent cancellation isolation is also tested.
Two activity-engine fixtures initialize their World configuration through the
normal creation unit of work, preserving every original policy, CAS, historical
receipt and fixed-run assertion. The installer expectation includes the already
supported v27/v28 fixtures instead of stopping at v26.

The historical E inventory is restored byte-for-byte from committed source
2f6b0e211b4a3c68aa45413dba721e89db99501d, with normalized digest
8f40f852077d32f77f1a417c9726e08d02041aa0d0fb6223ade13049e3777a79.
The original D and F inventories and digest constants remain unchanged. Once
F exists, E verifies the immutable D→E→F chain and refuses regeneration; three
negative digest cases and a write-refusal regression cover that boundary.
Current World management behavior stays owned by the current UI/API contracts
and browser checks rather than by symbols from an earlier facade.

The measured whole-suite run includes all 28 real predecessor upgrade CLIs and
reaches 97% at the old time limit. The backend budget is set to 75 minutes so the
remaining tests and post-suite contracts can finish. All tests, assertions,
failure exits, required jobs and protection rules remain enforced. Focused
regression results and the new final candidate's full CI must be recorded
separately before completion.

The corrected executor, activity fixtures and immutable inventories pass all
51 focused regressions in 15.46 seconds in the isolated locked environment.
That includes every one of the eight reproduced failures and the five added
negative/concurrency nodes. The current hybrid inventory changes only the
Runtime graph and response-supervisor test digests; its frozen predecessor,
schema, bounds, defaults and all other contracts are byte-equivalent in JSON.
The 159 unreported tail nodes separately pass in 170.19 seconds, with three
existing warnings. These focused 210 executed nodes do not replace the final
candidate's complete 5,420-node suite or its hosted checks.

The 303217c1 initial architecture CI detects one omitted deterministic import
inventory update. The official generator adds only `asyncio` to the Runtime
response graph's external imports (4,115→4,116). Module count 1,404, internal
edges 5,819, all module ownership, policy and every other inventory field remain
unchanged; legacy exception edges stay zero. The generated-inventory check,
boundary check, current Memory inventory, L4 inventory and frontend design
contract pass. This refresh records current source imports and does not rewrite
the frozen source checkpoint, predecessor inventories or permission policy.

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
