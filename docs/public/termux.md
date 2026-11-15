# Run Angmoo with ARM64 Termux / PRoot

> **0.1.5 support policy:** Docker (Linux amd64/ARM64, including Windows Docker Desktop) and experimental Termux ARM64 remain supported. New Windows native installers and official native support end with 0.1.5. Existing EXEs, source and manual workflows are retained. No Windows-native-to-Docker data migration tool is provided: Docker starts a separate empty environment. Keep your old installation and backup if you need its data. Existing Docker/Termux 0.1.4 users update with their data preserved; do not run the SQLite migration again.

English | [한국어](termux.ko.md)

Version 0.1.5 reuses the validated ARM64 frontend, backend and PostgreSQL image
filesystems through PRoot. No Docker daemon is needed on Android. The commands below use the published 0.1.5 release. Android support remains experimental:
Linux/QEMU success does not certify screen-off/background behavior. A prior
Samsung Android 14 observation included child-process termination despite a
wake lock and battery-optimization exclusion.

## First installation

Use private Termux storage on an ARM64 device without an existing Angmoo installation.
Existing 0.1.4 users should go to **Update while keeping the same data home** below.
Continue to the next command only after the previous one succeeds.

```sh
pkg update && pkg install -y python curl proot clang make libandroid-shmem
curl --fail --location --proto '=https' --proto-redir '=https' --max-time 120 -o "$HOME/install-angmoo.py" https://github.com/angmoo-tree/angmoo/releases/download/release-v0.1.5/install-termux.py
python "$HOME/install-angmoo.py"
```

The installer verifies version/source/digests and starts all three services.
Its pinned tools ZIP hash/size and `RELEASE-SHA256SUMS` must agree before code
runs. The initial installer is trusted through the official HTTPS Release URL;
this is not separate release-signature verification or Android certification.
Open http://127.0.0.1:3000 when ready.

```sh
angmoo start
angmoo status
angmoo diagnostics
angmoo stop
angmoo restart
```

Startup orders PostgreSQL readiness, backend, then frontend; shutdown reverses
that order. App ports default to 8080/3000; DB uses loopback 5432. A foreign
listener is not adopted or killed. Inspect logs on failure; do not delete data.

## Update while keeping the same data home

### Update the 0.1.4 installation you normally run with `angmoo start`

Use the **same 0.1.5 installer as a new installation**. It preserves the already selected data home and updates the launcher and three images. A PostgreSQL home selected by the 0.1.3 migration remains selected. Do not run `migrate` again.

1. Make a [complete backup](postgresql-backup.md) first. Keep the existing home, media, secrets and recovery journals.
2. Stop the current services in Termux. Do not continue if this fails.

```sh
angmoo stop
```

3. Copy and run this single line. The installer **starts Angmoo automatically** after installation.

```sh
curl --fail --location --proto '=https' --proto-redir '=https' --max-time 120 -o "$HOME/install-angmoo.py" https://github.com/angmoo-tree/angmoo/releases/download/release-v0.1.5/install-termux.py && python "$HOME/install-angmoo.py"
```

4. Wait for `Ready` and the address, then open the same address (default http://127.0.0.1:3000). Check your Worlds, characters, memories and conversations. Use `angmoo status` to check status. For later sessions, use `angmoo start` and `angmoo stop`.

`Installed; run angmoo start.` means **image installation is complete**, not that all services are ready. The installer above continues to startup automatically; wait for `Ready` or an explicit error. Download, extraction and service preparation times vary by device and data. Do not run a second installer in parallel. On failure, use `angmoo status` and `angmoo diagnostics`; do not delete data.

### If you explicitly pass `--home` on every command

Do not run the default installer above unchanged. Back up your existing custom home, then follow these steps.

1. Stop it with `angmoo --home /PRIVATE/EXISTING/HOME stop`. Replace `/PRIVATE/EXISTING/HOME` with your actual existing path and quote paths containing spaces.
2. Download `angmoo-termux-tools.zip` from the [0.1.5 Release](https://github.com/angmoo-tree/angmoo/releases/tag/release-v0.1.5) and compare its SHA-256 with its entry in `RELEASE-SHA256SUMS`. If it matches, extract it into a new folder and run `sh setup.sh` there to update only the tools.
3. Pass the same existing home to every command. Check that each succeeds before continuing.

```sh
angmoo --home /PRIVATE/EXISTING/HOME install --release 0.1.5
angmoo --home /PRIVATE/EXISTING/HOME start
angmoo --home /PRIVATE/EXISTING/HOME status
```

The standalone `angmoo install` command ends at `Installed; run angmoo start.`, so the following `start` command is required. Once ready, check your data at the existing browser address.

## Existing 0.1.3 data

Use the historical **0.1.4** tools ZIP and checksum, run `sh setup.sh` to update the
launcher, then:

```sh
angmoo migrate --release 0.1.4 --language en
angmoo start
```

The original stays intact. Backup, conversion and verification use a sibling
`<old-home>-postgresql`; selection changes only after success. Keep the same
explicit `--home` for a custom installation. Follow
[migration, resume and rollback](postgresql-migration.md). A normal `install`
does not overwrite SQLite data. Private PG experiments are not supported inputs.

## Host tools and data

PRoot-Distro 5.10.0 is hash-pinned in a private Python environment. Play Store
Termux builds a pinned upstream PRoot with the SysV shared-memory helper in the
installation's private tools directory. It does not replace packaged PRoot,
global settings or app-image files. Source/patch/binary hashes are recorded in
`records/proot-build.json`. Short private IPC scratch directories under
`.cache/angmoo-pg` have installation ownership markers; they are not databases.

PGDATA, media, secrets and retained-result journals stay outside image rootfs.
Keep the home private (0700), not on `/sdcard`. Follow the
[complete backup/restore guide](postgresql-backup.md); a DB file alone is not
enough. Do not attach an older image to new PG data or remove originals/backups
before verification.

## Registration and candidate validation

`setup.sh` registers `angmoo` through the existing wrapper without changing
shell startup files. From reviewed new tools, use `sh setup.sh --register-command-only`
only to register an already complete installation. A conflicting command or
modified wrapper is not overwritten. Direct migration from 0.1.0 is not supported.

Maintainers can use `install --candidate-manifest` with a separate `--home`
for three same-source candidates. Keep local checks, hosted CI and physical
device observations distinct.

## Saved service logs

Angmoo's fixed terminal instructions are in English, regardless of the web
language. The web UI and this installation guide remain available in English
and Korean. Original service output, external tool messages and user file names
are preserved with the existing redaction rules.

Each new start automatically uses `basic` logging. To temporarily include safe
service diagnostics, choose the mode before starting:

```sh
~/.local/bin/angmoo start --log-mode detailed --log-duration 15m
~/.local/bin/angmoo restart --log-mode detailed --log-duration 15m
```

Detailed mode defaults to 15 minutes and accepts whole-minute durations from `1m` to `60m`.
Startup time counts toward that interval. It returns to `basic` when the duration expires, without a restart;
the next launch also defaults to basic. Invalid restart options are rejected
before stopping the current services. `start` never changes an already running
session. This option does not enable Chat/SNS capture or memory diagnostics.

Basic retains startup/shutdown, warnings, failures and recovery. Detailed adds
allowlisted access categories and worker/lease/proxy summaries, never request
bodies, query strings, keys, SQL parameters or global DEBUG. `status` and
`diagnostics` separate the requested policy, UTC-based effective-mode estimate
and each service's acknowledgement. A lazy frontend or old image can remain
unconfirmed; that is not a health failure. Each service also enforces its own
one-way monotonic expiry, which the host's UTC estimate cannot directly observe.

The two capture threads block while idle and wake on output or lifecycle events.
Only dirty files are flushed, at most one second after the first pending write.
The supervisor's process checks and an explicitly opened `logs --follow` viewer
remain separate costs. These changes do not establish phone battery usage.

`start` runs services in the background. View their saved output with:

```sh
angmoo logs --service all --tail 200
angmoo logs --service backend --follow
angmoo diagnostics
angmoo logs --session <launch-id> --service frontend
```

`Ctrl+C` stops only the log viewer. Failed launches retain the first failed service,
phase, UTC observation time, safe original error and observed exit code in
`logs/<launch-id>/session.json`. The exit code is that of the PRoot command; it does
not alone prove a guest crash or Android OOM. Readiness probe failures and cleanup
failures are separate. `diagnostics` also reports bootstrap capture gaps.

Logs stay in private storage (directory 0700, files 0600). Sensitive fields and
recognizable credentials are redacted before writing. Inspect before sharing:
application output can still contain personal text. Backend/frontend each retain
three 2 MiB segments; supervisor/bootstrap each retain two 1 MiB segments. At most
four sessions and 64 MiB are retained. Rotation, oversized lines, queue overflow
and disk errors are reported as evidence gaps, never as complete capture.
Viewing logs requires no running service, installed payload or product DB access.

If Android or a forced shutdown leaves a log session without an end record,
the next `angmoo start` checks the previous processes under the installation's
execution lock. When they are confirmed gone, it records an interrupted session
and continues starting Angmoo. It does not invent an end time or claim complete
log capture. The existing four-session retention limit still applies; completed
and verified interrupted sessions can eventually be removed by that policy.
Keep a separate copy of logs you need for a diagnosis.

If a previous process is alive or cannot be checked, a second server is not
started. Use `angmoo diagnostics` and keep the existing logs and data. Do not
delete log folders or reset application data to get past this check. Log cleanup
interrupted during a rename or deletion is rechecked on the next start. Older
launchers do not understand recovered interrupted sessions; downgrading is not
a recovery procedure.

`installation_complete_start_failed` means image installation succeeded but
automatic startup failed. Read the preceding error and run `angmoo diagnostics`;
after resolving that cause, retry `angmoo start` with the same data home.
Repeating downloads or deleting characters and API keys is not required.
