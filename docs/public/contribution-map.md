# Angmoo Local OSS contribution map

`angmoo-tree/angmoo` is the canonical repository for application code,
migrations, tests, documentation, and GitHub governance. Contributors work in
a fork or branch and submit a pull request. The repository owner performs the
final merge after required checks pass.

## Architecture transition

The target structure is explained by [backend ARCHITECTURE](../../backend/ARCHITECTURE.md) and [frontend ARCHITECTURE](../../frontend/ARCHITECTURE.md). [The preservation map](../architecture/refactor-feature-preservation.md) records the current migration and consumers. Only scopes listed in each architecture policy `refactor` section use the new rules. AR-1 provides checker support with no active product scopes; the pilot activates its own scope in the same change as its code. The existing locations and public/layer rules below remain valid elsewhere.

## Change locations

| Area | Primary backend | Primary frontend | Validation focus |
|---|---|---|---|
| Local identity and agents | `backend/app/api`, `backend/app/services` | `frontend/src/app/agents` | ownership, sessions, limits |
| World and Studio | World routes/services/models | `features/device-home`, `features/creator-studio`, `features/world-app` public entries plus legacy World routes | schema, migration, package boundary |
| Routine runtime | `app.domains.routine_posts.public` contracts + `app.runtime.routine_posts` SQLAlchemy orchestration | agent activity surfaces | deterministic tick, duplicate write |
| SNS and Inbox | `app.domains.social.public` contracts + `app.runtime.social` SQLAlchemy read/write/Inbox adapters | `features/social/public.ts` | event ordering, observation receipt, relationship direction |
| Relationship graph | `app.domains.relationships.public` + domain-owned ORM definitions + `app.runtime.relationships` SQLAlchemy composition + `app.runtime.graph_projection`; LadybugDB remains the replayable adapter | `features/relationships/public.ts` | read parity, replay, outage, World isolation |
| Providers and credentials | `backend/app/providers`, `backend/app/credentials` | settings/model forms | BYOK redaction, fake provider |
| Local Bot | bot route/schema | `frontend/src/app/angmoo-api` | quota and response contracts |

Legacy frontend API calls remain behind `frontend/src/lib` only for surfaces
that have not moved yet. New product-shell
work belongs to `frontend/src/features/<feature>` and exposes only `public.ts`;
feature-local API clients stay under that feature instead of inventing backend
contracts in route components. See `docs/architecture/frontend-product-shell.md`.

## Responsibility boundaries

- Routes own authentication dependencies, HTTP input/output, public use-case
  calls, and error mapping.
- Domain public APIs and use cases own new business policy and orchestration.
- Legacy services may remain as explicitly owned composition adapters during
  staged migration, but new features do not add another horizontal service.
- Repository ports sit below use cases; CRUD and persistence adapters do not
  import policy from above or commit behind a caller.
- Provider SDK imports stay inside their adapters.
- Raw secret decryption stays inside the credential resolver boundary.
- Public read schemas never expose API keys, encrypted envelopes, or
  ciphertext.

Compatibility facades may preserve stable imports during refactoring only when
they name an owner, current consumer, removal stage, and usage-zero deletion
gate. They re-export canonical types or compose adapters; they do not duplicate
use-case logic. T2.5 PR C removed the unused relationship schema and repository
aliases after both `rg` and the AST inventory reported zero importers. L4 PR E
removes the horizontal relationship graph/event/model/CRUD bridges. L4 PR F
removes the temporary manual-social facades and the domain-internal routine
SQLAlchemy runtime after their consumer count reaches zero. Runtime consumers
now enter through the social or relationships public boundary and the isolated
runtime SQLAlchemy composition, routine-post, and graph-projection boundaries.
Do not combine a move with unrelated behavior changes.

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
