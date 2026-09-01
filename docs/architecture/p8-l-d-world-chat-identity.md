# P8-L-D World-scoped Chat identity inventory

Status: **IMPLEMENTED · LOCAL TECH PASS · ISSUE #218 OPEN · BRANCH `feat/p8-l-d-world-chat-identity-role-binding` · EXACT BASE `8a83f48ed565992f8c3e7dd1dbe958f33997e7ab` · IMPLEMENTATION COMMIT `9351b38d70496ff60d97a1484808cbe7c3be58c5` PUSHED · DRAFT PR #219 OPEN · HOSTED CI RUNNING · USER/READY/MERGE/POST-MERGE PENDING**

P8-L-D owns the first append-only successor inventory after the P8-L-B Chat domain parity closeout. The machine-readable artifact is `p8-l-d-world-chat-identity-inventory.json`; it records the World-scoped thread identity, the Alembic/Embedded v4 migration pair, canonical World Chat routes, and the supported Windows installer `v3 → v4` upgrade fixture.

## Historical inventory rule

`security/p8_l_a_inventory.json` and `security/p8_l_b_chat_domain_inventory.json` are completed-stage evidence. They remain byte-for-byte frozen. Once this D inventory exists, the P8-L-B check verifies its frozen digest and predecessor chain instead of regenerating B from the newer D tree. Regenerating B against D would incorrectly report the intentional Alembic `0084` migration and Chat model changes as B drift.

Current-tree ownership therefore moves forward without rewriting history:

```text
P8-L-A frozen inventory
→ P8-L-B frozen inventory
→ P8-L-D current World Chat identity inventory
```

The D generator checks durable semantic invariants rather than the current global Alembic head count. A later stage may add another migration without invalidating D, while mutation of D's immutable `0084`, Embedded v4 manifest, or `v3 → v4` migration files remains detectable through their normalized SHA-256 records.

## Installer Gate

The supported predecessor matrix remains cumulative: v1 and v2 are retained, and v3 is added. The v3 fixture contains both a deterministically resolvable legacy thread and an ambiguous legacy thread, plus messages in both threads. It is frozen in the pre-v4 `message_threads` shape. The real candidate installer must upgrade it to Embedded SQLite v4, preserve all legacy fields and message bodies, bind only the uniquely resolvable thread, leave a non-unique or absent pairing `ambiguous`, quarantine an active tuple collision as `quarantined`, and remain idempotent when the same candidate is installed again.

## Verification

The 2026-09-01 local Gate passed with the full backend suite at `1543 passed,
22 skipped`, the focused identity/migration/API/installer/inventory bundle at
`54 passed`, Next product-shell browser tests at `18/18`, static/Tauri browser
tests at `61/61`, and Rust product-window tests at `7/7`. Frontend lint,
typecheck, Next build, static export, generated inventory checks, and compileall
also passed. A real file-backed SQLite/WAL concurrency probe converged two
simultaneous first-use create-or-get requests to `created + reused` with zero
exceptions and exactly one thread and one preference row. PostgreSQL-specific
concurrency remains a separate unverified Gate.

Run:

```powershell
backend\.venv\Scripts\python.exe scripts\ci\generate_p8_l_d_world_chat_inventory.py --check
backend\.venv\Scripts\python.exe scripts\ci\check_windows_installer_supported_upgrade_matrix.py
backend\.venv\Scripts\python.exe -m pytest -q backend\tests\test_p8_l_d_world_chat_inventory.py backend\tests\test_p8_l_d_installer_upgrade_contract.py backend\tests\test_windows_installer_supported_upgrade_verifier.py
```

The real NSIS execution remains a Hosted Windows Gate because it requires the built candidate installer. `.github/workflows/windows-installer.yml` builds and uploads `supported-v3.zip`, and the supported-upgrade job passes it to the isolated runner alongside the existing v1 and v2 fixtures.
