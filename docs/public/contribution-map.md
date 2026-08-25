# Angmoo Local OSS contribution map

`angmoo-tree/angmoo` is the canonical repository for application code,
migrations, tests, documentation, and GitHub governance. Contributors work in
a fork or branch and submit a pull request. The repository owner performs the
final merge after required checks pass.

## Change locations

| Area | Primary backend | Primary frontend | Validation focus |
|---|---|---|---|
| Local identity and agents | `backend/app/api`, `backend/app/services` | `frontend/src/app/agents` | ownership, sessions, limits |
| World and Studio | World routes/services/models | `features/device-home`, `features/creator-studio`, `features/world-app` public entries plus legacy World routes | schema, migration, package boundary |
| Routine runtime | routine planners/runtime | agent activity surfaces | deterministic tick, duplicate write |
| SNS and Inbox | community/social services | posts, notifications | event ordering, relationship direction |
| Relationship graph | `app.domains.relationships.public` + `app.integrations.relationship_graph_read`; the SQLAlchemy gateway remains an L4 adapter | relationship graph | read parity, replay, outage, World isolation |
| Providers and credentials | `backend/app/providers`, `backend/app/credentials` | settings/model forms | BYOK redaction, fake provider |
| Local Bot | bot route/schema | `frontend/src/app/angmoo-api` | quota and response contracts |

Legacy frontend API calls remain behind `frontend/src/lib`. New product-shell
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
aliases after both `rg` and the AST inventory reported zero importers. The
SQLAlchemy relationship gateway remains an L4-owned adapter because it still
has runtime consumers. Do not combine a move with unrelated behavior changes.

## Validation map

All PRs run these required checks: `backend`, `frontend`,
`sqlite-canonical-migration`, `local-core-smoke`, `local-autonomy-smoke`,
`local-full-graph`, `oss-boundary`, `dependency-license`, `dco`, and
`architecture-boundary`.

The required `local-core-smoke` check also builds the release Docker targets,
checks non-root and secret-layer boundaries, scans fixable high/critical
vulnerabilities, emits an SPDX JSON SBOM, and runs the clean-clone full-stack
lifecycle. The tag-only release workflow publishes to GHCR after the same Gate;
it is not an additional pull-request check.

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
