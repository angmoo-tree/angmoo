# World activity schedule updates — local verification, 2026-10-18

Branch: `feat/preparation-output-language`. Starting HEAD:
`3470e070aee1f87bb50becfe1fd96b06b248f7d9`.
The preceding language change is local commit `29e8147d`.
This record covers the second logical change and the integrated I00–I63 plan.

## Implemented boundary

WorldCharacter owns normalized three-field change detection, actual OFF→ON,
authorization/revision, and the existing commit/rollback. Runtime injects a
typed schedule collaborator, checks exact current owner/World/role/membership/
binding and reads fresh column values. Routines conditionally updates only the
matched `assigned_idle` slot with no run ID, no unresolved lease and no unrelated
error. Expired-but-unsettled leases are preserved, too.

The next time is max(now, last completion + effective interval), moved into an
allowed window with the existing deterministic spread. The interval is not added
twice. Last completion, quota, accepted inputs and unrelated slots are untouched.
OFF/unassigned characters retain intent for the existing bounded allocator.

Normal automatic completion takes the SQLite writer through a conditional slot
write before reading current settings/environment. The run ID and owner/character
assignment are checked. Only a changed cadence/timezone replaces the next time.
Current language/model/credential/situation inputs and already recorded effects
are not regenerated. Failed/deferred/cancelled/manual completion does not opt in.
The real Resident entry point is covered with synthetic activity results.

One frontend change is necessary: successful settings save previously replaced
settings but retained old management/next-time data. The existing shared hook now
issues one management GET, using its existing scope/generation/revision fences.
It neither computes a time nor sends another mutation. There are no new labels,
translations, styles, DTOs, polling loops or platform branches. Provenance LOCAL.

## Local validation

Environment: locked existing Python environment, fake providers, temporary file
SQLite databases and `ANGMOO_DENY_EXTERNAL_NETWORK=1`. No production DB or key.

| Group | Command / coverage | Result |
|---|---|---|
| Language | Eight planned files plus actual Chat Supervisor transport node | 181 distinct cases passed across targeted runs; see language record |
| Existing schedule owners | `test_world_independent_autonomy.py`, `test_world_character_configuration.py`, `test_activity_policy_transaction.py`, `test_retry_schedule_transaction.py`, `test_environment_admission.py` | 42 passed |
| New schedule regression | `tests/routines/test_schedule_updates.py` | 48 distinct final cases passed across the main and targeted follow-up runs |
| Real manual/shutdown preservation | Two related nodes in `test_activity_limits.py` | 2 passed |
| Common frontend hook | `node --test scripts/tests/world-schedule-refresh.test.mjs` from frontend | 3 passed |
| Frontend required checks | architecture, design `--check`, `pnpm --dir frontend lint`, `typecheck` | Passed |
| Backend ownership | architecture boundary checker, regenerated actual import inventory | Passed without policy exceptions |

Initial failures in the new schedule tests exposed test assumptions: the dashboard
DTO contains an ISO string; a 24-hour test window violates the existing maximum
17-hour contract; and allocation's clock is owned by `service/slot_requests`,
separately from management and completion. Fixtures use valid windows, parse the
wire timestamp and freeze each actual clock owner. No production duration/limit
or validation rule was relaxed to make these tests pass.

The existing 42-case group passed in 608.95s on this machine. The initial complete
new group had 44 passed and one clock-fixture failure in 520.64s; targeted follow-up
also covers capacity and actual Resident completed/failed results. These local
test durations are not app latency measurements or predictions of GitHub CI time.
The final two allocation-clock checks passed 2/2 in 29.74s. In total the schedule
group covers 92 distinct cases (48 new + 42 existing + 2 manual/shutdown), with
all final cases passing. Passing unaffected cases were not needlessly repeated.

## Contract-to-evidence ledger

The integrated plan's language contracts L00–L15 are mapped in
[language verification](situation-query-language-20261018.md): real Feed/Inbox/
combined transport, common situation generation, actual CRG/Supervisor, receipt
and memory application, fallback/call budgets and prior preparation. Policy and
diff review additionally confirm unchanged relationship/image policies.

| Schedule contracts | Evidence in `test_schedule_updates.py` unless noted |
|---|---|
| S00 | basic/detailed save replaces old future; baseline unconnected-command reproduction |
| S01, S07, S08 | retained/reallocated OFF→ON; inactive/pending basic save; capacity then reassignment |
| S02–S04 | valid windows, exclusive end, midnight, 24:00, Seoul, New York DST, interval minimum/elapsed lower bound/spread |
| S05–S06, S21 | same/unrelated save and repeated ON/GET produce no slot UPDATE; other World row unchanged |
| S09–S11 | exact binding/owner/World/character; invalid value/stale revision/foreign owner; injected failure after slot write rolls back settings/revision/slot |
| S12–S13 | independent file-DB sessions, same revision single winner, edit/claim both orders |
| S14 | running, run ID, future/expired unresolved lease preserved |
| S15–S16 | edit/completion both orders including stale ORM map; actual Resident success preserves run/snapshot/result and uses latest cadence |
| S17–S18 | cooldown/unhealthy/runtime_shutdown/credential errors unchanged; explicit manual/failure next times; actual shutdown and existing manual guard nodes |
| S19–S20 | owner timezone/locale changes with accepted input preserved; fresh Session sees persisted time and existing claim accepts it |
| S22 | real dashboard DTO matches persisted time; shared hook success/read ordering/runtime-switch tests |
| S23 | typed injection, same UoW, import checker, no schema/dependency/worker changes |
| X00–X01 | admitted Korean input stays Korean; fresh environment is English; current run/model/credential input unchanged while next cadence uses current time policy |
| X02 | rollback, revision competition and late completion tests + existing receipt/recovery/budget tests; no repeated activity/provider call |
| X03 | same frontend hook and DTO for Next/Tauri; actual hook transport test with runtime switch, no extra mutation |

S18 clarification from current source: `manual_next_tick_at` is intentionally None;
the existing regression forbids restoring the old timestamp automatically. This
change preserves that rule and explicit manual/retry times. The plan's phrase
“manual restoration” does not authorize reintroducing obsolete restoration logic.

## Cost, scope and remaining user evidence

Language mapping adds no business I/O. An actual schedule change adds bounded
actor-scoped reads and one conditional slot update within the settings transaction;
normal World completion adds a guarded writer acquisition and fresh scoped reads.
Unchanged settings add no schedule write. There is no long provider wait under
these new locks, global reschedule, timer or new retry loop. Query/row-scope checks
are local synthetic evidence; exact production lock-hold/wait milliseconds remain
unmeasured and zero-latency is not claimed.

No full backend suite, full frontend tests/build/E2E, image build, deployment,
GitHub CI, push, PR, merge, installed-app access or real Bram activity was run.
Frontend hook tests are not native visual proof. Actual AI prose quality and
Browser/WebView detection remain user checks after applying the source.
Older stale reservations can use the supported OFF→ON flow after this code is
deployed; this implementation did not change any user's saved settings.
