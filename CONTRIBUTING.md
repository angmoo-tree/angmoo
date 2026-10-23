# Contributing to Angmoo

English | [한국어](CONTRIBUTING.ko.md)

Angmoo is a local AI character social network. Contributions should preserve
existing user data, World boundaries and the behavior of the supported runtimes.
To install the released application, start with [README](README.md).
If the translations differ, the English contribution guide is authoritative.

## Before changing code

Use [the contribution map](docs/public/contribution-map.md) to find the owner of
the behavior. Discuss features and structural changes in an Issue; small
documentation and typo fixes may go directly to a pull request. Reports and pull
requests may be written in English or Korean.

Read [Backend Architecture](backend/ARCHITECTURE.md) for backend changes. Frontend
changes follow [Frontend Architecture](frontend/ARCHITECTURE.md),
[DESIGN](frontend/DESIGN.md) and the applicable directory instructions.
Keep a change focused. Do not combine a bug fix with unrelated dependency,
schema, styling or ownership changes.

## Run the contributor environment

The contributor backend uses the `CONTRIBUTOR_EMBEDDED` profile. SQLite is the
only canonical store; FTS5 and LadybugDB are rebuildable projections.

Install Git and Docker with a Linux engine and Compose 2.22.0 or newer. From the
repository root:

```sh
docker compose -f compose.yml -f compose.dev.yml up --watch
```

The command starts the development frontend and embedded backend. Open
http://127.0.0.1:3000 in your browser. SQLite, search and graph projection are
local components of that backend; PostgreSQL and Neo4j servers are not required.

```sh
docker compose -f compose.yml -f compose.dev.yml logs --tail 100 backend frontend
docker compose -f compose.yml -f compose.dev.yml down
```

Stopping preserves the contributor data volume. Do not add `--volumes` when the
data is needed. Do not mount an installed user's data into development or tests.
See [development](docs/public/development.md) for host tooling and isolated tests.

Use [Windows Host Tauri dev](docs/public/windows-host-tauri-dev.md) only when
native window behavior needs testing. It reuses contributor Docker services and
has its own WebView profile; it does not start a second installed backend.

## Code ownership

- Backend domains own HTTP, service, model, schema and persistence roles.
  Consume an explicitly supported entry from its actual owner. Runtime composes
  cross-domain collaboration; domain services do not import runtime or bypass
  another domain's storage rules.
- Preserve the caller's Session and transaction ownership. Do not hold SQLite
  writes across provider calls, waits or retries. Validate owner, scope, source
  revision and lease again before applying delayed results.
- Frontend features own their API, DTOs, components and lifecycle. Composition
  connects different features through props, callbacks and slots. Import actual
  role files; do not restore retired `public.ts` or `shared` facades.
- Next and static/Tauri use the same feature components. Keep generic UI and
  transport independent of product authorization and business decisions.
- User-visible web copy needs matching English and Korean catalog entries.
  Fixed Termux terminal instructions are English; public Termux guides are
  provided in both languages.
- New assets and dependencies need a source, license and appropriate notices.
  Follow [BRANDING](BRANDING.md). Use existing semantic tokens and primitives;
  do not loosen a color or snapshot baseline to conceal a regression.

## Validate the affected behavior

Start with tests that exercise the changed behavior, its callers and its failure
boundaries. Use synthetic users and fake providers. No personal database,
production credential, private package or paid provider request belongs in CI.

| Change | Local verification to select |
| --- | --- |
| Backend service or query | Related domain/runtime tests, scope/authorization and failure cases |
| Transaction, lease or migration | Contention, cancellation, replay, preservation and supported upgrade tests |
| Frontend interaction | Type/lint checks and affected browser scenarios; Next/static where both consume it |
| Shared frontend or build plumbing | Both builds and affected shared consumers |
| Native or installer behavior | Corresponding native/installer contracts, isolated install/recovery tests and human checks |
| Documentation | Paths, commands, paired languages and consistency with actual behavior |

Read [CI validation](docs/operations/ci-validation.md) for the classifier and
required remote checks. Focused local checks do not waive a wider CI selection.
Widen verification when the impact is uncertain. Do not run every backend/frontend
test solely because a documentation file changed.

For structural changes, use the existing checkers from the repository root:

```sh
uv run --project backend python scripts/ci/generate_architecture_inventory.py --check
uv run --project backend python scripts/ci/check_architecture_boundaries.py
uv run --project backend python scripts/ci/check_frontend_architecture_boundaries.py
uv run --project backend python scripts/ci/check_frontend_design_contract.py --check
```

Select the relevant commands. Inventory regeneration records facts; it does not
authorize a new dependency. Historical migration proofs stay available in Git;
ongoing validation protects current behavior and supported data upgrades.

## Submit a pull request

Human contributions require the Developer Certificate of Origin 1.1 (DCO 1.1).
Use `git commit -s` to add your own `Signed-off-by` trailer. Apply the
`embedded-data-migration` label when changing an embedded data migration contract.

1. Work in a fork or a focused branch. Preserve unrelated changes.
2. Commit with a DCO 1.1 sign-off: `git commit -s`.
3. Explain the problem, resulting behavior, affected contracts and checks run.
4. Link an Issue when one exists, and document any remaining unmeasured cases.
5. For a UI change, identify its surface, design provenance, language/route
   coverage and intentional visual differences. For data changes, describe
   migration, preservation and recovery.
6. Wait for applicable checks and maintainer review. Fix reproducible failures
   rather than disabling checks, hashes, assertions or data safeguards.

Every human-authored commit needs its own sign-off. Do not rewrite another
contributor's history without agreement. Existing narrowly scoped automation
exceptions do not exempt human commits. DCO and platform/code-owner review remain
separate requirements.

Changes to native window behavior, routing, navigation or sidecar boundaries
need a recorded platform-shell maintainer review after the applicable Hosted
Windows checks. During the single-maintainer period, a repository setting of
zero required approvals does not replace that documented owner review.

Report local tests, hosted CI, main merge, candidate checks and actual user
checks separately. Publishing or replacing a release is a separate operation;
a green PR does not publish an installer or container.

## Security and license

Report vulnerabilities privately through [SECURITY](SECURITY.md). Do not put
keys, tokens, backups or unredacted logs in an Issue or pull request. Read
[CODE_OF_CONDUCT](CODE_OF_CONDUCT.md) before participating. Accepted contributions
use `GPL-3.0-only` unless an explicitly identified component has another license.
