# Project direction

The latest published SQLite baseline, Angmoo 0.1.3, is available for Windows x64 and Docker amd64/ARM64, with
experimental Android ARM64 support through Termux and PRoot. See
[the release](https://github.com/angmoo-tree/angmoo/releases/tag/release-v0.1.3)
and [installation guide](../../README.md) for current functionality.

Areas worth discussing for future work include:

- clearer Chat, Feed, memory and relationship experiences;
- reliability, diagnostics and resource use during longer local sessions;
- platform compatibility and data-preserving updates;
- accessibility and English/Korean documentation;
- carefully scoped provider and integration improvements.

These are discussion areas, not promised versions, dates or supported features.
Implementation decisions belong in reviewed Issues and pull requests. The
0.1.4 source implements local PostgreSQL, pgvector exact search and preserved
LadybugDB projections. Its migration input is the published 0.1.3 SQLite format.
Source implementation does not mean that a 0.1.4 Release has been published.
See the [runtime](postgresql-runtime.md), [migration](postgresql-migration.md) and
[backup](postgresql-backup.md) guides. Neo4j, federation and horizontal scaling
remain separate proposals.

Start with [where to contribute](where-to-contribute.md) and describe a concrete
user problem before proposing additional infrastructure.
