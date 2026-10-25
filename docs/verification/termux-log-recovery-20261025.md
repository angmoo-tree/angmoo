# Termux interrupted log recovery verification

Date: 2026-10-25. Product branch: `fix/termux-log-session-recovery`, based on
`1361b056bdc9a5292e7652038ef0a9412220273c`. This report covers the host fix
and 0.1.3 version alignment; it is not a publication or phone upgrade receipt.

## Behavior and preservation

The legacy reproduction has four log sessions, two without an end timestamp,
and no surviving runtime. The old code raises `log_retention_active_session`.
The new startup holds the existing home flock, checks process identities and
a bounded same-UID launch/home/session/log-descriptor snapshot, then marks only
proven inactive unfinished sessions `interrupted`. Historical end time stays
unknown, original failures are retained and capture completeness stays false.
Alive or unverifiable ownership prevents a new server. Recovery never kills
processes and never opens the product database.

The four-session/64 MiB policy is unchanged. Private validated paths, links,
UIDs and known file types remain required. Atomic metadata and a bounded
retention receipt permit recovery after interrupted renames/deletions or
directory creation. Cleanup failures do not acquire invented session or
service end timestamps. Installation success and subsequent startup failure
are reported separately. Old and new release tool profiles remain explicit.

## Local evidence

- Linux, pinned host-tool dependency, actual procfs/flock/processes: 80 Termux
  tests pass. Includes SIGKILL, surviving descendants, PID reuse, boot changes,
  unknown observations, handoff gaps, atomic-write failures, partial retention,
  hardlink refusal and unchanged byte limits.
- Native Termux on an Android 14 ARM64 phone: 22 tests pass, one hardlink-fixture
  test is unsupported because this Python has no `os.link`; Android also
  denied a native `ln` fixture. The actual hardlink guard passes on Linux.
  This limitation is not a claim of native hardlink coverage.
- The final native sample checks four same-UID processes and 34 descriptors
  in 7.16 ms. Thread count remains 1; no data directory is created. These are
  a bounded synthetic sample, not phone-performance guarantees.
- All 36 checked original installed launcher/state/log files remain byte
  identical after the native tests. Only a separate diagnostic source copy
  and temporary synthetic homes/processes were used.
- Focused backend/product/release-profile contracts: 48 tests pass. Current
  embedded-runtime inventory regressions: 8 pass. Public-doc contracts: 17 pass.
- Public-document links/content check, release-tag/version, local runtime,
  container release, desktop installer and Windows launcher contracts pass.
  Windows local smoke uses isolated data and fake Docker, without starting
  the installed application. Frontend runtime-identity tests pass.
- Architecture boundaries, architecture inventory and deferred-runtime
  inventory checks pass. Current generated ER0 hashes were refreshed with
  the standard generator; historical fixtures are unchanged.
- Lock changes update only the Angmoo self-package version to 0.1.3, not
  third-party dependency versions. No schema/data-version change is required.

The first hosted CI run encountered a different runner-owned process whose
`/proc/<pid>/environ` was inaccessible. Recovery correctly refused to prove
inactivity, so fixtures expecting an otherwise empty host failed. The hosted
lifecycle step now uses a private PID/mount/procfs namespace and immediately
drops back to the ordinary runner UID. Actual Linux processes, the full test
suite and explicit unreadable-process rejection remain exercised; production
recovery is unchanged. Namespace teardown kills remaining synthetic children.

Local evidence directory (not a release asset):
`.task-output/termux-log-session-recovery-20261025/run-01` in the parent
workspace. `linux-06.log`, `native-07.log` and their source-hash receipts are
the final host results; earlier failed fixture attempts are retained.

## Not performed by these checks

No real Chat, SNS activity, embedding or provider request was generated.
The phone's installed images, original sessions, settings and data were not
replaced or repaired. No installed Windows application was launched. Native
synthetic checks do not certify Android background operation. PR/main CI,
exact-source candidates, Windows original-EXE acceptance and publication
must be recorded separately after they actually complete.
