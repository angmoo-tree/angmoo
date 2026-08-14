# Backend domain map and import contract

This document is the contributor-facing architecture contract for Angmoo's
incremental domain-first refactor. It describes the target direction; it does
not claim that every legacy module has already moved.

The T2.5 umbrella proposal is
[`#32`](https://github.com/angmoo-tree/angmoo/issues/32). The architecture
baseline was reconfirmed from `main` commit
`16fe1b58c34bfac7e0f94cf449d8078bba98d1b2`.

## Facts, policy, and enforcement

These files have deliberately separate responsibilities:

| File | Responsibility |
|---|---|
| `security/architecture_import_baseline.json` | Deterministic facts about every `backend/app` Python module and import edge |
| `security/architecture_import_policy.json` | Target direction, exact legacy exceptions, owners, removal conditions, and review dates |
| `scripts/ci/generate_architecture_inventory.py` | Reproduce the facts without network or provider calls |
| `scripts/ci/check_architecture_boundaries.py` | Enforce policy, cycles, and no-growth rules |

At the PR A baseline the precise inventory contains 246 modules, 595 internal
edges, and 1,030 unique per-module external import records. The previous T2
inventory reported 426 internal edges because `from package import module`
was recorded only as the package; inventory schema v2 resolves the real module
when it exists.

The policy freezes 392 exact imports into the horizontal legacy prefixes
`app.cruds`, `app.models`, `app.schemas`, and `app.services`. Existing edges may
only disappear. Updating the inventory cannot silently authorize another
legacy edge.

## Target tree

Only packages used by the current migration stage are created. Empty future
packages are not pre-created.

```text
backend/app/
├── core/                     # configuration, DB and common primitives
├── domains/
│   ├── identity/
│   ├── worlds/
│   ├── characters/
│   ├── activities/
│   ├── social/
│   ├── relationships/
│   ├── chat/
│   ├── world_packages/
│   └── media/
├── runtime/
│   ├── resident/
│   ├── scheduler/
│   └── graph_projection/
├── integrations/
│   ├── llm/
│   ├── image/
│   └── neo4j/
├── compatibility/           # temporary facade with an owner and removal gate
└── main.py
```

## Ownership and migration stages

| Area | Stable cross-area surface | Owner stage | T2.5 state |
|---|---|---:|---|
| `core` | small primitives only | L0 | existing core is audited, not moved in PR A |
| `identity` | `app.domains.identity.public` | L1 | target only |
| resident and scheduler runtime | runtime public ports | L2 | target only |
| `worlds`, `characters`, `activities`, root posts | each domain's `public.py` | L3 | target only |
| `world_packages` | `app.domains.world_packages.public` | L3.5 | new Local feature later |
| feed and `social` | `app.domains.social.public` | L4 | target only |
| `relationships` graph read | `app.domains.relationships.public` | T2.5 pilot | PR B moves the read-only slice |
| relationships write and graph projection | domain/runtime public ports | L4 | unchanged by the read pilot |
| `chat` and chat memory | `app.domains.chat.public` | P8-L | blocked by Local transition gates |
| remaining active legacy or ownerless shim | none | L6 | final removal gate |

PR A adds the contract and checker but moves **zero product source files**.
PR B is limited to the P7 relationship graph read path. PR C removes only
imports or shims proven unused and closes the evidence loop.

## Dependency direction

```text
FastAPI route/composition
        ↓
domain public API
        ↓
domain use case
        ↓
domain model, schema, or repository port
        ↓
core primitive or integration adapter

runtime orchestration
        ↓
multiple domain public APIs + integration public ports
```

Rules for new code:

- `core` does not import domains, runtime, or concrete integrations.
- A domain may import `core` and modules inside the same domain.
- Cross-domain use goes through `app.domains.<name>.public` only.
- A domain does not import runtime, a provider SDK, or a legacy horizontal
  layer.
- Runtime composes domain public APIs and integration public ports; domains do
  not call upward into runtime.
- Integrations own transport and SDK details, not World or relationship policy.
- Routes translate HTTP input/output and errors; they do not own queries,
  provider calls, commits, or locks.
- Repositories and CRUD modules never import a use case or service above them.
- Wildcard imports and new `from app import models, schemas` dependencies are
  rejected.

Use this cross-domain form:

```python
from app.domains.relationships import public as relationships
```

Do not reach into another domain's implementation:

```python
from app.domains.relationships.graph_read.use_case import _internal_helper
```

`public.py` is a small stable surface, not a convenience re-export of every
internal name.

## Domain package vocabulary

Use names that reveal responsibility:

- `public.py`: stable names used outside the domain
- `router.py`: FastAPI router when the domain owns one
- `schemas.py`: HTTP/domain read contract owned by the domain
- `models.py`: ORM models only after their registry and migration boundary are
  ready to move
- `repository.py`: persistence/query port and result types, with no hidden
  commit
- `use_case.py` or `use_cases/`: authorization-following orchestration and
  transaction boundary
- `dependencies.py`: actual FastAPI request dependencies
- `errors.py`: stable domain errors and reason codes
- `planner.py`, `context.py`, `executor.py`, `apply.py`: explicit generation
  responsibilities

Avoid generic new `utils.py`, `helpers.py`, `common.py`, or `service.py` files
when a more precise responsibility exists.

## Transaction and provider boundary

Structural PRs do not move commit, rollback, lock, lease, idempotency, or retry
ownership. Event and Outbox writes remain in the same PostgreSQL transaction as
their canonical state. Repositories do not commit behind a caller's back.

The T2.5 pilot is read-only. It adds no migration, DB write, provider call,
prompt, model, token setting, or SocialEvent/Outbox/projector change. Tests use
synthetic PostgreSQL/Neo4j data and fake providers; real provider calls must
remain zero.

## Exact legacy disposition

The policy contains two reviewed edge groups and one exact module cycle:

| Entry | Count | Owner | Removal condition |
|---|---:|---:|---|
| pre-T2.5 horizontal imports | 390 edges | L6 fallback owner | remove each edge at its owning domain/runtime stage; none remain after L6 |
| Neo4j write-runtime command bridge | 2 edges | L4 | move projection commands and metrics behind runtime/integration public ports |
| routine/social interaction module cycle | 2 modules | L4 | split routine context and social interaction input behind public contracts |

Every exception records exact importer and imported module, a reason, owner
stage, removal condition, and review date. Wildcard prefixes are invalid. A
removed edge makes its policy entry stale and therefore fails CI until the
exception is deleted too.

## Contributor workflow

Before adding a backend feature:

1. Find the owning area in the table above.
2. Add behavior inside that area instead of creating another horizontal
   service.
3. Add the smallest stable name to the area's `public.py` only when another
   area needs it.
4. Keep persistence below the use case and provider SDKs inside integrations.
5. Run:

   ```powershell
   uv run --project backend python scripts/ci/generate_architecture_inventory.py --write
   uv run --project backend python scripts/ci/check_architecture_boundaries.py
   uv run --directory backend python -m pytest -q tests/test_t2_5_architecture_boundaries.py
   ```

6. Review the inventory diff. A new domain edge is expected only when it obeys
   the public API contract. Never add a legacy exception merely to turn CI
   green.

Checker failures include the importer, imported module, rule, expected fix,
whether an exact legacy exception exists, its owner stage, and this document.

Architecture changes use a focused Issue and PR. Do not mix product behavior,
migrations, dependency majors, provider configuration, bulk formatting,
Hosted/Private/Production settings, or unrelated frontend moves into a
structure-only PR.
