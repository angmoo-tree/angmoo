# World post, Chat and character management implementation

User-authorized plan: workspace `docs/plan/10-05 World 게시글 상세 제목·헤더 정렬과 답글 입력 순서 개선 코드 구현 세부 계획.md`.

Status: **implementation and local verification closeout in progress**. Product behavior P00–P25 is implemented and all three delegated lanes have frozen their source and final local evidence. The repaired core regression passes the final consolidated34-case rerun; exact source commit/provenance, official preservation and task-resource cleanup are being recorded in P26–P28. No historical PASS is reused. C01–C79 and T01–T118 are contracts and coverage identifiers, not 79 features or 118 distinct passing test cases.

## P00 baseline and preservation

- Product checkout: `D:/project_code/angmoo-workspace/angmoo-tree-angmoo`.
- Branch: `feat/0.1.0-release-readiness`; starting HEAD `b36c2d49ec11d45fa8f45d1dd4b5fd2b63dfeea6`; clean before task edits.
- Local implementation and signed-off local commits only. No push, PR, hosted/local CI workflow, main switch/merge/rebase, history rewrite or blanket staging.
- Existing Docker frontend `6bd4f1ff6f27` and backend `12d904c72b25` are running. Frontend publishes localhost 3000; backend uses the existing `angmoo_angmoo_contributor_embedded_data` volume. No task restart or mutation of that volume.
- Existing Compose dev watch can sync `frontend/src`, `frontend/public`, `backend/app`, scripts and tests. Source edits can propagate; isolated tests do not guarantee an unchanged observation runtime.
- Automated writes use synthetic owners/Worlds, task-owned temporary SQLite and separate loopback ports. No operational user data, installed data, API keys or real AI/image provider calls.
- Task Python processes prepend `scripts/testing/offline-python` to PYTHONPATH to disable implicit user dotenv loading, discard inherited provider keys and block non-loopback connections. Product runtime does not load this test bootstrap.
- Workspace/frontend AGENTS, frontend ARCHITECTURE/DESIGN, backend ARCHITECTURE, current design-reference/product-shell/preservation and installed Next CSS/Playwright guides were consulted.

## Work ownership

- Social: detail header/reply placement and scoped server-confirmed reaction updates.
- Chat: neutral Dialog placement, canonical World deletion and both UI entry points.
- Characters/Relationships frontend: shared display cards, World management panes, profile actions/stat placement and graph avatars.
- Primary: immutable import baselines, World configuration storage/migrations/effective readers, autonomy/runtime integration, common documentation, final validation and local commits.
- Shared source files and generated build outputs have one owner; independent tests use separate task resources.

## P01 initial findings

- Registration/copy already creates independent Character/WorldCharacter IDs and preserves single-World execution binding.
- Current `settings_copy` uses live source persona/media. No immutable creation baseline exists in the current canonical model.
- Current public profile fallback reads live Character display values; current owner profile PATCH also changes common Character fields.
- World `autonomous_enabled` exists, while current global activation changes both common activity settings and selected World state. Scoped persistence and actual admission must be separated without relaxing leases or capacity.
- Existing World states, IDs, posts, threads, memories, relationships and admitted request snapshots remain preservation targets.

## Implemented behavior and owning paths

- World detail uses `게시글` / `post`, with the existing back button and a 12px title gap. The same reply form appears after the reply heading, empty state or recursive list, and pagination.
- Social captures auth/runtime/owner/request lifetime, validates the returned confirmed reaction and publishes it once. Each matching row receives the exact server count/selection. Ready content, loaded cursors, image elements, scroll and drafts survive. Profile membership/count revalidation follows canonical page chains and retains anchors; access loss is separate from a retryable background error.
- The shared native Dialog has centered margins and constrained internal scrolling. World Chat lists and rooms use Trash2, with Settings → Trash in the room. Owned canonical DELETE soft-deletes only the thread timestamp. Active responses reject with 409, replay is idempotent, and explicit restart creates a fresh empty thread. The shared admission lock orders accept/retry/model changes with deletion.
- Device Home and World reuse the same Characters management display card. World GETs use only active participants, put actual owner-controlled users first and count stored ON/OFF/users without treating unavailable capacity or outside hours as OFF. World management reuses the header, three tabs, profile uploader/cropper, persona and activity controls; changed fields are sent to scoped revision-checked APIs.
- New registration captures immutable creation S0. Proven initial records restore S0; unverifiable legacy records capture an honest, one-time `legacy_transition` L0. Source revision, provenance, digest, capture time and media lineage are stored. Copy uses that immutable basis, creates independent actor/role IDs and starts OFF, without copying World memories, relationships, posts, threads, queues or leases.
- `WorldCharacterConfiguration` owns complete World profile/settings. Profile/media/persona/policy/model edits and ON/OFF affect only that World. Reads do not backfill or borrow live common Character settings. Existing World values and admitted inputs survive the additive v28/0106 conversion. Canonical handle/media ownership/CAS/permission checks remain in the owning services.
- Runtime supplies narrow effective-configuration and autonomy-admission ports to owning Chat/Social/Routine/Media services. New admission freezes World/actor/revision/persona/model/policy; retry/recovery/worker input retains the accepted snapshot. Historical requests retain their historical path. Independent A/B ON is admitted through the existing capacity, duplicate, lease, time and permission policies. OFF and membership changes do not recapture or release an already admitted snapshot.
- World authors and graph nodes get authorized saved display values in batches. Profile actions use the existing neutral Network SVG → Mail → supported edit. Three follow statistics are absent; the four canonical post/reply/like/received counts are inline in the profile body. Graph nodes use the common photo/initial fallback avatar and retain center, direction, coordinates and accessible names/evidence.

Key owning sources: `backend/app/domains/characters/service/import_snapshots.py`, `backend/app/domains/world_characters/service/configuration.py`, `backend/app/domains/world_characters/service/management.py`, `backend/app/runtime/world_characters/management.py`, `backend/app/runtime/routines/configuration_reads.py`, `backend/app/runtime/resident/autonomy_composition.py`, `backend/app/runtime/world_configuration/`, `backend/app/runtime/social/post_authors.py`, `backend/app/domains/chat/service/threads.py`; Characters/Social/Chat/Relationships components, clients and hooks under their existing frontend feature roots.

Architecture: owning domains do not import Runtime or other feature UI. Runtime composition injects the ports; the run-now API response belongs at API composition to avoid World ↔ Routine dependency cycles. Existing architecture entries were retained and only four explicit supported entries were added. No wildcard/cycle exemption, replacement store, lazy read migration, arbitrary capacity increase or hidden global PATCH was introduced.

## P00–P28 stage record

| Stage | Implemented / verified result | Principal evidence |
| --- | --- | --- |
| P00 | Branch/clean baseline, instructions, watch boundary and independent resources | Baseline above; task source/build copies without dotenv |
| P01 | Storage/read/write/consumer investigation and real synthetic two-World fixtures | `backend/tests/world_configuration_fixture_support.py`, actual browser fixture |
| P02 | Architecture/design/product shell/reference and ko/en contracts | Backend/frontend ARCHITECTURE, DESIGN, catalogs and reference documents |
| P03 | Exact title and fixed left alignment | Social final 43 cases in each mode |
| P04 | Reply tree/pagination before the same composer | Social order/55-reply pagination and unchanged nesting regression |
| P05 | Typed confirmed reaction event and request lifetime | Social unit four cases and actual publisher audit |
| P06 | World/global target-only updates | Social row/image/form identity and zero extra feed/thread GET assertions |
| P07 | Canonical profile counts/membership/page chains | Three loaded pages, anchor/focus, delayed GET and access-loss cases |
| P08 | Centered native Dialog | Chat ko/en 480/960/1440/1920px, 360px/200%, focus/backdrop/internal scroll |
| P09 | Scoped guarded soft DELETE | Real router/DB permission, timestamp-only preservation, 15 lifecycle states |
| P10 | Typed delete controller/auth/runtime lifetime | Chat failure/retry/lost-response/late401 cases |
| P11 | List Trash and room Settings → Trash | Chat 23 cases in each mode; surviving rows/drafts/photos retained |
| P12 | Actual deletion/restart/races and legacy regression | Chat 31 + 55 groups and actual API browser case in each mode |
| P13 | Immutable S0/restored S0/L0, complete World configuration, additive migration | Snapshot/copy, SQLite/PostgreSQL transition and read-only config tests |
| P14 | Shared card layout and original World shell | Character shared display source and two-mode geometry/navigation tests |
| P15 | World client, exact participation, user-first/count/recent order | Character UI and real dashboard user 0/2, exclusions, current-World recent/query tests |
| P16 | World saved ON/OFF and original runtime admission | Routine 23 independent activity/read-admission cases, separate sessions/barriers |
| P17 | Migration/copy/CAS/media/readiness/preservation regression | Core final group, historical upgrade 15, graph/entry/owner 46 |
| P18 | Scoped management/profile/settings/media APIs and effective readers | Real router/auth/origin/field/revision tests, actual browser writes |
| P19 | Same three-tab layout and World-only editors | Character ko/en draft/conflict/permission/geometry cases |
| P20 | Accepted actual consumer inputs and scoped run-now | Chat 31, Social/Media 32, Routine 25 and actual S0/L0 browser scenarios |
| P21 | Network action, compact statistics and photo graph | Character profile/graph cases, canonical graph API, query limits and preserved media |
| P22 | API/ORM/schema/source/test inventory and contract map | 62 operation/schema deltas, six ORM deltas; exact append record follows source commit |
| P23 | Individual local static checks and both builds | Catalog 16/2535; architecture 1401 modules/5807 edges; frontend 14 features; design PASS |
| P24 | Synthetic browser and actual API integration in both modes | Final Social, Chat, Character and real API cohorts below |
| P25 | Final screenshots, geometry and source/consumer review | Ko/en, seven widths, 200%, native focus; 399 frontend source files match tested build |
| P26 | Signed-off source commit and exact append-only introduction | Pending final Character source freeze / actual commit record |
| P27 | Official frontend/backend preservation and separate evidence commit | Pending committed introduction and official checks |
| P28 | Plan/report, owned resource shutdown, ending state | Pending final evidence commit / cleanup |

## T01–T118 traceability

Each range below is fully expanded in the referenced lane summary or concrete pytest nodes. These IDs overlap executed cases; they are not summed into a test-count claim. Browser response doubles, actual owning API/DB behavior and controlled worker input are different forms of evidence.

| Contract range | Executable validation / evidence |
| --- | --- |
| T01–T14 | `browser-tests/world-post-reactions.spec.ts`; existing World composer and static product-shell preservation. [Social per-ID mapping](../../artifacts/world-post-reactions-20261005/summary.md) |
| T15–T16 | Individual local checks/build/source comparison and exact Git/provenance/cleanup blocks here; hosted/local workflow CI is unexecuted |
| T17–T32 | Confirmed reactions, three-page list/profile, pending/auth/runtime/old GET, response loss and typed errors. Social 43 per mode plus four pure scope/revision cases; same [per-ID mapping](../../artifacts/world-post-reactions-20261005/summary.md) |
| T33–T39 | `world-chat-dialog-delete.spec.ts`, computed center/scroll/focus/44px/settings/trash/confirmation/retained composer. [Chat per-ID mapping](../../artifacts/world-post-detail-chat-management-20261005/summary.md) |
| T40–T44 | `tests/chat/test_world_chat_delete.py`: actual router, all-row preservation, 15 nonterminal states, file SQLite/two Sessions/controlled barriers for accept/retry/model versus DELETE |
| T45–T48 | Typed UI errors/lost-response/late navigation plus `world-chat-delete-backend.spec.ts` actual UI → API → DB → restart; existing Chat API/identity/model/unlimited/evidence regression |
| T49–T64 | `world-character-dashboard.spec.ts`, configuration/readiness/entry tests; real participation/user0/user2/summary/state/query count/current-World evidence. [Character per-ID mapping](../../artifacts/world-character-management-20261005/summary.md) |
| T65–T76 | `world-character-management.spec.ts` and actual `world-character-configuration-api.spec.ts`: view/Social query/back/keyboard/private lifetime, only changed fields/revision, media cropper, real run admission and DB input |
| T77–T81 | `profile-relationship-avatar.spec.ts`, shared profile components, parent/pseudo-border assertions, Network → Mail → edit keyboard/geometry and canonical inline four counts |
| T82–T88 | `test_relationship_graph_avatar_read.py`, graph domain/regressions and actual API browser photo; same authorized node projection for Ladybug/canonical fallback, 1/8/20 nodes use five constant queries; unsafe/broken/missing photo falls back |
| T89–T90 | Real scoped profile/settings/explicit removal tests; A/B/common/origin values remain separate, live edits cannot resurrect removed values |
| T91–T93 | Snapshot-copy and config tests: final creation capture, rollback, immutable digest/origin, real copy/new IDs/default OFF, explicit creation-entry once and read-only GET |
| T94 | Actual Chat/Social/Routine/Media owning consumers and accepted model/persona/revision. `test_world_chat_configuration.py`, `test_world_configuration_inputs.py`, `test_world_independent_autonomy.py` |
| T95–T97 | Real API field/origin/owner/handle/media/CAS refusal and file SQLite two-Session same-revision race; owner-controlled profile edits only World configuration |
| T98 | Import-media survival/source replacement/delete and expiring copy-draft lineage; unrelated external files/credentials are not copied |
| T99–T100 | v28/0106 additive migration, historical upgrade regression, existing creation/copy/owner/World/Chat/Device Home regression and strict read refusal |
| T101–T102 | Honest ko/en basis/scope notice and actual registration/copy/settings/media/browser scenarios in Next/static with separate S0/L0 variants |
| T103–T104 | Actual registration creates independent actor/role/binding with fixed basis and default OFF; existing state/retry is not reset |
| T105–T108 | Real A/B ON, A-only OFF, slots/capacity/outside-hours/lease, current-World controlled run input; UI route/pending/auth scope preserves saved ON and bindings |
| T109 | Separate SQLite Sessions/barriers order OFF, settings revision and membership-left against automatic admission; existing concurrency/limits retained, accepted lease/snapshot not recaptured. Separate real PostgreSQL20-session single-flight PASS |
| T110 | Actual S0 browser copy → A/B ON → A OFF → B scoped run → real AgentRun input, two modes |
| T111–T114 | Creation/restored-initial/legacy-transition cases, selected source provenance, L0 future copy and complete existing World/row/history/lease preservation |
| T115–T116 | SQLite/PostgreSQL repeat, rollback/resume and source-edit serialization; immutable origin/media lifetime; GET never creates or recaptures a basis |
| T117 | Both S0/L0 actual frozen consumer variants, public author/profile/graph values, honest basis notices and supported image admission; private state/secret data excluded |
| T118 | Actual migrated L0 API/browser copy → A edit → fixed B basis → existing A return → independent admission/input, Next/static |

## Local results and failure disposition

| Group | Result / evidence |
| --- | --- |
| Social final Next/static | 43 / 43 PASS per mode; [summary](../../artifacts/world-post-reactions-20261005/summary.md) |
| Social original static preservation / pure reaction rules | 33 PASS / four PASS; unknown-count aggregate heart and recursive reply indentation were repaired without weakening original assertions |
| Chat final Next/static API doubles | 23 / 23 PASS; [summary](../../artifacts/world-post-detail-chat-management-20261005/summary.md) |
| Chat actual API/file SQLite browser | One PASS per mode; retained old data, exact soft-delete field, new empty ID and zero generation |
| Character UI | 24 base cases + six distinct comparator/history/focus/pending/auth cases PASS per mode; three stronger border/avatar and two footer assertions rerun per mode. [Character summary](../../artifacts/world-character-management-20261005/summary.md) |
| Character actual S0/L0 browser | Two real API/DB scenarios × two basis kinds × two modes = eight PASS; four fresh DB state/health/closed-DB hash records. Next L0 used the preceding successful build with identical World source; remaining modes and all final UI additions used the final integrated build. Root does not infer DB isolation from API doubles |
| Snapshot/config/copy/graph/SQLite/PostgreSQL final core | Final34 PASS after the read/admission repair: [XML](../../artifacts/world-configuration-20261005/core-final-after-read-admission-fix.xml). Includes13 configuration, three real snapshot-copy, ten graph/media, five SQLite transition and three PostgreSQL transition cases. Earlier33-pass/one-regression run is retained separately |
| Current config + historical embedded upgrades | 26 PASS: [XML](../../artifacts/world-configuration-20261005/config-and-historical-migration-final.xml); 11 current config + 15 historical upgrade cases |
| Chat backend / existing Chat regression | 31 PASS / 55 PASS, with one shared node; counts are not unique totals |
| Independent World admission / read separation | 24 PASS (23 World cases + actual draft copy); nine PASS separate Identity/OSS boundaries. Draft/published-not-ready/stale policy display is read-only, while real automatic/manual admission refuses; role/membership/binding/config guards remain |
| Existing Activity/Routine/slots/owner/copy | Final101 PASS + one PostgreSQL skip (Routine99 nodes + snapshot-copy3). That exact skipped node separately passes on the final source with actual20 Sessions and controlled local transport: [XML](../../artifacts/world-configuration-20261005/routine-tick-postgres-after-read-admission-fix.xml). Earlier98-pass cohort remains separate |
| Actual World authors and accepted writes / consumers | 38 PASS / 32 PASS; [Social actual input record](../../artifacts/world-post-reactions-20261005/summary.md) |
| Relationships/feed/context regression / author architecture | 112 PASS / eight PASS |
| Locale, TypeScript, lint, backend/frontend architecture, design | PASS; 16 namespaces/2535 keys; 1401 modules/5807 internal edges/zero legacy exemptions; 14 frontend features; 1215 raw-color occurrences/36files/18surfaces/no route gaps/36 diagnostic screenshot calls |
| Next production + static export | PASS using official build/serve scripts in task source copy; all399 tracked source files match the final tested frontend source by SHA256 |
| Official preservation | Pending exact source commit and append records below |

Intermediate failed XML/JSON remains available. Five historical migration failures came from reconstructing a frozen v2 test database with current v28 tables; fixture reconstruction was corrected, frozen manifests/assertions were retained, and all15 historical cases pass. The new dashboard fixture initially violated the actual owner/membership FKs, and its hours assertion assumed equal start/end meant all day; valid synthetic membership and the existing17-hour policy fixed the fixture. Its two cases now pass with real readiness/state readers. The graph limit assertion initially overlooked existing canonical batch queries; the fixed1/8/20-node case proves the constant five-query bound. Final integration also exposed a real regression: the strict execution-readiness check rejected the existing draft-World copy's returned settings view. The owning module now has separate validated settings-read and admission functions; the original copy fixture/assertions were retained, publication was not forced, and seven additional permission/readiness cases pass. Social/Chat/Character intermediate new-test origin/URL/async/API-double issues are detailed in their summaries. These failed attempts are not relabeled as final PASS.

The approved design inventory now has36 diagnostic screenshot calls instead of24. Its existing11 canonical PNGs, pinned Linux environment and thresholds remain unchanged. Windows diagnostic screenshots/computed geometry do not establish a pinned Linux screenshot-snapshot PASS. Physical WebView/Tauri/IME, real AI output quality and direct USER CHECK are unmeasured.

## Source commit and official preservation

P26 source commit: pending. P27 exact change/introduction records and official backend/frontend preservation: pending. Original source/backend/frontend checkpoints, feature/path maps and SQLite v1–v27 manifests remain unchanged. Append records must contain the actual source commit, parent, blobs/text/AST and canonical operation/schema/ORM deltas; no fabricated SHA or reset baseline is permitted.

The report is introduced in the source commit and finalized in a separate evidence commit, so its tracked introduction has an exact committed source record. Build/test raw artifacts stay under the ignored task-owned artifact directories; reproducible fixture/config/source is tracked.

## Existing observation runtime and excluded work

The original frontend/backend container IDs were preserved; the task did not stop, restart or delete them and did not read or edit the operational database. Compose watch can synchronize code and automatically reload/start the backend, so **unchanged operational runtime or zero automatic migration is not claimed**.

The ending read-only health observation is currently frontend healthy / backend unhealthy. Filtered safe logs contain `SqliteCanonicalUpgradeError`, reason `sqlite_schema_manifest_mismatch`, at the schema-validation path. The task did not inspect the user DB and cannot establish its physical/schema contents or the cause. No fallback bypass, old-manifest rewrite, data reset or operational repair was attempted. Local synthetic migration/verification PASS is separate from this operational health limitation.

No real user API key, paid model/image request, push, PR creation/modification, hosted/local workflow CI, main checkout/merge, installed-app operation or direct USER CHECK was performed. Controlled transport/worker calls and zero external calls are explicitly separated in the fixture health/input records. Operational Docker recovery/application remains a separate scope; installed identity has not been assessed in this implementation task.

## Task resources and reproduction

Task resources: loopback3337 Next,3336 static,3338 optional development preview,3356 Character fixture; Chat3352/3354 fixtures already stopped. Synthetic fileSQLite/media live under workspace `docs/temp/world-ui-2026-10-05`; user data paths are never substituted. The separately labeled task PostgreSQL container on35432 uses tmpfs/no existing volumes and has isolated configuration/tick test databases. P28 stops only these task-owned resources, preserving raw evidence and the original Docker IDs/volume.

Run product checks from this repository; run pytest from `backend` with the offline guard first on PYTHONPATH. Browser configs own the source-copy/loopback fixture contracts. Exact mode/basis commands are recorded in each lane summary. Use a fresh fixture directory for each actual Character run; retained fixture DBs are evidence, not reusable operational stores.

```powershell
$env:PYTHONPATH='D:\project_code\angmoo-workspace\angmoo-tree-angmoo\scripts\testing\offline-python;D:\project_code\angmoo-workspace\angmoo-tree-angmoo\backend'
# backend cwd
& .venv/Scripts/python.exe -m pytest tests/chat/test_world_chat_delete.py tests/chat/test_world_chat_configuration.py tests/routines/test_world_independent_autonomy.py -q
# repo cwd; individual local checkers, not a CI workflow
& backend/.venv/Scripts/python.exe scripts/ci/check_architecture_boundaries.py
& backend/.venv/Scripts/python.exe scripts/ci/check_frontend_architecture_boundaries.py
& backend/.venv/Scripts/python.exe scripts/ci/check_frontend_design_contract.py --check
& backend/.venv/Scripts/python.exe scripts/ci/check_refactor_frontend_preservation.py
& backend/.venv/Scripts/python.exe scripts/ci/check_refactor_preservation.py --contracts --nodes
```
