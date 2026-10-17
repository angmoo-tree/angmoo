# Experimental ARM64 reuse with Termux

This adapter reuses the **same validated ARM64 backend and frontend images**.
Docker is not required on Android. PRoot-Distro imports each OCI filesystem
separately, preserving the backend Debian/Python and frontend Debian/Node bases.
It runs the existing app entrypoints; it does not install another app dependency
set, patch the images, or require editing ports or environment files.

**Publication boundary:** the commands below require an actual published
`release-v0.1.0`. P1/P2 implementation does not publish it. Linux ARM64/QEMU
results are not evidence that Android sleep, Doze, or background activity works.
Physical-device certification remains P4; until recorded, Android is experimental.

After installing a current supported Termux, download `angmoo-termux-tools.zip`
from the official `angmoo-tree/angmoo` release and verify its entry in
`RELEASE-SHA256SUMS`. Extract it into Termux private storage, then perform the
one-time host-tool setup from that directory:

```sh
sh setup.sh
export PATH="$HOME/.local/bin:$PATH"
```

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
select the partial pair or erase the prior install. Interrupted sessions with
surviving owned processes refuse a second backend; diagnostics reports the state.

For P1/P4 controlled validation before publication, copy the validated candidate
manifest and both ARM64 `.oci.tar` files to private Linux storage, then use:

```sh
angmoo --home "$HOME/.local/share/angmoo-rehearsal" install --manifest /absolute/candidate.json
angmoo --home "$HOME/.local/share/angmoo-rehearsal" start
angmoo --home "$HOME/.local/share/angmoo-rehearsal" status
angmoo --home "$HOME/.local/share/angmoo-rehearsal" stop
angmoo --home "$HOME/.local/share/angmoo-rehearsal" restart
```

The manifest must contain the complete pair and exact hashes. Record source,
archive/config/diff-ID identity, PRoot version, host architecture, QEMU or native,
start/stop times, app readiness, restart data preservation, and stale/port/failure
tests. Physical Android T01–T05/T11 additionally records setup command count,
permission/storage behavior, foreground SNS/Chat, device sleep and recovery.
Do not mark these physical checks passed from a Linux container rehearsal.

Local OCI import flattens only the index into a temporary transport archive for
PRoot-Distro 5.10.0. Image manifests, compressed layers, configuration and
SBOM/provenance blobs keep their original hashes; the original candidate stays
unchanged. Registry installation already selects the exact execution digest.

The initial Linux rehearsal imported both ARM64 payloads, but Debian's PRoot
5.1.0 with QEMU could create a file through the bind while `statx`/write-access
checks reported that path unavailable. App start correctly refused the data
root. This is not an Android PASS: startup, browser use and restart still require
P4 on a real supported Termux device. Do not bypass the write-access check or
change user-data permissions to force this rehearsal to pass.
