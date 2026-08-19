# L3-ER1 LadybugDB and Tauri native compatibility evidence

- Issue: [#101](https://github.com/angmoo-tree/angmoo/issues/101)
- Branch: `spike/l3-er1-native-runtime`
- Baseline: `a46888c98f7dfc4700f5e0d5ec9632b8de558578`
- Date: 2026-08-19
- Draft PR: [#102](https://github.com/angmoo-tree/angmoo/pull/102)
- First fully green proof head: `932caf60084d5046faa52eb8cb46a9b60f9b598f`
- Status: local and Hosted Windows technical proof PASS; user Go/No-Go and Ready/merge approval remain pending

## Frozen toolchain

| Component | Pinned value |
|---|---:|
| CPython | 3.13.12, uv-managed Windows x86-64 |
| LadybugDB Python package | 0.19.1 |
| PyInstaller | 6.16.0 |
| Rust | 1.97.1 MSVC |
| Tauri CLI | 2.11.4 |
| Tauri Rust crate | 2.11.5 |

The current Angmoo Docker backend remains Python 3.13. This spike does not
change the production runtime, storage adapters, API routes, Docker services,
or release defaults.

The compatibility gate deliberately pins patch release 3.13.12. LadybugDB
0.19.1 does publish an official `cp313-win_amd64` wheel; the pin is not a
workaround for missing Python 3.13 support. It makes the native DLL loading
environment reproducible and fails before the graph probe unless the bundled
`ladybug._lbug` PyBind module imports successfully.

## LadybugDB result

The executable probe passed all required synthetic contracts on Windows x64:

- database create, close, reopen, and idempotent `MERGE`;
- exclusive writer rejection and five serialized reads;
- World-scoped direct evidence lookup;
- bounded one-to-three-hop traversal;
- World isolation with zero cross-World rows;
- a physical database path containing Korean characters and spaces.

LadybugDB 0.19.1 rejected a database path containing characters outside the
active Windows ANSI code page. Its official CPython 3.13 Windows wheel
nevertheless imported and ran
through the default bundled PyBind native module without a machine-wide
LadybugDB, OpenSSL, JVM, or C API shared-library installation. The earlier C
API-path failure was not representative of the default wheel runtime and is
not used by this spike.

The accepted spike workaround is process-scoped: the dedicated LadybugDB
sidecar maps the intended Unicode application-data directory to one unused
temporary ASCII drive letter, gives the native library that ASCII path, and
removes the mapping during graceful or parent-death shutdown. The graph file
never leaves the canonical user-data directory. This is not permitted inside
a shared multi-purpose process and is not a machine-wide LadybugDB install.

## Tauri and sidecar result

The local release build produced and executed a Tauri v2 Windows application
with a PyInstaller-packaged FastAPI/LadybugDB sidecar. The proof verified:

- a dynamic loopback-only port;
- an ephemeral per-launch token;
- unauthenticated health rejection;
- authenticated health and embedded graph access;
- duplicate writer refusal;
- authenticated graceful shutdown;
- parent-death orphan cleanup;
- no persisted token in evidence.

Local baseline measurements:

| Artifact or metric | Result |
|---|---:|
| packaged sidecar | 21,273,109 bytes |
| Tauri executable | 11,005,440 bytes |
| NSIS installer | 23,589,854 bytes |
| Tauri-to-sidecar proof startup | 5,340 ms |
| Microsoft Defender custom scan | PASS, no threats |

The exact artifact hashes and the deterministic SPDX 2.3 dependency inventory
are generated outside Git by `run-spike.ps1`. They must be regenerated on a
clean Windows runner; generated binaries and user-specific absolute paths are
not committed.

## Hosted Windows evidence

Draft PR #102 reproduced the pinned proof on GitHub-hosted Windows at head
`932caf60084d5046faa52eb8cb46a9b60f9b598f`:

- `windows-native`: PASS in 6 minutes 45 seconds
  ([run 32265603554](https://github.com/angmoo-tree/angmoo/actions/runs/32265603554/job/96109213488));
- the official `ladybug-0.19.1-cp313-cp313-win_amd64.whl` imported through
  `ladybug._lbug` under uv-managed CPython 3.13.12;
- the Unicode checkout path reproduced the Windows ANSI-path limitation and
  passed with the process-owned temporary ASCII drive alias;
- all existing Angmoo checks also passed, including backend, frontend,
  PostgreSQL migration, architecture boundary, DCO, OSS boundary, dependency
  license, CodeQL, Windows local smoke, and the three Local Smoke jobs.

This establishes clean Hosted reproduction and current-runtime regression
compatibility. It does not switch the production runtime and does not itself
authorize ER1 merge or ER2 implementation.

## License and distribution boundary

- LadybugDB 0.19.1: MIT;
- Tauri and its CLI: Apache-2.0 OR MIT;
- Angmoo spike source: GPL-3.0-only;
- PyInstaller is build tooling under GPL-2.0-or-later with its bootloader
  distribution exception;
- separate MPL/BSD/Unicode licensed dependency files retain their notices.

These terms permit a GPL-3.0-only Angmoo distribution when the generated SBOM,
third-party notices, and dependency license texts are preserved. This is a
compatibility finding, not legal advice.

## Decision boundary

Local and Hosted evidence satisfy the technical Go criteria, but do not by
themselves make ER1 PASS. The remaining gates are:

1. user review of the CPython 3.13.12 and LadybugDB 0.19.1 pins;
2. user review of the process-owned temporary ASCII drive alias for Unicode
   Windows data paths;
3. explicit user Go/No-Go and PR #102 Ready/merge approval.

If clean Windows reproduction fails, the spike is No-Go and ER2 does not
start. The existing PostgreSQL/Neo4j/Docker runtime remains unchanged in either
case.
