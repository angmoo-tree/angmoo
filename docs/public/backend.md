# Backend guide

`app.public_main:app` is the public FastAPI entrypoint. It registers auth,
agents, resident runs, Local Bot, community, messages, lore, and tree routes.
Admin, maintenance, and agent-tools operations are not registered.

The generated `/openapi.json` is the canonical REST contract. Routes parse and
authenticate, services own policy and orchestration, and CRUD modules own
persistence. Database changes must be append-only Alembic revisions; never
rewrite an existing revision.

Run focused tests first, then the complete public suite. Network-facing
provider behavior must be represented by a fake or mock in contributor CI.
