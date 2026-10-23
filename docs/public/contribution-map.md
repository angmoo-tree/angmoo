# Contribution map

`angmoo-tree/angmoo` is the canonical repository for application code,
migrations, tests and documentation. Use the actual owner files shown below;
the architecture guides describe their permitted dependencies.

| Area | Backend owner | Frontend owner | Verification focus |
| --- | --- | --- | --- |
| Local identity | `domains/identity` | `features/identity`, composition providers | sessions, local owner, stop/resume, privacy |
| Characters | `domains/characters`, `world_characters` | `features/characters`, Creator Studio composition | creation, import, configuration, scope |
| Worlds and packages | `domains/worlds`, `world_packages`, `device_home` | corresponding features and composition screens | atomic import, owner binding, exclusions |
| SNS and Feed | `domains/social`, `runtime/social` | `features/social` | root pages, replies, confirmed writes, evidence |
| Autonomous activity | `domains/routines`, `routine_posts`, runtime graph/resident | activity settings and status composition | lease, tick, cancellation, result recovery |
| Chat | `domains/chat`, `runtime/chat` | `features/chat` | bounded history, gaps, stream, accepted request identity |
| Memory | `domains/memory`, `runtime/memory` | `features/memory` | canonical scope, retrieval, preparation, cleanup |
| Relationships | `domains/relationships`, `runtime/relationships` | `features/relationships` | activation, evidence, direction, projection replay |
| Media and providers | media/identity owners, `integrations`, `providers` | media/settings features | credentials, request limits, unknown outcomes |
| Local Bot | `domains/local_bot` | support/API guide surfaces | token scope, documented API, quotas |
| Data and startup | `runtime/persistence`, `runtime/migrations`, `main.py` | runtime/native providers | generation, preservation, startup/shutdown |
| Termux | `launcher/termux` and service log policy owners | public install guides | image identity, data isolation, logs and expiry |
| Windows packaging | `desktop`, build/release scripts | static frontend | native lifecycle, installer identity and recovery |

Domain and runtime paths are relative to `backend/app`; feature and composition
paths are relative to `frontend/src`. `launcher/termux` and `desktop` are relative
to the repository root.
The map is a starting point, not permission to import another owner's storage.
Use [Backend Architecture](../../backend/ARCHITECTURE.md) and
[Frontend Architecture](../../frontend/ARCHITECTURE.md).

## Dependency rules

Backend runtime composes concrete cross-domain collaboration. Domain services
retain authorization, state transitions and transaction ownership. Share only
explicit supported entries; do not force a new `public/application/ports` chain.

Frontend composition connects features through props, callbacks and slots.
Features import concrete role files and common code, not sibling feature
internals. Retired facades and former partial migration scopes are not extension
points. Next and static use the same feature components.

## Verification and delivery

Select local checks from the actual changed behavior and its consumers.
[CI validation](../operations/ci-validation.md) owns the conservative remote
selection and required checks. A selected narrow or not-applicable result
must not be described as full validation. Public checks use synthetic data and
fake providers.

Changes to authorization, credentials, retry/lease behavior, migrations or public
API contracts need focused negative cases and preservation/recovery notes.
Build, installer and platform changes also need their actual consumer checks.

Use [CONTRIBUTING](../../CONTRIBUTING.md) for Issues, DCO and PR review. Merge,
release candidate validation, publication and real user checks remain separate.
