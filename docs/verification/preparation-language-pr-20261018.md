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
