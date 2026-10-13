# Release readiness integration evidence — 2026-10-13

This report distinguishes committed source, focused local regressions, hosted CI,
platform review, deployment and real-provider quality. The initial preparation
snapshot below is historical; subsequent corrected-head evidence is recorded in
the later section. Pending items are not PASS; exact final
head/base and completed CI outcomes are recorded in the PR and workspace execution
ledger rather than inferred from this earlier snapshot.

## Source and preservation

- Repository: `angmoo-tree/angmoo`; branch: `feat/0.1.0-release-readiness`.
- Original unpublished source HEAD: `9a2c9040e8a750433005f200998dfa7a187acc09`.
- Public base observed during preparation: `97102c98e67781e306103cacbd2a4bba325d15f2`.
- Original source is retained in the local `backup/release-readiness-20261013-pre-pr`
  branch. It is not pushed as part of the PR.
- The author explicitly certified the 60 missing DCO trailers and approved the
  unpublished history repair. The 70 logical commits retain order, author and
  product code/test/asset trees; only missing trailers and exact references in the
  two unpublished provenance ledgers changed. Official DCO validation passed on
  the independent replay clone. Public history and frozen checkpoints remained
  unchanged. Historical source SHAs in old reports remain historical.
- CI preparation fixes are separate signed commits after that replay. Late
  evidence retains immutable ledger order, verifies real source blob/parent
  preimages and ancestry, then follows actual Git topology. It does not use dates,
  arbitrary aliases, allowlists or omitted transitions to excuse drift.
- Preparation implementation source: `2e87d02d11f885bc4a04f8060e484b67fb1a2226`.
  The official source/API/ORM/assertion stages completed; the last full collection
  reported two obsolete unparameterized node IDs. Exact original-case mappings
  now retain their expanded matrices, with 6296 protected current identities and
  6296 collected tests. Both expanded matrices passed (6 cases). Final committed
  metadata/source validation must pass before publication and in required CI.
  Historical collection targets relevant changed test files; the final official
  checker still collects the entire current corpus and checks every protected
  lineage. Collection is not test execution.
- Completing the missing historical AST/assertion evidence increases the Git
  ledger size and validation cost. Existing entries remain append-only; immutable
  source-object caching and streaming historical ledger reads bound memory while
  retaining the comparisons. This cost is recorded rather than hiding missing
  evidence with a new current-tree baseline.

## Scope of the integration

The branch consolidates World-owned credentials and settings, private memory
batching and durable situations, Chat participant/evidence handling and optional
person hints, source revalidation and timeout recovery, Creator Studio/profile
media, World deletion with default SNS protection and reusable character
foundations, Comfy workflow compatibility, Partner transport and Windows managed
key/CSP protection. Original feature plans and their existing verification reports
describe each implementation and its measured boundaries.

Preparation corrected actual ownership problems rather than relaxing architecture
rules: shared credential state has a lower owner, situation value types have a
single dependency direction, Chat consumes a supported Relationships operation
and a neutral retained-manifest port, Worlds owns its write lock, and concrete
erasure/upper composition are separate from low-level fences/model registration.
Cold migrations can reflect SQL descriptors but reviewed deletion rules still
determine scope and an incomplete schema fails.

The preservation checker now recognizes two existing product changes through
closed, exact committed proofs. World stream termination can change its body
while all HTTP authentication/dependency/route/argument/return bindings remain
protected. Model registration retains the one canonical Base and direct owner
imports, with only the committed SQLite `after_create` write-fence hook allowed.
The retired World topic view requires its actual deletion preimage, supported
owner/behavior sources and absence of active consumers. Arbitrary hook, route,
primitive, source or dialect changes still fail. The old scheduler recovery and
Comfy Partner tests are mapped one-to-one to their actual renamed tests; exact
parent/child assertion transitions preserve the approved single recovery owner
and retired server-key contracts.

The World recommendation fixture now verifies the retained catalog and absence of
retired World topic preparation. A separate route fixture verifies current
translation/Studio route bindings rather than an obsolete `P1` heading. API
unknown-field, authorization and version assertions are retained.

The image loader/proxy lint defects were fixed without changing their HTTP and
payload assertions. `sharp` changed from 0.35.4 to 0.35.5; Next and its ESLint
configuration changed from 16.3.6 to 16.3.8. These are compatible security patches;
native install-script policy remains disabled. They address
[GHSA-wq5f-xc86-pv6w](https://github.com/advisories/GHSA-wq5f-xc86-pv6w) and
[GHSA-cjq9-62q9-8jv4](https://github.com/advisories/GHSA-cjq9-62q9-8jv4).
Lockfiles and the deterministic third-party notice match actual packages.

The exact full-tree CI audit also exposed the unresolved `braces` advisory
[GHSA-vfj7-8cjw-p6xm](https://github.com/advisories/GHSA-vfj7-8cjw-p6xm).
The registry has no 3.0.4 release despite that generic audit suggestion. Instead
of an audit exclusion, the single pinned Next lint consumer uses
`tinyglobby`0.2.17's `globSync` API. A checksum-bound pnpm patch specifies literal
directory expansion and absolute-path handling to preserve its old behavior,
including Windows drives. The regression executes the actual Next root helper
and its internal-link rule: valid roots/links stay accepted and invalid internal
anchors are still reported. The vulnerable dependency is absent from the lock
tree; 16 unused development dependencies were removed. The accepted maintenance
cost is reviewing this small pinned patch when upgrading the Next lint plugin.
The regression is wired into hosted frontend CI. Production dependencies and
application UI remain independent of this lint-only substitution.

## Focused local validation

| Validation | Result and limits |
| --- | --- |
| Scoped backend ownership/credentials/situation/evidence/World lifecycle/erasure/graph files | Initial run: 199 passed, 1 failed, 1 optional cost benchmark skipped. The obsolete heading failure was corrected and its exact HTTP/source-contract node passed separately. No new skip was added. |
| Existing provenance negatives, real Git late-evidence chain and cold erasure descriptor/fence tests | 22 passed. Missing transitions, modified source preimages and rewritten ledger history remain rejected. |
| Authenticated stream frame proof negatives | 5 passed; altered decorators, dependency/arguments and surrounding bindings remain rejected. |
| Registration fence and retired World topic view proof, including existing model preservation cases | 35 passed; missing/wrong proof, unsafe hooks/providers/dialects and active retired consumers remain rejected. |
| Single recovery-owner and Comfy Partner contract regressions | 20 passed; synthetic transport, no GPU or external provider call. |
| Expanded Chat situation delivery and native graph erasure original cases | 6 passed; all added identity/question/event-free cases remain protected. |
| Backend architecture | PASS: 1518 modules, 6540 internal edges, 0 legacy exceptions. |
| Frontend lint/type/catalog | PASS; catalog: 16 namespaces and 2617 source keys with key/parameter/plural parity. |
| Frontend ownership/design | PASS: 14 features; raw-color inventory 1157 in 35 files, 18 surfaces, 0 route gaps, 61 existing screenshot mappings. This is not a new visual user review. |
| World image URL/token/exact profile payload script | PASS. |
| Profile photo proxy HTTP/headers/chunks/CSRF script | PASS against a synthetic upstream and isolated Next server. |
| Next 16.3.8 production and static shell builds | PASS, no production key or provider call. |
| Production dependency audit | PASS: no known vulnerabilities in the audited production dependency tree. |
| Python frozen-lock audit with uv 0.12.5 | PASS: 85 packages, no known vulnerabilities or adverse project statuses at the audit time. |
| Full dependency audit and pinned Next root/link-rule regression | PASS on the local Windows runtime; no advisory exclusion or severity change. Hosted Linux execution is still pending. |
| Dependency/project license and deterministic notice | PASS: Python 85, Node 67, 5 existing conditional reviews; GPL identity retained. |
| Generated architecture/L4/deferred/embedded inventories | Refreshed by official generators and checked. Frozen migration/checkpoint/visual evidence was not regenerated. |
| Current source secret/privacy scan with asset inspectors | 0 fatal findings. Existing audit-only asset/vocabulary classifications are recorded separately; no current-tree finding was suppressed. |
| Full reachable source history scan | 17872 files, 61 binary audits, 57 audit-only findings, 0 fatal findings. Historical asset/vocabulary classifications remain visible rather than suppressed. |
| Hosted required PR and exact merge-SHA main CI | **PENDING**. |
| Target-OS CI and explicit final-head platform owner review | **PENDING**. |

The optional `ANGMOO_MEASURE_CHAT_IDENTITY_COSTS` benchmark was not enabled. Its
preserved baseline comparison was not represented as a performance PASS. The
local run did not execute the entire backend/browser corpus; required hosted
suites and Windows installer child matrices retain their full scope.

## Isolation and remaining boundaries

Validation used synthetic profiles/Worlds, temporary SQLite/graph/media roots,
fake/none providers and network-disabled backend containers. User dotenv, API
keys, conversations, installed data and active Docker volumes were not copied
into fixtures or published artifacts. Pinned pnpm 11.22.0 and Python 3.13 were
used; the isolated Windows dependency environment was materialized with uv
0.12.5. Source-only checks performed before that environment existed are not
mistaken for full runtime/asset checks.

No existing user app container was restarted, rebuilt or replaced. The user can
continue observing the existing fixed Docker image without source watch. No tag,
release, installed-app update, real model image generation, GPU/model install,
Partner payment or paid AI/embedding call was performed. Previous Comfy decoder
verification and real-AI/user-quality observations retain their original limits.

World deletion remains irreversible after admission and protects the default SNS
binding, other World scopes, shared character foundations and initial managed
media. Schema changes use shipped versioned migrations; deployment and data
rollback are independent of this Git integration. Platform-shell approval and
post-merge CI receipts are recorded in the workspace execution plan rather than
rewriting `main` to add a completion claim.

## PR365 first-head CI corrections (2026-10-13)

Attempt1 at source `0e625143` failed on stale current inventories, historical
fixture construction, retired Local-mode onboarding and former UI expectations.
Its DCO/license/full-graph/Windows advisory and Core Tauri Windows tests/build
passed; installer child gates were skipped after their prerequisite fixture
build failed. A failed/skipped check is not a merge PASS.

Historical v1-v8 direct metadata builders now omit only later v34/v36/v37 tables,
while all frozen manifests and released DDL remain unchanged. Synthetic v2 seeds
copy explicit predecessor columns with row-count/FK/digest checks, and installer
fixtures strip newer fences/tables before constructing each supported predecessor.
The cold registry explicitly includes Worlds' two deletion models; real-app media
factory tests bind middleware's actual SQL session factory to the same disposable
database as their API overrides, without disabling the gate.

The current quickstart creates keyless LLM registrations and proves that they
cannot mint retained legacy Local Bot credentials. Legacy Local Bot positive
domain tests remain. Explicit expected-status handling accepts only the selected
409 and unrelated 401/403/422/500 responses still fail the smoke.

Frontend tests exercise the current usage-state groups, compact directory,
World-embedded graph scope, pending-memory recovery, separate relationship
settings and topic states. Retired Feed diagnostic panels remain absent; scope,
authorization, late-result, idempotency, readable layout and no-provider checks
remain. No canonical PNG, visual tolerance, raw-color policy or UI wording changed.
The current design report retains 1157 colors / 35 files / 18 surfaces / 61 calls.

The synthetic real proxy uses explicit fixed-host HTTP request options. Managed
private files reject cross-platform traversal/drive syntax before filesystem IO
and also reject a symlink at the expected root directory. The TLS fixture sets an
explicit TLS1.2 minimum while preserving bad-certificate/hostname/redirect tests.

Pinned Gitleaks8.30.1 initially reported114 matches. Each was a public Git/schema
fingerprint, protocol/code fragment or explicit synthetic fixture identifier.
Added exceptions bind exact rule AND closed path AND exact matched secret value;
other secrets on the same large JSON AST line are still detected. The corrected
tracked-tree scan found0 leaks; full ancestor scanning is a separate final check.
CodeQL alerts19/20 were reviewed and dismissed as false positives: SHA256/HMAC in
the retained dev-v1 encryption/MAC protocol are not password storage, contributor
app keys use token_urlsafe(48), current envelope writes use HKDF/AESGCM and user
passwords use salted PBKDF2. Existing ciphertext compatibility and tamper/scope
rejection tests remain. Other alerts await the corrected source scan.

Local evidence: 39 initial scoped backend regressions; all31 readable installer
predecessors plus the additional installer contract passed; 11 initially failing
browser cases passed in related reruns; current media/app factory, precise HTTP
failure handling and retained Local Bot tests9 passed; focused current security,
registration, credentials and package tests43 passed. The isolated provider-free
contributor smoke persisted the reply/state and verified LLM Local Bot denial.
Hosted final-head checks, native human review, Ready, merge and merge-SHA main CI
remain pending. Fixed source does not update the user's running Docker or installer.

## Corrected source after the 7bcc22bb CI attempt

At `7bcc22bb`, required architecture, migration, DCO, license, local core/autonomy/
full-graph, Windows Tauri/host and CodeQL checks completed successfully. Frontend
failed at a retired card-creation selector, OSS scanning found four newly committed
public blob identifiers, and the packaged installer candidate failed to announce
its endpoint. The backend suite was still running when these repairs were prepared.
The source of each failed check is retained; downstream skipped installer matrices
are not successful executions.

The sidecar startup imports World's reviewed erasure inventory. Its eleven
domain-owned JSON files were absent from the PyInstaller data inputs. The builder
now reads the authoritative owner tuple without importing/starting the app,
validates each JSON's path/owner/version, and includes only those exact resources
at their real runtime paths in both OneFile and OneDir builds. Missing or invalid
policies fail packaging. A file-only frozen-layout test first reproduces the missing
resource and then loads the unchanged rules from every owned destination. Native
packaged execution still awaits the corrected Windows CI. The sanitized Defender
report is uploaded even if a later packaging step fails; raw logs/keys/DB are excluded.

Four public blob identifiers are allowed only by their exact existing path/rule/
field/value, with actual Git source/ancestry and changed-value/path negative tests.
No file, AST line, history range or unrelated credential is exempted. The reviewed
7bcc22bb tree/history scans found no leaks, including all 1147 ancestor commits;
the final corrected head is scanned again before publication.

Current schema tests now expect the actually shipped head, 174 registered tables,
and v37/0114. Old migration manifests and predecessor schemas remain immutable.
Card, Comfy/image, daily setup and static navigation tests use the existing current
controls and contracts. Provider-free request, exact payload, conflict, retry,
late-result and OFF-by-default assertions remain.

An actual static Feed/Post cold-start defect was also corrected: requests wait for
initial authentication to settle, then remount on user/session/runtime scope changes.
Late results from an old runtime are rejected. This avoids both the original
aborted-load blank state and automatic duplicate fetches that could hide a manual
retry. The production preview now uses Next's actual repository-root traced
`standalone/frontend/server.js`, preserving its existing Windows launcher behavior.

| Focused corrected-source evidence | Observed result |
| --- | --- |
| Current schema/layout/observation expectations | 21 passed; frozen predecessors retained. |
| Sidecar resource, supply-chain and native shell contracts | 21 passed; four resource cases included. File-only synthetic layout, no installed runtime launch. |
| Native Windows managed-key file regressions | 7 passed. |
| Exact public blob provenance and secret-scan negatives | 3 passed. |
| Synthetic PNG/JSON card through the actual Next proxy | 2 passed. |
| Shared image flows in Next and static | 56 passed; no external provider or GPU. |
| Current World-scoped daily setup in Next/static | 2 plus 2 passed; explicit activation only, failed writes retain OFF. |
| Static direct routes, authorization/media and current lifecycle/relationships | 78 passed. |
| Memory scope and retained native shutdown regressions | 2 passed. |
| Canonical Ubuntu Next/static visual comparisons | 36 passed without snapshot updates. Existing eleven images and 25px/0.1 tolerance retained; eight additional versioned captures represent intended product changes. Creation of those captures is recorded separately. |
| Frontend architecture/design | Passed: 14 features, 1157 raw colors in 35 files, 18 surfaces, 61 screenshot mappings, historical-plus-current 19 images. |

The [versioned visual report](release-readiness-visual-deltas-20261013.md) links the
current captures to the pre-existing implementation decisions. All actual source,
assertion, browser and new-file transitions are appended after the real repair
commit, retaining the original provenance prefix. These local results do not replace
required corrected-head hosted CI, final human platform review or merge-SHA main CI.

## Backend completion and current fixture contracts

The backend job for source `7bcc22bb` was cancelled at the existing 75-minute
limit, after 4752 completed progress entries in its actual 6323-node collection.
Ninety entries were failures/errors. Its identity artifact survived; no completed
JUnit report survived. This is an incomplete, failing run, not a whole-suite PASS.
The completed source/provenance/collection and privacy checks at `35c5f340` are
separate: protected/current 6327 nodes, frontend preservation 324, DCO and both
current-tree/unlimited-history custom and Gitleaks scans passed.

Current corrections preserve the implemented registration and admission contracts:
new `AgentCreate` inputs use LLM mode with the required description and synthetic
key, while legacy Local Bot ORM fixtures remain. Minimal current test schemas
include World's two deletion control tables, and injected HTTP runtimes use the
same temporary session factory for the actual deletion admission read. Read-count
assertions include admission while still checking the actor lock before target or
evidence access. Deferred bounded character labels and the retained legacy v1
selection protocol remain explicitly tested.

Historical fixtures seed current services only in disposable current databases,
then project the exact frozen predecessor tables and columns. Row counts, FK,
schema digest and sequence checks remain. Tests of the published individual
deltas retain their original versions; the production coordinator is expected to
reach the declared `SQLITE_SCHEMA_VERSION`. Social tests use its actual
copy-on-write promotion path before invoking current services and verify that
the original predecessor bytes remain unchanged. Fixture schema markers are
created exactly once, and image profile writes explicitly state key revision0.
Released manifests, DDL and historical data contracts remain unchanged.

An actual receipt-inspection defect compared a delivered v1 source (which omits
private author metadata) with the whole canonical dataclass. Unchanged material
was therefore incorrectly marked partial. The inspector now reuses the existing
`episode_source_payload` serializer for comparison. Current source access, status,
offsets, changed text and private-SNS exclusion remain enforced; canonical author
metadata is still private. Existing unchanged/changed/private-source regressions
exercise this behavior without changing their assertions.

The backend corpus now runs through four independent jobs. Each fixed runner
collects `tests` in full and partitions exact node IDs by SHA256 modulo4. No new
filter, skip, xfail, maxfail or timeout extension is introduced. Every setup,
call and teardown result is written to a bounded-schema progress journal, and a
final report is written only after pytest returns. The required `backend` job
requires successful preflight and all partitions, then verifies matching source,
checkout, Python, lock and collection identities plus exact, nonduplicated full
coverage. Failed setup/teardown, missing results, interruption or a missing job
cannot become aggregate success. Existing normal pytest skips are recorded
separately. Exact artifact allowlists retain only synthetic test reports.

The tradeoff is four runner/dependency/collection preparations and distributed
module fixtures, in exchange for finishing the unchanged corpus within the
existing per-job limit and retaining exact failure locations. Real pytest child
sessions, a teardown failure, missing/unexecuted reports and six damaged-workflow
cases are covered by focused tests; the combined CI policy/report/coverage
regressions passed46 cases. Required hosted full-corpus and target-OS execution
must still complete on the final corrected source head before review and merge.

The additional isolated migration/Social correction run passed24 cases, including
authenticated/failed vault upgrade, old receipt/sequence preservation, rollback,
both fresh and production-upgraded World-author paths and worker deadline cleanup.
These tests used a recorded dirty-source overlay over `35c5f340`; they are focused
precommit evidence. A broader related-file run and final committed-source gates
are tracked separately, and no in-progress run is counted as successful.

The broader 353-case overlay run completed with333 passed/6 existing skips,
9 failed/5 setup errors. Eight failures and five setup errors were the already
corrected duplicate-marker/old-Social-fixture cases above. The remaining timeout
case actually expired at `child_bootstrap`, before its intended `nn_query` fault.
The backend correctly reported the last observed stage. That synthetic test now
allows30 seconds for cold spawn/import and blocks its child for60 seconds, so the
same real deadline, last-stage, metadata, forced cleanup and no-late-success
assertions can test the intended stage. Product budgets and the 75-minute CI job
limits are unchanged. No retry-until-pass or relaxed assertion is introduced.
The corrected worker module passed21 cases on Windows and21 on isolated Linux;
the same three existing Vec1-dependent cases were skipped locally. Hosted CI
builds the pinned extension and is the separate native execution Gate.

The `4dd96051` hosted preflight completed dependency installation, native Vec1
build, schema materialization, full baseline collection and current/frozen
inventories, then exposed missing route-security metadata. Eleven newer OpenAPI
operations and one schema-hidden legacy World-media route were absent from the
explicit current inventory. Existing entries, endpoint ownership and access
classes are preserved; the twelve additions are classified from their actual
authentication and resource authorization. The World-media routes permit only
the already authorized visibility/member reads, protected resource operations
remain owner-only, and pure workflow analysis requires an authenticated session.
The full route/auth/object-ID and mutation-surface security assertions remain;
their exact current mutation count is149 with all four added POST/PATCH/DELETE
operations explicitly required. No runtime authentication or API scope changes.
The retained public-runtime surface test is also aligned to the actual227 paths
and282 operations, explicitly requiring all eleven additions while preserving
every existing private/retired-route denial. A related preflight/public-contract
run identified this stale count before the next hosted corpus execution.

The `af123e06` preflight passed, but its actual partition CLI collected only2323
items with377 import errors: a file-launched runner had `scripts/ci` on `sys.path`
instead of the backend directory supplied by `python -m pytest`. The runner now
adds only its verified backend working directory before collection. A real CLI
test creates an isolated Git/backend/app fixture, clears inherited PYTHONPATH and
runs all four original scripts against80 importing cases, then verifies exact
complete coverage. Product imports, test selection and failure handling are
unchanged; collection failure remains a failing result.

The same hosted head exposed a Comfy browser-test synchronization defect: the
analysis-complete status can precede the parent's reference-support update. The
test's uncheck operation could see a temporarily disabled, unchecked control and
return without an actual OFF selection, leaving the preference uninitialized.
The regression now requires the reference control to be enabled and checked
before unchecking, and asserts the saved OFF preference and unsaved appearance
and style. The existing product state and scoped late-result guards are retained.
No layout, translation, raw color, permission or provider-call changes.
The real CLI's first actual-corpus partition then reached495 passed/4 existing
skips before a fixture changed process cwd and exposed a relative progress-journal
path. CI report/JUnit/journal paths are now absolute under the verified backend
directory. The real CLI fixture changes cwd in every test and still requires
all four partitions' setup/call/teardown results and exact coverage, so this operational failure cannot
be hidden by a synthetic test that never changes directories.

The combined CLI/policy/report regressions passed47 cases. The unchanged product
frontend passed all20 repeated Next/static reference-OFF and late-profile cases,
then all56 related image-integration cases with the exact committed synthetic
PNG/JPEG/WebP fixtures. The first supplementary local image environment omitted
those three files and finished44 passed/12 failed with ENOENT; that environment
failure is retained separately, and no product patch or weakened assertion was
used to remove it. Final corrected-head hosted CI and human platform review are
still separate pending Gates.

The `af123e06` Windows installer build, clean-install and failure-recovery jobs
passed. Its direct supported-predecessor upgrade failed with exit42. A file-only
replay of the identical synthetic v1 builder reported
`world_activity_secret_authentication_failed`: the fixture stored a non-envelope
placeholder where the current migration correctly requires an authenticated
credential. The builder now uses the existing scoped local encryption helper
with its owned fixture secret. No process-secret/KMS fallback or migration change
is introduced. The verifier compares ciphertext, fingerprint and enabled state
with the digest-verified immutable predecessor, rather than expecting a literal
placeholder. It still rejects any target credential drift.

The related Windows module passed35 cases, preserving all31 frozen-predecessor
cases and adding three actual file-only v1/v29/v32 upgrades. Linux passed7 related
cases, including those upgrades plus verifier and owned-secret regressions. These
checks preserve the original DB/secret/media bytes and process settings, require
a healthy graph and current SQLite target, and reject an incorrect secret and
different target ciphertext even if it decrypts to the same synthetic value.
No executable or service was launched. The corrected-head real Windows NSIS
matrix remains a required hosted Gate before review/merge.

The exact `b1139f1a` hosted backend corpus completed all6350 cases:6261 passed,
66 existing skips and23 failures. All four downloaded reports share source,
checkout tree, Python and lock identities, and their unique union covers6350.
The original aggregate correctly rejects these failing reports. Frontend,
Windows Core/Host/advisory, migration, governance, local smoke, CodeQL and the
then-current v1-v28 native installer matrix passed. This is not whole-CI success.

The follow-up repair translates SQLAlchemy checkout pressure and SQLite queue
capacity into the Relationships outbox port at the concrete adapter. The worker
retains its lease/finalize rules and bounded backoff without importing SQLAlchemy
exceptions. Eight actual adapter/operation faults preserve their cause chains,
and a different error remains a different error. Current generated import and
runtime inventories classify actual owners rather than allowing a boundary bypass.

Synthetic startup fixtures now adopt both character ownership and the matching
World membership. Comfy tests require Partner-only secrets, reject a retired
server key, and retain write-only/revision/unverified-connection checks. Dashboard
queries remain equal for one and eight characters with three fixed erasure fences;
the additional guarded World-media endpoint and separate deletion router are
explicitly asserted. Current Studio, creation and support screen composition,
first-registration OFF, auth/runtime post loading and main-landmark ownership
replace stale text/topology expectations while retaining scope and access checks.
The new autonomy section marker is semantic only, with no visible copy or layout.

Every readable v1-v36 predecessor is now explicitly wired through fixture creation,
archive validation and the real hosted NSIS upgrade runner at unchanged time limits.
The synthetic schema retains v33 diagnostics at v33 and later, while old frozen
manifests and production forward migrations remain unchanged. New v33-v36 file-only
authenticated upgrades preserve original DB/secret/media and reject target drift.

Focused failed-node and new port/upgrade regressions passed43 cases. The broader
144-case related-file run completed143 passed/1 failed: the sole remaining issue
was a literal-only historical inventory reader rejecting a dynamic fixture-version
assignment. The supported versions are now an explicit36-version tuple, checked
against the actual readable registry, rather than changing that historical reader.
The subsequent P8-L-D inventory/matrix checks and four-case module rerun passed.
Frontend lint/type/ownership/design and backend import/
runtime contract checks passed. Final committed preservation/privacy checks,
expanded native matrix, full new-head CI and human review remain separate Gates.
