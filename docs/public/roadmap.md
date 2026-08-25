# v0.3 roadmap

The historical public `v0.3.0` target was a reproducible local-owner experiment
with LangGraph/direct, Gemini, PostgreSQL+pgvector, persistent runtime secrets,
owner-scoped BYOK, and fake-provider CI. The current canonical runtime is
SQLite/FTS5 plus LadybugDB with in-process scheduler/projector; PostgreSQL and
Neo4j are not supported runtime or migration inputs.

Possible post-v0.2 work includes horizontal scaling, worker separation,
federation, broader hosted parity, and additional provider support. These are
directions, not current compatibility or support promises.
