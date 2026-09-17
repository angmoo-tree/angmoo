# Chat reference trace RT validation

2026-09-12 · Local implementation on `fix/chat-retrieval-debugging`.
Baseline HEAD: `ee8eabf7c68e5a7fb7a5c4e9d11dc0e4d2a56a8d`; 83 pre-existing dirty/untracked entries.
Artifact directory: `D:/project_code/angmoo-workspace/.task-output/chat-ref-trace-20260912-224658`.

## Status

RT0–RT6 implemented and locally checked. RT7 contributor runtime deployment and source verification are complete. A subsequently authorized ten-question DELEGATED BROWSER CHECK is complete; it is not relabeled direct USER CHECK. RT8 now includes attribution of new actual failures through their exported request records. The implementation checks made no paid model calls; the later browser test sent ten real chat requests with existing internal repair enabled. This records diagnostics capability, not improved model accuracy or resolution of historical failures.

## Ownership and contracts

- Chat owns `contracts/reference_observation.py`, semantic parsing instrumentation, resolution provenance and the diagnostic request history.
- Shared `decision_observation` owns bounded transport only. `decision-trace.v2` extends the previous detail rows; the basic record remains `chat-retrieval-diagnostics.v1`. Old detail rows remain readable without fabricating missing v2 fields.
- Relationships' existing Graph expected/returned identity and direction observations are reused. The actual Graph validator, query operations, repair policy and CRG responsibility are unchanged.
- The frontend change is **LOCAL** under frontend ARCHITECTURE/DESIGN: the same Chat component and existing Button/tokens, no new colors or separate Tauri UI.

## Reference evidence

`reference_failure` is emitted at the existing failing check. It records phase, call, entity index or relationship field, actual rule and reason. String shape features are bounded to a 161-character scan, with `features_complete=no` when truncated. Neither a prefix nor the full arbitrary reference string is exported. Raw and normalized aliases may be compared only when capture and alias limits permit it.

The recorded rules distinguish required-string/type/length failure, entity-ref format, relationship-ref format, missing entity-ref key, same endpoint and unbound endpoint. Existing exception codes and check order are retained. A formatting observation is not a second validator. In BOTH, identical whole-request semantics are still validated once under call 1; received/normalized inputs retain each call's ordinal.

`reference_inputs` records received, normalized and validated stages. `resolved_references` records existing candidate counts, adopted identity aliases and the direction result; it does not repeat entity resolution or any database query. Ref aliases describe strings within a request; identity aliases describe bound identities. Neither alias is a cross-request identity.

Actual rejection and binding rows are prioritized over redundant detail snapshots under the existing 24-row/64-KiB cap. Omission remains explicit. Basic logs do not acquire reference strings or identity aliases. Detailed OFF does not allocate reference alias mappings.

## Request identification and export

The old diagnostic selector consumed `evidence_summaries`, which lists only committed responses with public evidence. It could not select previous failed requests. A separate owner-scoped `GET /diagnostics/requests` now reads existing `ChatResponseRequest` rows, regardless of evidence or terminal state. Default page size is 30, maximum 100, ordered by creation time and request ID. The cursor is an existing request ID looked up within the authorized thread; no new database table or migration is used.

The diagnostic read adds whitelisted request metadata. The frontend displays time/state/ID and exports `angmoo-query-diagnostics.export.v1`, including that same request, basic record and optional details. It separates creation time, export time, historical capture observations and current capture settings. An expired/missing detail array stays null; basic-only export is identified as such. Old ID-less arrays are legacy unattributed evidence, not automatically associated with the newest failure.

Changing selection, refreshing, or changing scope invalidates the previous snapshot. Aborted/out-of-order responses cannot replace a newer selection. The export helper additionally checks World/thread/request and metadata consistency. Opening nested detail disclosure does not trigger parent refresh. No message text, tokens, credentials or arbitrary request metadata are added to the export envelope.

## Local checks

- Existing targeted diagnostics/Graph/argument tests after instrumentation: 201 passed.
- New `test_reference_trace.py`: 23 passed. Includes malformed/normalized refs, first-failure location, self/unbound/builtin distinctions, OFF/ON provider-input equality, scope cleanup, routing provenance, mixed history pagination and owner checks.
- Combined RT5 suite: **310 passed, 1 skipped**, one existing Starlette/httpx warning. `rt5-tests.txt`. The skip is an opt-in performance test.
- Export helper on the installed Node 20 runtime via the existing TypeScript compiler: **3 passed**, `frontend-export-tests.txt`. No additional dependency or test framework.
- Playwright `diagnostics/product-shell.spec.ts`: **1 passed**, `browser-tests.txt`. A synthetic, fully intercepted backend verifies failed-request selection, 30+ history entries, exact download ID, basic-only export, out-of-order reads and latest selection. It sends no real messages and is not a USER CHECK.
- `frontend typecheck` and lint pass. Existing architecture and frontend boundaries pass. Updated source import inventory: 1,096 modules / 4,123 internal edges / zero legacy exact edges.
- Frontend design check passes, raw colors remain 1,392 in 37 files. The generated design report changed only the hash of an already-dirty pre-existing browser spec; design thresholds and screenshot expectations were not relaxed.
- AST comparison: eleven prompt/schema/normalization definitions match RT0 exactly (`prompt-schema-preservation.json`).
- Full preservation has the pre-existing `Chat durable command changed: mark_terminal` failure. RT0 captured it before edits. It is not reported as PASS and protected baselines are not relaxed.

## Runtime and USER CHECK

Contributor Docker was identified through its actual compose project/configuration and volume; this is not installed Windows Angmoo/AppData. Before build, the active canonical generation was schema v11, with 66 requests (46 committed, 20 failed), no active requests. The latest model snapshot was gemini-3.1-flash-lite/high. Request metadata hash is saved in `runtime-before.json`. The latest request preceded the current detail TTL, so no recent retained request detail is assumed recoverable through restart.

Both development images built successfully and `compose.yml` + `compose.dev.yml up -d --no-build backend frontend` recreated only the two services. Both are healthy. SHA-256 comparisons confirm the deployed reference observer, request repository, NA workflow configuration, frontend diagnostics component and export helper match local source (`runtime-source-hashes.json`). NA remains native controls + code coordination, positional entity refs false. No volume/database deletion, migration change or model-setting write occurred.

`runtime-after.json` matches the prior 66 requests, states and metadata hash exactly. This comparison occurred before new USER CHECK messages. Historical model snapshot remains `gemini-3.1-flash-lite` / `high`; this is not a claim that a new model request has run.

The user has been asked to refresh port 3000, enable detailed capture, and submit incoming relationship (1) and positive relationship ranking (3), reporting their request IDs and result status. No old failure is assigned a concrete raw reference value from the synthetic examples.

## Limited performance observations

The synthetic provider reference-rejection boundary was measured after ten warmups, 100 samples per mode, using RT0 source overrides versus current source. Files: `performance-before-idle.json` and `performance-after-idle.json`.

| Mode | Before p50/p95/max ms | After p50/p95/max ms |
| --- | --- | --- |
| Detailed OFF | 1.188 / 15.765 / 16.922 | 1.133 / 10.855 / 20.239 |
| Detailed ON | 1.902 / 16.271 / 110.795 | 1.570 / 15.321 / 121.789 |

No incremental p95 regression exceeding 5ms was observed. Large outliers and local scheduling variance preclude claiming a speedup. This samples a changed parsing boundary, not full Graph retrieval/model latency. The initial baseline harness import failure was corrected by allowing unchanged modules from the current source; the initial concurrent-build measurement is retained separately and is not used as the before/after comparison. No product behavior was changed to satisfy the benchmark.

The deployed request-list repository was independently sampled read-only on the existing database: 30 records/page, next page present, 100 measured reads, p50 1.821ms / p95 3.407ms / max 3.860ms (`history-performance.json`). This excludes HTTP and browser rendering; the browser test validates correctness, not a render-latency SLA. Initial standalone harness imports (SQLModel assumption, then missing ORM model registration) were corrected to use the actual SQLAlchemy Session and runtime model registration. No database writes were performed by the measurement.

## Attribution handoff

Historical issue 1: counterpart rejection is known; the first divergent value in the original failed request is still not reconstructed. A later successful incoming lookup is a separate request.

Historical issue 3: format→unbound and format→self are distinct observed sequences. New instrumentation can identify the exact field/rule and alias relationship on a new occurrence; it does not retroactively establish the missing format characters.

Issues 2 and 5 retain their prior evidence and are not repaired here. Request-list selection and ID-less export were independently verified backend/frontend diagnostic defects and are addressed by RT4.

For direct testing, enable detailed capture after runtime restart, send the incoming-relation question and positive-relationship-ranking question one at a time, and export the selected request immediately. Do not repeat tests until the request ID and captured fields are checked. A successful response validates that path only; an unreproduced failure remains unreproduced.

Rollback is a comparison against `before/` for only this patch. Preserve pre-existing dirty files, logs and user downloads; no reset, branch switch, volume deletion or blanket restore.

## Subsequent authorized browser check — 2026-09-12 23:43–23:50 KST

Browser connectivity recovered after the earlier tool initialization blocker. Ten user-approved questions were sent once each using the actual Edge UI, on the existing thread, with `gemini-3.1-flash-lite/high` confirmed in all ten request records. All ten exports include matching request metadata and detail_captured=true, detail_omitted=0. Detailed capture was renewed after the seventh new request exhausted the prior remaining allowance. No code/model/validation changes or user-retry-button clicks occurred.

Results: GRAPH requested 10/10, Supervisor validation passed 7/10, graph actually executed 4/10, committed replies 4/10. Three replies provided the expected facts. One shared-neighbor reply reported inability to confirm: the candidate was excluded under observed_by_subject=false for All Might→Haru. This is an initial fixture-scope oversight, not evidence of model failure. Six failures divide into three Supervisor reference errors and three Graph contract rejections.

New evidence establishes builtin values in the invalid entity-ref position (questions 5/6), undeclared/self endpoint transitions (7/10), a Planner counterpart bound to responding_character rather than the expected counterpart (2), and the global outgoing contract rejecting a necessary incoming step for bidirectional questions (4/5). The fourth/eighth questionnaire numbers here belong to this ten-question test, not the earlier DT five-question set.

Full questions, request IDs, evidence, policy limitation and follow-up proposals: [10-question browser report](../../../docs/plan/09-12%20미도리야%20Graph%2010문항%20브라우저%20실검증%20결과와%20실패%20원인%20분류.md). Evidence directory: `D:/project_code/angmoo-workspace/.task-output/graph-browser-10-20260912`. These are new requests; historical missing raw values remain unproven.
