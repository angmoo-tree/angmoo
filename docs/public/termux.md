# Experimental ARM64 reuse with Termux

This adapter reuses the **same validated ARM64 backend and frontend images**.
Docker is not required on Android. PRoot-Distro imports each OCI filesystem
separately, preserving the backend Debian/Python and frontend Debian/Node bases.
It runs the existing app entrypoints; it does not install another app dependency
set, patch the images, or require editing ports or environment files.

**Release:** [Angmoo 0.1.0](https://github.com/angmoo-tree/angmoo/releases/tag/release-v0.1.0) is available.
Android support remains experimental. Linux ARM64 or QEMU checks do not certify
phone power management, background execution or performance.

On the tested Samsung Android 14 device, the system terminated a Termux child
process during screen-off use even with a partial wake lock and battery
optimization exclusion. These settings do not guarantee continuous operation.
This is a device-specific observation, not a universal Android memory limit.
Closing the browser does not itself stop the server; Android may still interrupt it.

## First install and start: two commands

Install Termux on a supported ARM64 Android device, then enter these two commands.
The second downloads the installer from the official versioned Release before
running it. A missing release never falls back to another version or main code.

```sh
pkg update && pkg install -y python curl proot
```

```sh
curl --fail --location --proto '=https' --proto-redir '=https' --max-time 120 -o "$HOME/install-angmoo.py" https://github.com/angmoo-tree/angmoo/releases/download/release-v0.1.0/install-termux.py && python "$HOME/install-angmoo.py"
```

The installer downloads the tools ZIP, checks `RELEASE-SHA256SUMS`, extracts it,
sets up host tools, installs the images and starts backend/frontend in order.
The release producer embeds the exact ZIP SHA-256 and size in the installer;
both that binding and the checksum entry must match before tools code runs.
Existing image architecture/source/version/digest checks, data preservation,
duplicate-process protection and port checks remain in the existing launcher.
A failed step prevents later steps. No shell startup files are edited.

The initial installer's trust source is the official GitHub Release HTTPS URL
above. Its own SHA-256 is also in `RELEASE-SHA256SUMS` for separate review and
verification. This is not release-signature verification or Android certification.

On success, open **http://127.0.0.1:3000**. For subsequent use, skip installation:
these explicit paths work without a separate PATH setup command.

```sh
~/.local/bin/angmoo start
~/.local/bin/angmoo status
~/.local/bin/angmoo stop
```

## Command registration in the development source

The command registration described here is **not included in the published
0.1.0 tools**. The explicit paths above remain valid for that release.

With reviewed tools containing `command_registration.py`, normal `sh setup.sh`
also registers `$PREFIX/bin/angmoo` as a link to the existing
`$HOME/.local/bin/angmoo` wrapper. After `Command ready: angmoo`, current and new
Termux shells can use `angmoo start`, `angmoo status` and `angmoo stop`. No alias
or shell startup-file edit is needed. Internal installation calls still use the
verified full path, and readiness is reported only after both services are ready.

For an already complete installation, run this from the reviewed **new tools**
directory to register only the command:

```sh
sh setup.sh --register-command-only
```

This mode does not run pkg/pip, replace tool or image files, restart services, or
read application data, keys or logs. It uses a private setup lock to coordinate
installers. Do not rerun the whole first-install bootstrap merely to register an
existing custom-home installation. Keep its existing home when using commands:

```sh
angmoo --home "$HOME/.local/share/angmoo-custom" status
```

An existing link to the same wrapper is reused. A different command, modified
wrapper, unsafe prefix, or command shadowing earlier in PATH is an error; setup
does not overwrite it. An incomplete installation cannot use register-only.
`setup_busy` means another setup owns the lock. Let it finish before retrying.
Inspect the conflicting command before making changes; the original full path
remains available when that installation is intact. Native Termux detection is
required for prefix registration; a non-Termux validation environment retains
the full-path workflow. No power-management setting is changed.

## Manual setup and controlled validation

To review the individual steps, download `angmoo-termux-tools.zip`
from the official `angmoo-tree/angmoo` release and verify its entry in
`RELEASE-SHA256SUMS`. Extract it into Termux private storage, then perform the
one-time host-tool setup from that directory:

```sh
sh setup.sh
export PATH="$HOME/.local/bin:$PATH"
```

For published 0.1.0, this export affects only the current shell. Tools with the
verified prefix registration above do not need it.

Setup installs the platform's Python/PRoot if missing and the hash-pinned
PRoot-Distro 5.10.0 wheel in a private virtual environment. No root or Docker
daemon is needed. Keep its licenses and versioned upstream source notices.
Installation and each later start are one command each:

```sh
angmoo install --release 0.1.0
angmoo start
```

Open **http://127.0.0.1:3000** in the Android browser. Backend uses loopback 8080.
If another process owns either port, start refuses to adopt or kill that process.
`angmoo status` and `angmoo diagnostics` read safe identity/state only. Stop and
restart with `angmoo stop` / `angmoo restart`; backend may take up to 200 seconds
to drain. These commands preserve data. Do not kill Termux during a write.

Host state and data live under `~/.local/share/angmoo`, mode 0700, outside either
rootfs. Only backend receives the data mount. Do not move this directory to
shared Android storage. Neither credentials nor data go into the images.
Keep both service payloads on the same version/source. A failed import does not
select the partial pair or erase the prior install. If owned processes survive an interrupted session, the launcher refuses to
start a second backend and reports the state through diagnostics.

## Local candidate validation

Maintainers can use `install --candidate-manifest` with a separate `--home`
for an explicitly validated ARM64 backend/frontend pair. Do not mix candidate
and release data roots or change image validation to make a test start.
See [candidate import](../operations/release-candidate-import.md) for identity
checks. Local or emulated validation is not a physical-phone certification.

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
