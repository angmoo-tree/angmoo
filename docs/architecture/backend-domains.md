# Backend domain map and import contract

The current backend uses `app/domains/<domain>/<role>`. Read [Backend ARCHITECTURE](../../backend/ARCHITECTURE.md) first to understand functionality and code placement; this document explains **checked boundaries and the meaning of exceptions**. Current contributor rules do not require `public.py`, `application`, `ports`, or `infrastructure` in every domain.

The [compatibility contract](backend-compatibility.md) records actual consumers and reasons for supported historical imports. Do not apply a target directory structure from historical documents as a current contributor rule.

## Domains and responsibilities

Current domain owners are `identity`, `characters`, `worlds`, `world_characters`, `device_home`, `world_packages`, `social`, `relationships`, `routines`, `routine_posts`, `chat`, `memory`, `runtime`, `local_bot`, `character_lore`, `media`, `tree`, and `operations`. When adding a domain, describe its actual functionality and callers and register its ownership scope. Domains do not all need the same file set.

- `router` owns HTTP input/output and error conversion. `service` owns authorization and state transitions shared by HTTP and workers.
- `service` owns execution order and persistence boundaries. Extract SQL into `repository` when useful. Preserve the shared Session and existing commit/rollback contracts.
- `models` contains the owning domain's ORM models; `schemas` defines input/output shapes. Shared `app.models` provides one Base without importing domain models back into it.
- Use `contracts`, `policies`, `utils`, `exceptions`, and `constants` for actual values, decisions, errors, and helpers. Pure decisions do not perform DB, HTTP, or SDK work.

## Using another domain's capabilities

Use supported `service`, `schemas`, and `contracts` explicitly from their owning paths. If a nested module is exposed as a contract, record its exact path in the policy's `entries`. Do not use wildcards that automatically expose siblings or every descendant. Reviewed error types can also be exposed as exact entries.

Do not directly import another domain's `models`, `repository`, or `router` to bypass its state-transition, authorization, or persistence contracts. Compose specific cross-domain reads or shared-transaction work in top-level `app/runtime`. Domains do not import runtime in return to find services.

Circular imports, services calling their own routers, and shared Base/error/utility code importing product domains are prohibited. `main` creates and wires the app and runtime. `integrations` owns shared communication/SDK wiring; domain `client` modules own business-specific requests and responses; `providers` owns the shared Gemini generation/embedding adapter, contracts, and registry; `credentials` handles credential resolution.

## Files and checks

| File | Meaning |
| --- | --- |
| `security/architecture_import_baseline.json` | Reproducible inventory of current Python files, import edges, and external imports |
| `security/architecture_import_policy.json` | Domain ownership, roles, exact supported entries, and required retained contracts |
| `scripts/ci/generate_architecture_inventory.py` | Generates the inventory from current code and detects stale output |
| `scripts/ci/check_architecture_boundaries.py` | Checks direction, roles, cycles, exceptions, and file placement in completed scopes |
| `scripts/ci/check_refactor_preservation.py` | Tool for investigating historical migration evidence when needed; not a routine CI requirement to reproduce old source bodies |

The policy's domain catalog and full boundaries apply to current source. Do not hide a new dependency behind an exception that checks only selected files. New domains and unused old-layer files are also checked; a file without imports does not pass merely because it lacks edges. Removed scopes, entries, or compatibility items left in policy also cause failure.

Regenerating the import inventory updates facts, not permission rules. When a new dependency fails, inspect actual responsibility and callers. Adding an exception or supported entry does not justify exposing an entire persistence layer or disabling reverse-dependency/cycle checks.

World-specific character settings use immutable import values in `characters.contracts` and baseline
validation/creation services in `characters.service.import_snapshots`. Characters owns the source, digest,
and registration transaction for initial-creation and existing-character transition baselines. Reviewed
errors in `characters.exceptions` are exposed as exact entries. Read saved World values through
`world_characters.contracts.configuration` and `world_characters.service.configuration`. Chat, Social,
and Routine retain the accepted revision of this read contract. World schemas do not import Routine
policy directly. Actual Runtime composition connects active hours, credentials, slots, and Media validation
to their owning policies. These paths do not expose all models/repositories or permit circular imports.

## Required retained paths

The [compatibility contract](backend-compatibility.md) records exact consumers, concrete implementations, and reasons for schema helpers used by historical migrations and imports used by supported Hosted extensions. Policy `retained_modules` permits those files to exist; it does not exempt their imports from ordinary boundary checks. New product code uses the actual owning role.

Remove temporary domain aggregates and forwarding services after migrating consumers and validating original objects/behavior. Do not recreate empty files or equivalent forwarding classes merely to claim removal. `public_main.py` functionality is inherited by the single app-creation implementation in `app/main.py`, distinct from historical migration aliases.

## Validation

Run domain regressions and architecture checks relevant to the contribution. Shared DB, app-creation, and packaging changes require broader coverage of affected consumers and supported runtimes. Required remote scope follows the [CI policy](../operations/ci-validation.md). When moving tests, verify one-to-one correspondence with existing cases and update collection, fixtures, and CI commands. Do not report a pass when pytest collected no tests because an old path disappeared.

SQLite is canonical; FTS5 and LadybugDB are rebuildable derived data. Historical PostgreSQL/Neo4j material is historical or static comparison evidence. A string match does not make a file disposable; inspect its actual runtime, migration, or fixture role.
