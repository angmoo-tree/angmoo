# Angmoo Local OSS contribution map

`angmoo-tree/angmoo` is the canonical repository for application code,
migrations, tests, documentation, and GitHub governance. Contributors work in
a fork or branch and submit a pull request. The repository owner performs the
final merge after required checks pass.

## Architecture transition

The current backend structure is explained by [backend ARCHITECTURE](../../backend/ARCHITECTURE.md): each business domain owns its HTTP, service, schema, model and persistence roles. The backend policy covers all domains; new code does not require a `public → application → port` chain. [The preservation map](../architecture/refactor-feature-preservation.md) connects preserved features and their current owners. [Backend results](../architecture/refactor-backend-results.md) distinguish source preparation, PR validation, merge and installer evidence.

The frontend still follows the staged scopes in its own policy and [frontend ARCHITECTURE](../../frontend/ARCHITECTURE.md). Backend completion does not complete the remaining frontend transition.

## Change locations

| Area | Primary backend | Primary frontend | Validation focus |
|---|---|---|---|
| Local identity and characters | `app/domains/identity`, `app/domains/characters`; cross-owner lifecycle in `app/runtime/characters` | `frontend/src/app/agents` | ownership, sessions, limits |
| World and Studio | `app/domains/worlds`, `world_characters`, `device_home`, `world_packages` | `features/device-home/{api,components,types,utils}`, `composition/screens/device-home-screen.tsx`, remaining Creator Studio/World App public entries and legacy World routes | schema, migration, package boundary, Next/static shared screen |
| Routine runtime | `app/domains/routines`, `routine_posts`; worker composition in `app/runtime/resident`, `routine_posts` | agent activity surfaces | deterministic tick, duplicate write |
| SNS and Inbox | `app/domains/social/{service,repository,schemas,models}` and router; cross-owner collaboration in `app/runtime/social` | `features/social/public.ts` | event ordering, observation receipt, relationship direction |
| Relationship graph | `app/domains/relationships` role files; `app/runtime/relationships`, `graph_projection`; replayable LadybugDB adapter | `features/relationships/public.ts` | read parity, replay, outage, World isolation |
| Chat and Memory | `app/domains/chat`, `memory`; worker/provider composition in `app/runtime/chat`, `memory` | `features/chat`, `features/memory` | request state, source scope, evidence, cancellation, budgets, shutdown |
| Providers and credentials | domain `client` files, `app/integrations`, `app/providers`, `app/credentials` | settings/model forms | BYOK redaction, fake provider |
| Local Bot | `app/domains/local_bot` and runtime collaboration | `frontend/src/app/angmoo-api` | quota and response contracts |
| App, DB and installation | `app/main.py`, `app/models.py`, `app/database.py`, `app/runtime/persistence`, `migrations` | runtime/desktop shell | same Base/Session, supported upgrades, startup and shutdown |

Legacy frontend API calls remain behind `frontend/src/lib` only for surfaces
that have not moved yet. New product-shell work belongs to
`frontend/src/features/<feature>` and consumers import the concrete role file.
Feature-local API clients stay under that feature instead of inventing backend
contracts in route components. A temporary `public.ts` is allowed only for
named unmigrated consumers with a removal stage; Device Home currently keeps
four such API/type consumers and does not export its composition screen. See
`docs/architecture/frontend-product-shell.md`.

## Responsibility boundaries

- Routers own HTTP input/output, authentication dependencies, service calls
  and HTTP error mapping.
- Domain services own business policy, authorization, state transitions and
  transaction participation. HTTP and workers reuse those same decisions.
- Models, schemas and persistence stay with their business owner. A repository
  isolates SQL when useful; it does not open another Session or commit behind
  its caller.
- Other domains consume explicit supported service/schema/contract entries.
  Multi-owner SQL and lifecycle collaboration belongs to runtime composition;
  domain code does not import that runtime to locate services.
- Provider SDK imports stay inside their adapters.
- Raw secret decryption stays inside the credential resolver boundary.
- Public read schemas never expose API keys, encrypted envelopes, or
  ciphertext.

The remaining [historical and extension compatibility paths](../architecture/backend-compatibility.md)
have exact consumers and reasons: immutable migration helpers and supported
separately deployed Hosted extension imports. They do not require new business
code to pass through an old aggregate. The checker rejects unregistered old
layers even when no file imports them. The original source/test/API/ORM
evidence remains immutable, and supported installer upgrades verify the
historical data path. Do not combine a move with unrelated behavior changes.

## Validation map

All PRs run these required checks: `backend`, `frontend`,
`embedded-data-migration`, `local-core-smoke`, `local-autonomy-smoke`,
`local-full-graph`, `oss-boundary`, `dependency-license`, `dco`, and
`architecture-boundary`.

The required `local-core-smoke` check also builds the release Docker targets,
checks non-root and secret-layer boundaries, scans fixable high/critical
vulnerabilities, emits an SPDX JSON SBOM, and runs both the production Browser
and contributor-development container lifecycles from a fresh clone detached at
the exact source SHA. These are Hosted TECH checks built from PR source. The
documented default Browser command remains a USER Gate for the separately
approved matching published image. The tag-only release workflow publishes to
GHCR after that release approval; it is not an additional pull-request check.

`windows-local-smoke` and `codeql` remain advisory checks. They are triaged
rather than silently ignored and are promoted only after their deterministic
contract is stable.

Use synthetic users and fake providers. Contributor SQLite/LadybugDB fixtures
are disposable; production credentials, user data, and external LLM calls are
not allowed. PostgreSQL runtime and offline import are unsupported; Neo4j
remains static parity evidence only. Changes to REST/OpenAPI, SQLite
migrations, routine/social/graph state,
authorization, credentials, or retry/lease behavior require focused contract
tests and a rollback note.

## Issue and PR flow

Features, bugs, and structural changes should start with an Issue. Small docs
and typo fixes may submit a PR directly. Link an existing Issue with
`Closes #number` or an explicit reference. Every change still uses a PR and
applicable required checks; Issue linkage itself is not a merge gate.
