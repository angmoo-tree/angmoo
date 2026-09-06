# Backend guide

`app.main:public_app` is the public FastAPI ASGI export. The official contributor
and installed sidecar launchers prepare their embedded data and pass explicit
runtime configuration to `app.main.create_public_app`. This selects the public
profile of the single factory in `app/main.py`. Public routes include auth,
characters, World surfaces, resident runs, Local Bot, social, Chat, Memory, lore,
and Tree. Private admin, maintenance, and agent-tools operations are not
registered.

The generated `/openapi.json` is the canonical REST contract. Domain routers
parse requests, use authentication dependencies, and convert responses and
errors. Domain services own authorization, business flow, and transaction
participation. Persistence stays with that domain's service or repository;
multi-owner runtime collaboration preserves the caller's Session and existing
commit/rollback contract. See [Backend Architecture](../../backend/ARCHITECTURE.md)
for actual role locations.

SQLite is the canonical Local store. Supported schema upgrades use the explicit
embedded SQLite migration chain under `app/runtime/migrations`, with generation
validation and failure recovery. Historical PostgreSQL Alembic revisions remain
unchanged as provenance; they are not the Local bootstrap or a second runtime
migration chain. Preserve existing revision and embedded migration bodies, and
verify supported predecessor upgrades when adding a schema change. See
[Local runtime](local-runtime.md) and [Contributor development](development.md).

Run focused tests first, then the complete public suite. Network-facing
provider behavior must be represented by a fake or mock in contributor CI.
