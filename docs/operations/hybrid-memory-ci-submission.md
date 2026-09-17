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
- Full backend with native Vec1, provenance, final commit checks and remote CI
  remain in progress. These partial results are not a final submission PASS.

No paid provider calls are added by this CI preparation. Windows artifacts mean
MSI and NSIS installer EXE in GitHub Actions, not GitHub Releases or GHCR publication.
