# P8-L-F canonical Memory schema and scope control

Status: **IMPLEMENTED · LOCAL TECH PASS · IMPLEMENTATION COMMIT `cb348f6ca8adde22cf467e3a8b4a121b28178d71` · PUSH PASS · ISSUE #222 OPEN · DRAFT PR #223 OPEN · HOSTED CI V4 FIXTURE CORRECTION PENDING · USER GATE/MERGE PENDING**

P8-L-F establishes the canonical persistence boundary required by later memory write, recall, and owner-control stages. It does not call a provider, select a retrieval route, build an FTS index, mutate LadybugDB, generate a Chat answer, or expose a Memory UI.

The backend owner is `app.domains.memory`. Its framework-free domain defines `MemoryKindV1`, owner+World+remembering-subject scope, retention and pin semantics, item-shape invariants, and stable privacy-safe errors. Application code reaches persistence and future source/queue adapters only through the public facade and typed ports. SQLAlchemy remains inside `domains/memory/infrastructure`.

The first setting scope is deliberately narrow:

```text
owner_id
+ world_id
+ subject_world_character_id
```

The repository proves that the owner is active, owns the non-archived World, and that the remembering subject is an active WorldCharacter in that same World. A missing setting is created with `enabled = false`, retention 180 days, provider mode `none`, and version 1. Updates require an expected version and advance the monotonic token. Counterpart- or thread-specific overrides are not introduced.

Seven canonical tables are added:

- `memory_scope_settings` — opt-in state, retention, provider mode, version;
- `memory_candidates` — idempotent source envelopes and bounded decisions, not accepted memories;
- `memory_items` — scoped summaries with active/superseded/deleted lifecycle, validity, pin, and version;
- `memory_item_evidence` — exact canonical source references, digest, World, direction, and observation provenance;
- `memory_hot_briefs` — rebuildable scoped cache generations and source-set digest;
- `memory_hot_brief_items` — exact item/version membership of a brief;
- `memory_maintenance_jobs` — idempotent bounded jobs with lease-pair and terminal-state constraints.

`MemoryKindV1` is closed to `OWNER_PREFERENCE`, `AUTOBIOGRAPHICAL_EVENT`, `DIRECTIONAL_RELATIONSHIP`, `THREAD_SUMMARY`, and `ACCEPTED_JOINT_COMMITMENT`. Relationship and joint-commitment items require a counterpart; thread summaries require a thread. Unknown kinds fail closed. Pin bypasses retention expiry but not explicit deletion or supersession. Correction and deletion are represented by canonical lifecycle state rather than an in-place rewrite that loses provenance.

The schema is append-only Alembic revision `20260831_0085` after `20260831_0084`. Embedded SQLite advances from v4/87 tables to v5/94 tables with an immutable manifest and a v4→v5 expected-delta contract. Only the seven new empty tables may appear; every predecessor table and row identity is protected. The production upgrade coordinator still performs copy-on-write staging, integrity/FK/manifest validation, atomic generation promotion, and original-generation preservation on failure.

The real Windows installer matrix now includes synthetic v4 in addition to v1/v2/v3. v4 keeps the World Chat identity shape and removes only the new empty Memory tables, so Hosted CI must prove the actual v4→v5 path and target reinstall idempotency.

The machine-readable successor inventory is `p8-l-f-canonical-memory-inventory.json`. It chains the frozen P8-L-E inventory and records domain ownership, exact table/column/constraint contracts, migration metadata, supported predecessor coverage, and explicit non-scope.

## Local verification

- canonical domain, repository, schema, migration, and successor-inventory focus: `29 passed`;
- embedded-upgrade, installer, ER0, L4, and privacy-deletion regression bundle after v5 fixture synchronization: `35 passed`;
- v4 predecessor World Chat identity fixture correction regression: `20 passed`;
- full backend regression after the v4 fixture correction: `1,567 passed, 22 skipped`;
- P8-L-F/D/E generated inventories, ER0 inventories, architecture boundaries, desktop installer contract, and Windows supported-upgrade matrix: current and passing;
- C-drive free space before the corrected full regression: approximately `16.42 GiB`, above the `3 GiB` stop threshold.

The first Draft PR #223 Core CI backend job (`33490748179` / `99801483547`) preserved an append-only failure after `1,566 passed, 22 skipped`: the ER0 generator correctly rejected the stale `20260831_0085` source hash in `migration-conversion-inventory.json`. The migration received a final maintenance-lease constraint after the previous inventory write, so the checked-in hash still described the pre-constraint source. Exact head `4e2b888813f7d43c1da839eec1d88a52efc70817` corrected only that generated entry to normalized current-source digest `251cb4256c77f7047eb6b6eb2eab1eb35eac1059657ebd8f49d60da2db704b16` and passed the corrected full backend suite.

The second exact-head Windows Installer run (`33492170373` / supported-upgrade job `99813114023`) passed v1, v2, and v3 direct upgrades, clean install, migration-failure rollback, installer build, and all non-installer checks, but preserved `supported_upgrade_world_chat_identity_mismatch` for synthetic v4. The v4 fixture had been created with the current table shape while its two rows still held the ORM defaults instead of the already-migrated P8-L-D resolved/ambiguous identity state; v4 correctly skips the v3→v4 backfill, so the verifier exposed the fixture inconsistency. The correction freezes the resolved row with exact World/requester/responding WorldCharacter IDs, freezes the ambiguous row explicitly, and makes the local v4 builder test execute the same full identity verifier. It does not change production migration or product data. The related `20 passed`, full backend `1,567 passed / 22 skipped`, and generated P8-L-D/F inventories pass locally; a new exact-head Hosted CI pass is still required.

The branch push and Draft PR exist, but local evidence and either correction do not imply an exact-head Hosted CI pass, user installation Gate, merge, post-merge validation, or P8-L completion.
