# L3.5 World Package v1 closeout evidence

Status: **PR G LOCAL TECH, SECURITY, CLEAN-CLONE PASS / PR G MERGED / POST-PR-G RUNTIME HOTFIX LOCAL TECH PASS / HOSTED, USER, MERGE GATES PENDING** (Hosted code, Tauri, and release-candidate jobs passed; installed-runtime re-run remains pending.)

Tracking:

- Public Issue: `#170`
- branch: `test/l3-5-world-package-closeout`
- baseline: PR F merge commit `e264c8641419a69321182c0179fc8be8ffda9767`
- public Release, Nest upload, promotion, and merge remain separate approvals

Post-PR-G runtime hotfix tracking:

- Public Issue: `#172`
- branch: `fix/l3-5-world-package-runtime-closeout`
- baseline: PR G merge commit `a6d4d699fd2aabe2620e0f8544d4d7b4b2348bf9`
- Host Tauri and installed release-candidate user gates remain pending

## Closeout contract

PR G does not introduce another package format or persistence path. It composes
the PR A-F contracts into one bounded release-candidate proof:

```text
source runtime root
  -> deterministic portable-seed export
  -> final-artifact exclusion scan
  -> untrusted staging and preview
  -> caller-confirmed atomic import
  -> target Device Home registration
  -> target-only evolution and restart
```

The source and target roots are isolated. The source fixture contains synthetic
owner IDs, database IDs, credential and APP_SECRET markers, post/comment text,
memory, P2/P3/P4 state, relationship evidence, and LadybugDB/runtime markers.
The final `.angmoo-world` is scanned by filename allow-list, forbidden JSON key,
and synthetic-value byte search. Import must create fresh local IDs, exactly one
Device Home World, portable autonomous character seeds, and zero runtime rows.
Changing the target after commit must not modify the source database or package.

## Automated evidence matrix

| Area | Required proof |
|---|---|
| Format and deterministic export | checked schemas, canonical JSON, stable archive bytes, managed assets only |
| Archive security | traversal/absolute/drive/UNC/backslash, normalized duplicate, links/device entries, encryption, nesting, bomb and size limits, malformed JSON and images, MIME/polyglot cases |
| Exclusion | local IDs, owner/credentials/secrets, social history, P2/P3/P4, relationship/LadybugDB, scheduler/projector markers absent |
| Preview | bounded staging, no canonical writes, exact digest/token/owner/expiry binding, collision plan |
| Commit | one caller-owned transaction, managed-media journal, idempotency, retry, concurrency, ambiguous-result recovery |
| Failure injection | staging, validation, normalize, insert/flush, media promotion, commit/marker, restart leave old canonical and media intact |
| Independent target | new local IDs, runtime rows zero, Device Home registration, target-only update persists after restart, source unchanged |
| Runtime packaging | clean-clone Docker gate, contributor stack, Windows Host Tauri contract, installer release-candidate and installed-runtime smoke |
| Privacy reporting | public guide forbids real packages in public issues/PRs/logs and points security cases to private reporting |

The required workflow lists the representative World Package suite explicitly
so future test-file or job reorganization cannot silently drop closeout
coverage. The container clean-clone gate continues to use a unique Compose
project and fixture volume and removes only that fixture in `finally`.

## Local verification evidence

- World Package PR A-G representative suite: `72 passed`
- full backend suite: `1365 passed, 20 skipped`
- architecture and representative World Package boundary suite: `55 passed`
- frontend typecheck, lint, and static build: PASS
- Docker contributor source-to-target closeout: `2 passed`
- isolated production-image Browser Run smoke: PASS with two services, stable
  SQLite write/restart, LadybugDB/scheduler/projector ready, provider calls
  `0`, and stable APP_SECRET digest
- temporary clean-clone fixture containers and volume: removed in cleanup

These results establish the local Gate only. Hosted Windows and Linux jobs,
the human source-to-target release-candidate scenario, merge, and any public
Release remain separately gated.

## Post-PR-G runtime hardening

The catch-all Next.js backend proxy forwards World Package capability headers
only for the exact export/import route and HTTP-method pairs that own them.
Tokens are shape-validated, delivery mode is allow-listed, malformed capability
headers fail with a stable `400` response, and unrelated backend routes cannot
receive those headers. A route-level smoke test exercises this policy through
the actual Next.js handler in Core CI.

If delivery or discard compensation fails, the UI keeps the pending operation
visible and requires a successful cleanup retry before starting another
delivery. Process-owned export and import staging directories are discarded on
backend startup; canonical World data and the Docker named volume are not
deleted as recovery mechanisms.

The Windows NSIS candidate now replaces only `%LOCALAPPDATA%\Angmoo\app` as a
transactional payload. It asks an installed runtime to close normally, stages
the prior app as a rollback candidate, installs the new host and sidecar, and
verifies their candidate SHA-256 manifest before accepting the replacement.
Failure restores the prior app while leaving canonical, graph, media, secrets,
runtime, logs, and WebView data outside the payload transaction. Sidecar startup
fatal output is restricted to stable diagnostic codes rather than arbitrary
exception text or local paths.

The first Hosted installer audit exposed two packaging-only gaps in sequence.
The supply-chain inventory was tightened to recognize only the exact
installer-owned app rollback paths and to require reparse-point validation
before deletion. The subsequent installed-runtime smoke then timed out during
silent NSIS installation. Extraction of that exact candidate proved that the
embedded manifest's sidecar digest matched the packaged sidecar while its host
digest did not match the packaged host. The manifest had been generated by
`beforeBundleCommand`, before Tauri completed the final host link.

The manifest is therefore generated during NSIS compilation, where
`MAINBINARYSRCPATH` names the exact host consumed by the following `File`
directive. The sidecar and destination manifest paths are passed explicitly.
Installer preflight or payload-verification failure remains interactive for a
normal user install, but silent CI mode now exits with a stable non-zero code
instead of waiting on a message box. A locally rebuilt NSIS candidate was
extracted and proved exact host and sidecar digest parity. The Hosted
installed-runtime smoke must still pass on the revised Draft PR head before the
Hosted Gate is closed.

## Human release-candidate scenario

The final user Gate uses synthetic data only:

1. In the source runtime, export a fixture World with autonomous seed content.
2. Choose a Save As destination and verify one `.angmoo-world` artifact.
3. In an isolated target runtime, select the artifact and inspect preview,
   license, characters, warnings, digest, and collision plan.
4. Commit once and verify exactly one new Device Home icon.
5. Verify owner-controlled characters, credentials, posts/comments, memory,
   P2/P3/P4 history, and relationships were not transferred.
6. Modify or use the target World, restart, and verify the target persists while
   the source remains unchanged.
7. Verify cancellation, invalid package, and repeated commit paths do not leave
   partial Worlds, media, or staging artifacts.

TECH PASS can be recorded after the focused and full suites pass. HOSTED PASS,
USER EXPORT/IMPORT/INDEPENDENT-RUNTIME PASS, merge SHA, and L3.5 PASS are
recorded only after their respective evidence exists.
