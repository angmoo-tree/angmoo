# Generation language, schedules and Chat integration verification

PR #392 integrates the five scoped changes documented in the language,
schedule, topic-diagnostics and Chat-budget verification records.

## Initial publication

The original local branch `feat/preparation-output-language` remains at
`790da37ba15eca49366fa50c2d6be908aae4c5a3`. Three original commits lacked DCO
trailers. The five changes were replayed with `git cherry-pick --signoff` onto
`integrate/preparation-output-language-dco`, preserving the original branch and
commits without force-pushing or relaxing the DCO check.

The initial published head `c83bcbcf102fd5d1d0864075d608371bd75bf7b6` has the same
tree `b4f5847f968dcc516b9f303ff17f6b364b4dad97` as the original. Existing focused
verification applies to those identical files. DCO, OSS boundary, architecture
inventory, backend/frontend boundaries and frontend design checks passed again.

## Hosted preflight failure and generated inventory repair

Core CI run `39124758778`, attempt 1, failed before backend test partitioning at
`Verify L4 P5-P7 parity and ownership inventory`: the generated L4 inventory was
stale. Checking the following preflight locally also identified stale current
hybrid-episode file hashes.

The official generators updated `security/l4_pr_a_inventory.json` and
`docs/architecture/hybrid-episode-memory-inventory.json`. The reviewed delta is
current module/import totals, the new topic-diagnostics module and hashes of the
changed situation, topic and Chat source/tests. The frozen Memory predecessor,
schema, bounds, embedding configuration, runtime contracts, policy allowlists,
workflow gates and test assertions are unchanged. No product code changed in
this CI repair.

Validation on the repaired tree:

- Official L4 generator `--write --check`: PASS.
- Hybrid-episode generator `--write`, followed by the original Memory-batch
  preflight `--check`: PASS, including the frozen predecessor.
- Public route inventory: PASS, 287 operations.
- `tests/test_l4_pr_a_inventory.py`, `tests/test_l4_parity_current_source.py`,
  `tests/memory/test_hybrid_episode_inventory.py`: **13 passed in 19.61s**, locked
  environment with external network denied.

The initial impact classifier selected full backend and full Windows validation.
New hosted results must belong to the updated PR head. Merge/main CI, regenerated
same-source P3 candidates, P4 user/Android/real-AI checks and P6 publication remain
separate evidence stages.

## Full backend corpus inventory repair

Core CI run `39125053033`, attempt 1, backend partition 0 failed two checks in
`test_l3_er0_embedded_runtime_inventory.py`; 1,743 tests passed in that partition.
The generated `postgres-sql-inventory.json` still described the old
`daily_preparation.py` hash/line and omitted the new row-lock marker in
`routines/service/slot_leases.py` from the schedule change.

`scripts/verify_embedded_runtime_inventory.py --write --check` regenerated the
current scan. The only changed output is that inventory: one source hash/line,
one live entry, and its derived totals. The immutable baseline, migration/query/
route/parity corpora, scanner, assertions and runtime code remain unchanged.
The complete related test module passed: **8 passed in 6.22s**, locked offline
environment with external network denied. The new commit requires a fresh
hosted run; results from different heads or attempts are not combined.

The same run's backend partition 1 found two outdated expectations in the
named-selection lifecycle integration test: it expected `Use ko-KR for this
description` after new admission. The intended shared-language contract now
requires `Use Korean for this description`. The assertion was aligned with that
explicit contract and additionally rejects the old instruction; the existing
assertion that the persisted manifest retains `ko-KR` is unchanged. Response
commit, scoped memory receipt/application, provider count, replay, failure and
authorization checks remain active. No production behavior was modified.

Both related Chat modules passed: **26 passed in 41.70s**. The official current
hybrid inventory was regenerated for the changed test hash; its frozen
predecessor and all runtime settings are unchanged.
