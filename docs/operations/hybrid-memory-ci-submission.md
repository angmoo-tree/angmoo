# Hybrid and episode memory submission validation

Status: local CI preparation in progress. Remote CI, merge and Windows installer
artifact verification are separate gates and are not yet complete.

## Scope

The change introduces scoped FTS5/Vec1 flat retrieval and RRF, episode/source/thought
memory, and manual/scheduled/shutdown consolidation. SQLite remains canonical.
The accepted defaults are `social_hybrid`, `group_or_v1`, `thought_v1`, and
`episode_v1` generation/recall. Thoughts are capped at 280 characters. Chat
consolidation uses up to 50 new turns plus 5 context turns. Historical records
remain readable without inventing old thoughts. Embedded schema advances to v14.

F1–F4 retain user acceptance with their original limits: F1 covers one real SNS
reason response; F2 contains accepted known response-quality failures; F3 uses
perceived latency rather than repeated browser timing; F4 establishes concurrent
completion, not a resource or load benchmark. Public evidence excludes raw user
questions, stored thoughts, credentials and operational databases.

## CI corrections

- Removed the routine-post → LLM adapter reverse dependency by placing pure
  activity output transformations in their shared contract owner. The previous
  import remains a compatibility path; production consumers use the owner.
- Extracted the successful-action subjective-record validator from the Today SNS
  assembler, allowing memory hydration to reuse it without the social runtime
  composition cycle. Validation conditions and original caller sessions remain.
- Preserved the lightweight spawned-search entrypoint; server initialization
  imports were not restored to module scope.
- Registered five owner-scoped routes in the source security inventory and
  regenerated the public inventory (204 operations).
- Froze the v10 memory inventory at its original digest and added a successor
  covering current v14 hybrid/episode/consolidation sources. The existing CI
  command verifies both. Historical manifests are unchanged.
- Updated deterministic fixtures for thought JSON, final-action persistence,
  schema v14/115 tables and diagnostics export v2. Equal-due batch jobs may be
  claimed in either ID order; batch sizes and provider-call counts remain checked.
- Core CI explicitly builds the pinned Vec1 extension for native hybrid tests.
- Factory preservation continues to reject arbitrary changes; lifecycle signature
  evolution requires the existing exact committed before/after product proof.
- Product-change provenance reads each immutable Git object once per validation,
  while retaining all source, ancestry and before/after checks.

## Local evidence so far

- Initial focused suite: 1,584 passed, 15 failed, 27 skipped. Failures and their
  corrections are retained in local diagnostic artifacts.
- Corrected affected subset: 198 passed; new inventory/output-contract tests: 7 passed.
- Browser smoke: 23 passed, one diagnostics-version expectation failed, ten
  opt-in real-provider scenarios skipped. The corrected diagnostics test passed.
- Frontend lint, typecheck, Next build and static build passed.
- Browser continuity: 29 passed and 10 opt-in real-provider cases skipped;
  static continuity: 71 passed; lifecycle: 2 passed; pinned Linux visual: 36 passed.
- Frontend preservation passed for 324 source files. Dependency vulnerability,
  license and notice checks passed. Gitleaks candidate and ancestor-history scans
  found no leaks; the repository scanner found zero fatal items in tree/history
  scans (existing binary image audit notices remain distinct).
- Current architecture, frontend architecture/design, route inventory, schema
  migration, OSS boundary, CI policy, secret metadata, release/launcher/installer
  contracts and license-policy checks passed.
- Full backend with native Vec1: 3,668 passed, 20 failed, 28 skipped. The 20
  failures identified stale packaging/security expectations and incomplete
  predecessor fixture construction, not a passing full-suite result.
- Corrected packaging/security subset: 80 passed. Supported Windows predecessor
  fixtures now cover v1 through v13 before upgrade to v14; frozen historical
  digests remain checked. The historical 89-migration conversion inventory is
  preserved while current SQL/topology inventories include later additions.
- Native retrieval scope tests passed all six policy/deletion/isolation cases.
- Preservation passed for all 3,716 then-current protected test lineages; final
  packaging additions and remote CI are verified separately before completion.

No paid provider calls are added by this CI preparation. Windows artifacts mean
MSI and NSIS installer EXE in GitHub Actions, not GitHub Releases or GHCR publication.

## Remote submission and security triage

PR #328 initially failed `oss-boundary` because the deferred-runtime inventory
did not yet include the exact historical contract fragments in the new provenance
manifest. Regenerating the inventory records that occurrence without removing or
ignoring the marker. Other remote results remain separately tracked.

The initial container gate also rejected 13 fixable OS findings in the pinned
Debian base. The backend Dockerfile now upgrades gzip, PCRE2, system SQLite and
perl-base alongside its existing security upgrades, and verifies minimum patched
versions. Scanner severity and unfixed/secret policies are unchanged.

GitHub reported GHSA-2883-xcg3-v3hh in development-only ESLint's `js-yaml`.
The existing v4 override is advanced from 4.3.1 to patched 4.3.2; runtime frontend
dependencies are unchanged. This finding was outside the earlier production-only
audit and must not be described as a clean all-dependency audit before correction.

The three existing GHSA-wrw7-89jp-8q8g `glib` 0.18.5 alerts concern the desktop,
Defender experiment and native-runtime spike lockfiles. `cargo tree --locked
--target x86_64-pc-windows-msvc -i glib` shows no Windows dependency path. They
remain open upstream/Unix dependency follow-ups; this Windows installer scope does
not certify Unix GTK runtime safety or dismiss those alerts. Container backend
and frontend do not build these Rust desktop targets.

On the second CI attempt, backend image scanning passed. Frontend scanning then
found three advisories in its Debian 12 PCRE2 package; its runtime stage now
requires the patched 10.42-1+deb12u1 or later package. The second Gitleaks failure
identified four exact Git blob lines, not credentials. Each was checked against
its recorded introduction commit and blob object. Narrow path-and-whole-line
exceptions preserve all other detection. Candidate scanning and the complete
817-commit ancestor scan then passed with no leaks.

The third full hosted backend run completed with 3,690 passed, one failed and
28 explicitly gated skips. Its single failure was the generated Dockerfile hash
inventory after the OS security patches. Updating those two digests preserves
the historical inventory contents; all eight related ER0 tests passed locally.
The final submission is still checked by the complete hosted suite.
