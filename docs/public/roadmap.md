# Project direction

Angmoo 0.1.0 is available for Windows x64 and Docker amd64/ARM64, with
experimental Android ARM64 support through Termux and PRoot. See
[the release](https://github.com/angmoo-tree/angmoo/releases/tag/release-v0.1.0)
and [installation guide](../../README.md) for current functionality.

Areas worth discussing for future work include:

- clearer Chat, Feed, memory and relationship experiences;
- reliability, diagnostics and resource use during longer local sessions;
- platform compatibility and data-preserving updates;
- accessibility and English/Korean documentation;
- carefully scoped provider and integration improvements.

These are discussion areas, not promised versions, dates or supported features.
Implementation decisions belong in reviewed Issues and pull requests. The
supported runtime remains embedded SQLite with search and graph projections;
this page does not promise PostgreSQL, Neo4j, federation or horizontal scaling.

Start with [where to contribute](where-to-contribute.md) and describe a concrete
user problem before proposing additional infrastructure.
