# Angmoo Backend Architecture

English | [한국어](ARCHITECTURE.ko.md)

Angmoo's backend is a **FastAPI application organized by business domain, with HTTP handling, workflows, persistence, and input/output formats separated within each domain**. Start in `social` for post issues, `chat` for conversation issues, and `memory` for memory issues. Within a domain, names such as `router`, `service`, `repository`, `models`, and `schemas` describe each part's responsibility.

This guide explains **which domain and file to change, and which dependency, data, and execution contracts to preserve** when adding a feature or fixing a bug. It distinguishes the current structure from optional examples. Release-specific test results and progress reports are not architectural rules.

The domain-oriented layout draws on [FastAPI Best Practices](https://github.com/zhanymkanov/fastapi-best-practices#project-structure). Angmoo's counterpart to the reference's `src/auth` is `app/domains/identity`. Local execution and AI workloads also require distinct responsibilities in `runtime`, `integrations`, and `credentials`.

## How Angmoo applies the reference architecture

| Reference principle | Angmoo's implementation | What is not adopted |
| --- | --- | --- |
| Group by business domain rather than file type | `app/domains/identity`, `social`, `chat`, `memory`, and other domains | Global router, service, or model folders that collect every domain |
| Separate router, schema, service, and model responsibilities within a domain | The role tables and current file/package examples below | A requirement to create the same files in every domain |
| Make collaboration between domains explicit | Import supported services, schemas, and contracts from their owning modules | Arbitrary access to another domain's internal SQL or models |
| Separate HTTP wiring from business decisions | Routers and dependencies connect to services; requests and workers share validation | Authorization enforced only in HTTP handlers, allowing workers to bypass it |
| Make external I/O boundaries explicit | Domain clients, `integrations`, `providers`, and `runtime` composition | Wholesale adoption of the reference project's providers, deployment, or dependency tools |

Angmoo extends this layout for local data, autonomous activity, and AI processing.
`runtime` connects services and resource lifetimes; `integrations` owns technical transport and conversion;
`credentials` connects existing credential contracts. Local persistence uses PostgreSQL and the versioned schema in `runtime/persistence/postgresql_schema.py`.
SQLite is read only by the supported 0.1.3 offline migration path and compatibility tests. The reference's Alembic examples are not installation steps for Angmoo users.

### Reading order

1. Use §1 to identify the symptom and owning domain.
2. Use the current tree, role tables, and domain catalog in §2–4 to choose the change location.
3. Check call, dependency, transaction, and AI boundaries in §5–9.
4. Read §10 onward for the relevant execution, persistence, retrieval, shutdown, and validation contracts.

## 1. Where to start

Investigate in this order: **domain → responsibility → actual callers and tests**.

| Symptom | Starting point | Also check |
| --- | --- | --- |
| Posts from another World are visible | `domains/social/service/`, `repository/` | Current actor and World permissions, ordering, and pagination |
| A late Chat response is saved after cancellation | `domains/chat/service/generation.py` | Request state, lease, version, and the result-application transaction |
| A deleted memory remains in search results | `domains/memory/service/`, `repository/` | Canonical state, search indexes, and validation immediately before returning results |
| Autonomous activity runs twice | `domains/routines/service/`, `runtime/resident/` | Tick identity, claims, restarts, and retries |
| An API field or HTTP error differs from its contract | The domain's `schemas` and `router` | Response models, nullability, status codes, and error conversion |
| Only the installed app cannot open its database | `runtime/persistence/`, `runtime/migrations/` | Actual data paths, upgrades, and bundled resources |
| An AI response cannot be parsed | `integrations/llm/`, `providers/gemini.py`, and the domain parser | Provider format, allowed schema, timeouts, and call counts |

For duplicate memories, inspect Memory's canonical source identifier, job identity, conditional writes, and transaction before hiding duplicate rows in the UI. Check whether HTTP requests and workers enter the same service.

## 2. Project structure

Use the overall layout to locate domains and execution boundaries, then use the domain and integration examples to locate file responsibilities. **§2.1 lists current tracked paths**; §2.2–2.3 contain explicitly labeled examples. An omission does not mean other files are absent, and an example is not an instruction to create every listed file.

### 2.1 Current structure and file responsibilities

```text
backend/
├── app/
│   ├── domains/                   # Owners of domain code, data, and rules
│   │   ├── identity/              # Login, sessions, owner and credential policy
│   │   ├── characters/            # Character definitions, personas, Creator
│   │   ├── worlds/                # World definitions, membership, banners
│   │   ├── world_characters/      # Participation, profiles, routine creation and approval
│   │   ├── device_home/           # Local World list and Home/Studio entry
│   │   ├── world_packages/        # Package contracts, validation, export/import
│   │   ├── social/                # Posts, replies, Feed, Inbox
│   │   │   ├── router.py          # HTTP entry points for this domain
│   │   │   ├── dependencies.py    # Authentication, Session, service wiring
│   │   │   ├── schemas/           # Request and response formats
│   │   │   ├── models/            # Owned tables and relationships
│   │   │   ├── service/           # Business decisions, ordering, persistence boundaries
│   │   │   ├── repository/        # Extracted SQL queries and writes
│   │   │   ├── contracts/         # Domain values, results, collaborator types
│   │   │   ├── policies/          # Business decisions without I/O
│   │   │   ├── utils/             # Small domain-local conversions
│   │   │   ├── constants.py       # Domain constants
│   │   │   └── exceptions.py      # Domain errors
│   │   ├── relationships/         # Relationship events, candidates, graph query policy
│   │   ├── routines/              # Autonomous plans, slots, ticks, activity records
│   │   ├── routine_posts/         # Autonomous writing context, generation, provenance
│   │   ├── chat/                  # Conversations, recall, generation, streaming
│   │   ├── memory/                # Memories, source revalidation, review, recall
│   │   ├── runtime/               # Meaning of runtime state and lease rules
│   │   ├── local_bot/             # Local Bot authentication and supported actions
│   │   ├── character_lore/        # Reference documents, chunks, retrieval
│   │   ├── media/                 # Assets, recognition, World image policy, shared contracts
│   │   ├── tree/                  # Tree board
│   │   └── operations/            # Existing operational settings
│   ├── config.py                  # Shared environment configuration
│   ├── models.py                  # Single ORM Base
│   ├── database.py                # Engine and session creation and wiring
│   ├── exceptions.py              # Shared errors
│   ├── pagination.py              # Shared cursor byte conversion
│   ├── main.py                    # App/lifespan creation and service wiring
│   ├── api/                       # Shared HTTP wiring and route composition
│   │   ├── v1/                    # Existing URL groups and route registration
│   │   └── schemas/               # HTTP responses combining domains
│   ├── runtime/                   # Execution, cross-domain collaboration, startup/shutdown
│   │   ├── persistence/
│   │   │   └── model_registration.py # Model registration for the app and migrations
│   │   ├── migrations/            # Embedded upgrades of installed data
│   │   ├── chat/
│   │   │   └── message_composition.py # Chat services and concrete collaborators
│   │   ├── memory/                # Memory services, storage, worker wiring
│   │   ├── autonomous_activity/   # SNS LangGraph, lanes, checkpoints, ports
│   │   ├── resident/              # Scheduler, leases, lane execution, recovery
│   │   ├── relationships/         # Relationship policy, review, concrete wiring
│   │   ├── media/                 # Media storage, jobs, configuration wiring
│   │   ├── diagnostics/           # Bounded runtime diagnostics and observation wiring
│   │   ├── routines/              # Concrete references for planning services
│   │   ├── world_packages/        # Cross-domain export/import wiring
│   │   ├── graph_projection/      # Execution wiring for the derived relationship graph
│   │   ├── bootstrap/             # Local preparation and owned resource setup
│   │   ├── desktop_sidecar.py     # Installed-app sidecar entry and communication lifetime
│   │   ├── contributor_backend.py # Contributor Docker backend entry
│   │   ├── service_log_policy.py  # Service log policy and temporary detailed mode
│   │   ├── account_deletion.py    # Cross-domain deletion composition
│   │   └── ...                    # Other runtime code follows its collaborating domains
│   ├── integrations/              # External communication, media conversion, SDK wiring
│   │   ├── direct_llm.py          # Shared LLM calls and call tracing
│   │   ├── provider_http.py       # Provider HTTP connection utilities
│   │   ├── bounded_http.py        # Bounded HTTP I/O
│   │   ├── google_identity.py     # Google identity integration
│   │   ├── replicate_image.py     # Image integration implemented in a single file
│   │   ├── pollinations_image.py
│   │   ├── llm/                   # Task-specific LLM adapters
│   │   │   ├── character_response_generator.py
│   │   │   ├── memory_selection.py
│   │   │   └── ...
│   │   ├── media/
│   │   │   ├── images.py          # Image conversion and I/O
│   │   │   └── files.py           # Media file handling
│   │   └── ...                    # See §6.1 for integration package examples
│   ├── providers/
│   │   ├── contracts.py           # Shared generation/embedding requests, results, errors
│   │   ├── gemini.py              # Shared Gemini adapter
│   │   ├── registry.py            # Concrete provider selection
│   │   └── fake.py                # Deterministic test provider
│   ├── credentials/               # Shared credential wiring and supported contracts
│   │   ├── contracts.py
│   │   ├── resolver.py
│   │   └── service_images.py
│   ├── core/                      # Shared security, concurrency, small infrastructure tools
│   │   ├── security.py
│   │   ├── redaction.py
│   │   ├── search_text.py
│   │   └── ...
│   └── contracts/                 # Value contracts shared by domains
├── alembic/
│   ├── env.py
│   └── versions/                  # Preserved historical revisions and revision graph
├── tests/
│   ├── identity/
│   ├── characters/
│   ├── social/
│   ├── chat/
│   ├── memory/
│   ├── runtime/
│   ├── integrations/
│   ├── migrations/
│   └── conftest.py
├── ARCHITECTURE.md
├── pyproject.toml
├── uv.lock
├── .python-version
├── .env.example
├── logging.ini
└── alembic.ini

Repository root/
├── .gitignore
├── scripts/ci/
├── security/
└── .github/workflows/
```

`social` illustrates the current separation of responsibilities within a domain. Other domains follow the same ownership principles but use different depths of files and packages. Some integrations, such as `replicate_image.py`, are single files. Do not move existing files wholesale to match the expansion examples below.

### 2.2 Files that may belong inside a domain

This is **an example of responsibilities**, not a required file list. Replace `<domain>` with an actual domain such as `characters`, `social`, or `chat`. Keeping `utils.py`, `config.py`, or `client.py` directly inside the domain is also valid.

```text
app/domains/<domain>/
├── __init__.py          # Package setup
├── router.py            # HTTP routes, input/output, error conversion
├── schemas.py           # Request/response formats and value validation
├── dependencies.py      # Authenticated actor, request Session, service wiring
├── service.py           # Business decisions, execution order, persistence boundaries
├── repository.py        # Owned SQL extracted when useful
├── models.py            # Domain ORM tables and relationships
├── client.py            # Domain-specific external request context and response interpretation
├── contracts.py         # Domain values, commands, results, collaborator types
├── policies.py          # Business decisions without DB or HTTP access
├── config.py            # Domain-specific configuration
├── constants.py         # Domain constants and stable codes
├── exceptions.py        # Meaningful domain errors
└── utils.py             # Small conversions/helpers without business decisions
```

These files are **allowed responsibility examples, not mandatory scaffolding**. A feature with no HTTP interface may have no router, and a service may handle simple persistence directly. Create `repository`, `client`, `contracts`, `policies`, `config`, and `utils` only when there is a responsibility to separate.

Follow §3.1 when splitting a file into several files.

Keep `__init__.py` limited to package setup. Importing a module must not connect to a database, read secrets, call an external service, or start a worker. It does not need to re-export every internal module.

### 2.3 Optional areas, dependencies, and development configuration

The tracked backend currently has no `templates/` or `requirements/` directory. The following table explains **optional examples** from the reference structure. It is neither a list of current runtime requirements nor an adoption plan.

| Path | Responsibility and when to use it |
| --- | --- |
| `templates/index.html` | Example template for server-rendered HTML. `index.html` is illustrative; organize templates around actual screens and purposes. |
| `requirements/base.txt` | Runtime dependencies shared by development, production, and other environments. |
| `requirements/dev.txt` | Development dependencies, adding tests, linting, and development tools to the shared set. |
| `requirements/prod.txt` | Production dependencies, adding packages required for execution and deployment to the shared set. |

In a requirements-based layout, `dev.txt` and `prod.txt` can include the shared list with `-r base.txt`. Angmoo's current **dependency sources of truth** are `pyproject.toml` and `uv.lock`. If requirements files become necessary, decide whether to generate them from those sources or change the management approach. Do not maintain the same dependency versions manually in multiple places. An architectural example alone does not change installation commands, build commands, or dependency management.

Wire a new server-rendered feature at its HTTP boundary. This example does not move screens owned by Next.js into backend templates. Exclude development `.env` files from Git and product distributions, put publishable configuration examples in `.env.example`, and use the repository-root `.gitignore`.

## 3. Responsibilities within a domain

| Name | Owns | Does not decide |
| --- | --- | --- |
| `router` | URLs, HTTP methods, input/output, HTTP errors, streaming transport | Business authorization and state transitions that workers must also enforce |
| `schemas` | Pydantic request/response fields and value validation | Permissions on actual database entities |
| `dependencies` | Authentication, request Session, configured service wiring | The complete business workflow |
| `service` | Business decisions, authorization, execution order, state transitions, persistence boundaries | HTTP transport or application process startup |
| `repository` | The domain's SQL queries, writes, and conditional updates | Arbitrary changes that bypass another domain's policy |
| `client` | Domain-specific external service access, request context, response conversion | Visibility, authorization, or persistence eligibility |
| `models` | The domain's tables, columns, and relationships | Which fields are exposed by an API |
| `exceptions` | Stable domain error types and meanings | Exposing raw provider errors |
| `constants` / `config` | Domain-specific constants and configuration | A collection of every other domain's settings |
| `policies` | Pure business decisions over supplied values | Database, file, or network I/O |
| `contracts` | Domain values, commands, results, and required collaborator types | An abstraction layer imposed on every service |
| `utils` | Small conversions and helpers without business decisions | Authorization, visibility, or persistence eligibility |

Start with files named for their responsibilities. Use `repository`, `policies`, and `contracts` when there is something meaningful to separate. A service may use SQLAlchemy directly for simple persistence. Extract complex queries or SQL shared by several services into a repository. Do not add separate service, use-case, and interface layers just to forward a function call.

Split large domains such as Chat and Memory by responsibility. For example, Chat's `service/threads.py`, `settings.py`, `messages.py`, `generation.py`, and `evidence.py` own different user actions. There is no requirement to reproduce a full `application/domain/ports/infrastructure` hierarchy inside `service/`.

### 3.1 Splitting a file into a responsibility-specific package

Split a file into a package when its callers and reasons to change diverge. A domain whose creation, approval, and query flows have grown could use the following layout. These names illustrate decomposition; they are not the current file inventory of a particular domain.

```text
app/domains/<domain>/
├── router.py
├── dependencies.py
├── models.py                   # Keep as one file if small, independently of other roles
├── service/
│   ├── __init__.py
│   ├── creation.py             # Creation flow
│   ├── approval.py             # Approval and state transitions
│   └── queries.py              # Business queries
├── schemas/
│   ├── __init__.py
│   ├── creation.py             # Creation requests and responses
│   └── approval.py             # Approval requests and responses
├── repository/                 # When SQL benefits from separate ownership
│   ├── __init__.py
│   ├── queries.py
│   └── writes.py
├── contracts.py
├── policies.py
├── exceptions.py
└── utils/                      # When distinct helper responsibilities need separate files
    ├── __init__.py
    ├── text.py
    └── time_format.py
```

- Splitting `service.py` into `service/` preserves the domain's authorization, state-transition, and persistence responsibilities. File length alone does not justify adding forwarding layers around the same behavior.
- Choose each role's depth independently. A domain can use `service/` while retaining `models.py`, `schemas.py`, and `client.py`. Split `router/` or `models/` only when those responsibilities grow.
- **Do not keep both `service.py` and `service/` at the same location.** Apply the same rule to `schemas`, `models`, `client`, `utils`, and other roles.
- When moving files, update actual caller imports, supported functions/types, tests, and architecture checks together. A file split does not change Session, commit, error, or retry semantics.

The current [Chat services](app/domains/chat/service) are split by user action, while [Chat schemas](app/domains/chat/schemas.py) remain one file. [Social schemas](app/domains/social/schemas) and the [Social repository](app/domains/social/repository) are packages. These forms can coexist; domains need not have identical nesting.

### 3.2 Ownership of helpers, settings, and types

`domains/<domain>/utils.py` holds helpers owned by that domain. Do not move every helper into `app/core` or a global `utils` module from the outset. When several domains demonstrably use the same semantics, review ownership and dependency direction before extracting a shared utility.

| Content | Appropriate location and reason |
| --- | --- |
| Whitespace cleanup or display-value conversion used only by this domain | The domain's `utils.py` or `utils/text.py` |
| Deciding whether the current actor may approve a candidate | The domain's `service`; pure decisions over supplied values may move into `policies` |
| Deciding whether a persona's length is valid for storage or whether it is package-compatible | The owning domain's `schemas`, `service`, or validation functions; do not hide persistence eligibility in `utils` |
| Fixed status codes and constants for the feature | The domain's `constants.py` |
| Feature settings that vary by execution environment | The domain's `config.py`, supplied with the required values validated by shared configuration loading |
| HTTP request and response fields | The domain's `schemas.py` or `schemas/` |
| Commands, results, and collaborator types exposed to workers or other domains | The owning module, or extracted `contracts` when useful; reuse supported types when a separate copy is unnecessary |

The name `utils` does not permit arbitrary database, network, or business logic. Transport conversion belongs to the integration; business eligibility belongs to the domain. A file named `schemas.py` also has different meanings in different locations. External-service schemas and public HTTP responses are not automatically the same contract.

A domain's `config.py` does not require another environment-variable reader or `BaseSettings` instance. Shared loading belongs to `app/config.py`; concrete object and resource wiring belongs to `main` and `runtime`. Do not put per-user settings, credentials, or current database state in `constants.py`.

## 4. Domain catalog

| Domain | Responsibility |
| --- | --- |
| `identity` | Login, sessions, Local owner bootstrap, user settings, credential policy |
| `characters` | Character definitions, drafts, Creator, profiles, image settings |
| `worlds` | World definitions, creation, banners, membership, definition versions, readiness |
| `world_characters` | World participation, owner control, configuration generation/approval, Studio lifecycle |
| `device_home` | Local World list, Home/Studio entry, available execution surfaces |
| `world_packages` | World package contracts, export/import, validation, lineage, atomic application |
| `social` | Posts, replies, reactions, Feed, Inbox, manual writing, public activity, image requests |
| `relationships` | Relationship events, points, candidates, graph queries, application policy |
| `routines` | Autonomous activity settings, plans, slots, ticks, allowed actions, outcomes, activity logs |
| `routine_posts` | Autonomous writing inputs, context, generated results, duplication, provenance |
| `chat` | Threads, messages, retrieval plans, evidence, generation, cancellation, streaming |
| `memory` | Memory candidates/items, recall, source revalidation, AI batches, reservations, Daypart |
| `runtime` | Domain contracts and services for runtime state, diagnostics, and lease decisions |
| `local_bot` | Local Bot authentication, owner keys, supported HTTP actions |
| `character_lore` | Character reference documents, parsing, chunks, embeddings, retrieval |
| `media` | Assets, recognition, ComfyUI workflows, World image policy, shared value/error contracts |
| `tree` | Business operations for the Tree board |
| `operations` | Meaning, retrieval, and persistence of existing operational settings |

`domains/runtime` owns the meaning of runtime state and lease rules. Its responsibility differs from top-level `app/runtime`, which starts the app and workers. `Character` represents a character; `WorldCharacter` represents participation in a particular World. Sharing a character does not merge conversations, memories, or relationships across Worlds.

## 5. How requests and workers use services

```text
HTTP request → router → service → same-domain DB access / repository
                             └─→ required collaborators / external client

runtime scheduling and job execution → the same service

main → runtime composition → service creation/wiring → app.state → HTTP dependency
```

Routers interpret requests and produce responses. Services receive the actor and target scope, then decide what is allowed and which changes to persist. Validation placed only in a router can be missed by workers. Copying the policy into a worker can make the two entry points diverge.

See [Chat service composition](app/runtime/chat/message_composition.py) and [Chat dependencies](app/domains/chat/dependencies.py). Composition creates the concrete Thread, Message, and Generation services; dependencies provide the configured objects to requests. Runtime imports and composes domain services. Services do not import `app.main` to find running objects.

Memory candidate persistence starts in the [items service](app/domains/memory/service/items.py). It checks scope, settings, source success, and visibility, then identifies duplicate candidates for the same source before writing. A running worker or a successful LLM response alone does not establish a valid memory.

## 6. Connecting domains

**Import required functions and types explicitly from the role that owns them.**

```python
from app.domains.worlds.service import definition as world_definition
from app.domains.identity.contracts import CredentialMaterial, CredentialPurpose
```

Supported calls define inputs, outputs, errors, and transaction participation. Check entry points consumed by other domains against the exact module contracts in the [boundary policy](../security/architecture_import_policy.json). Review and register a new connection's owning service, schema, contract, and required errors. Do not widen internal access through wildcards or added exceptions. A file named `service` does not make every internal helper a public contract.

Do not import another domain's model or repository to bypass its state transitions, authorization, or persistence rules.

```text
main / runtime composition → supported domain services, schemas, contracts
domain service             → its own internals + required supported domain capabilities
domain model               → app.models.Base
shared Base, errors, tools → no dependency on domains
```

Place concrete collaboration that reads across domains or deletes their data atomically in `runtime/<domain>/`. For example, [account deletion](app/runtime/account_deletion.py) composes Identity, Character, World, Memory, and private-media cleanup into one operation. Identity decides whether deletion is permitted; composition preserves the shared Session and existing commit/rollback order.

Cross-domain runtime queries are specific queries with defined read scope, authorization revalidation, and Session contracts. They do not justify moving all database access into runtime or permitting arbitrary cross-domain SQL. If a cycle appears, review domain ownership and collaboration direction first.

Pass a small Protocol or callable when there is a real replacement boundary, such as a provider, clock, or restricted query into another domain. Not every repository or service needs a separate abstract interface. New code is not required to pass through an aggregate `public.py`.

Shared code is also divided by actual responsibility. [`routines/policies/active_hours.py`](app/domains/routines/policies/active_hours.py) owns active hours; [`social/service/search_documents.py`](app/domains/social/service/search_documents.py) owns post-search document fields and length rules. `core/search_text.py` contains only shared normalization and LIKE conversion. `core/public_media.py` wires shared HTTP media mounts; `core/image_generation.py` wires shared image-model and provider settings.

`integrations/llm` handles external AI communication and SDK wiring; a domain `client` handles domain-specific requests and response interpretation; `providers/gemini.py` provides the shared Gemini generation/embedding adapter. Inspect the concrete adapter selected by `providers/registry.py` together with the domain parser. SDK calls do not necessarily live in one directory.

`api/v1` retains composition that preserves existing URL groups and registration order, plus shared HTTP wiring. `api/schemas/first_greeting.py` defines an HTTP response combining an execution result and a Social post. Do not collect business authorization or SQL back into these composition files. Even when old route imports remain supported, the actual HTTP and business implementation has one owning path.

### 6.1 Structure of an external integration package

Single-file integrations such as `integrations/replicate_image.py` are supported. When request/response formats, configuration, errors, and conversions need separate ownership, split them **within a directory for the same integration**:

```text
app/integrations/<external_service>/
├── __init__.py          # Package setup; no external connection at import time
├── client.py            # HTTP/SDK requests, response reading, timeout/error conversion
├── schemas.py           # External API request, response, and transport formats
├── config.py            # Integration-specific endpoints and connection limits
├── constants.py         # External status codes, formats, fixed transport constants
├── exceptions.py        # Integration errors: timeout, authentication, invalid response
└── utils.py             # Small encoding and field-conversion helpers

tests/integrations/<external_service>/
├── test_client.py       # Success, failure, timeout, retries, call counts
└── test_schemas.py      # External response formats and missing/invalid values
```

`<external_service>` is a placeholder for the integration's name. **These files and tests illustrate separable responsibilities**; do not create all of them for every integration. Small tests may remain in one file, as in `tests/integrations/test_direct_llm.py`. `integrations` also includes technical adapters for media conversion, file handling, and graph SDKs.

| Integration file | Owns | Remains in the domain |
| --- | --- | --- |
| `client.py` | Serialization, transport, response reading, allowed timeouts/retries, SDK error conversion | Who may request an operation; eligibility for generation, publication, approval, and storage |
| `schemas.py` | External field names, nullability, status values, payload shapes | Public Angmoo HTTP fields and character/World state transitions |
| `config.py` | Endpoints, timeouts, and connection settings supplied by the app | User consent, business call budgets, credential-selection policy |
| `constants.py` | Fixed API values and error-code mappings for the integration | Permissions and user settings that change at runtime |
| `exceptions.py` | Information callers need, such as failure category and retryability | HTTP status selection and whether to persist a failed result |
| `utils.py` | Encoding, parsing helpers, external-field conversion | Decisions that bypass authorization, visibility, or business validation |

The basic example uses `client.py`. Use `clients.py` when one module genuinely groups several clients, or `client/` when connection responsibilities grow enough to split. Check existing naming and callers; do not duplicate the same responsibility under a different name.

External-service schemas and domain schemas are different contracts even when their filenames match. A domain client or adapter converts external fields, SDK objects, and error payloads into domain values; the service decides how to use or persist the result. Successful format validation is not business approval.

### 6.2 Domain clients, integrations, providers, and runtime

Keep these responsibilities distinct even when they participate in the same external call. A call is not required to pass through every location below. Separate them where actual reuse or replacement boundaries exist.

| Location | Responsibility | Current reference |
| --- | --- | --- |
| Domain `service` | Consent, authorization, business budgets, ordering, result application | [World activity setup service](app/domains/world_characters/service/autonomous_setup.py) |
| Domain `client` | Request context, response-schema selection, conversion to domain values | [World character client](app/domains/world_characters/client.py) |
| `integrations` | External HTTP/SDK/file I/O, call tracing, technical response/error conversion | [Shared LLM calls](app/integrations/direct_llm.py), [Replicate image integration](app/integrations/replicate_image.py) |
| `providers` | Shared generation/embedding contracts, adapters, selection | [Provider contracts](app/providers/contracts.py), [Gemini adapter](app/providers/gemini.py), [registry](app/providers/registry.py) |
| Identity and `credentials` wiring | Credential purpose, authorization, resolution, existing shared wiring | [Identity credential resolution](app/domains/identity/service/credential_resolution.py), [credential wiring](app/credentials/resolver.py) |
| `main` and `runtime` | Configuration, resource lifetimes, concrete service/adapter composition | [Chat composition](app/runtime/chat/message_composition.py) |

`integrations/llm/` also contains task-specific adapters implementing domain request/result contracts. Using supported domain types in an adapter is different from calling back into domain approval or persistence services. Do not move existing typed adapters wholesale or duplicate SDK code such as `providers/gemini.py` in a new integration directory. If placement must change, update actual call relationships and supported contracts together.

Before adding a connection, check whether existing `direct_llm`, `provider_http`, `bounded_http`, and provider contracts can be reused. Hidden SDK retries and fallbacks count toward actual call limits and timeouts; adapters must not add calls beyond the domain's allowance. Use shared credential wiring. An integration must not select or store user keys independently.

For World profile generation, **request consent and candidate approval** belong to `world_characters/service`; **generation-input construction and result interpretation** belong to the domain client; **model calls and external error handling** belong to the existing LLM integration. Do not put candidate-approval rules in an HTTP client or let an integration change approved database state because a transport format changed.

## 7. Models, Sessions, and transactions

[`app/models.py`](app/models.py) owns the single ORM `Base`. Each domain's models own its tables. [`runtime/persistence/model_registration.py`](app/runtime/persistence/model_registration.py) registers models needed at app startup and during migrations. Registration does not change domain ownership.

[`app/database.py`](app/database.py) creates and wires engines and synchronous SQLAlchemy `Session` objects. Importing a module does not create an engine. Supported Local execution supplies explicit runtime configuration and data paths. The test helper `model_fixture_support.py` collects ORM references needed by tests; it is not a global model registry for product code.

Functions participating in one business change receive the same Session. Creating a repository does not authorize opening another Session or adding an internal commit. Caller-owned commits, flush-only functions, and independently persisted activity logs have different contracts.

World Package import, for example, applies several models and lineage together. If World and WorldCharacter seeds committed independently, a later failure could leave partial data, so Package owns atomic application. Existing Daypart summaries instead preserve their per-group contract: roll back a failed group and continue with the next.

A Session is not a global object shared by concurrent work. Do not reuse a completed request's Session in a background task. Do not hold a write transaction open while waiting for external AI. Recheck current permissions, version, and lease when applying results.

### 7.1 PostgreSQL transactions, bounded retries, and completion records

Retry `40001` serialization failures and supported transient deadlocks by rerunning the complete DB transaction, including the reads and checks that decide the write. Roll back and return the connection before waiting. Keep one monotonic deadline and the operation's bounded attempt policy; do not wrap another retry loop around it.

A received AI result and its DB application have separate lifetimes. Preserve a valid draft before retrying storage; a storage retry must not repeat the provider call or a committed public action. An uncertain commit requires reconciliation against the same idempotency key and effect receipt. Invalid output, configuration errors and permission failures are not transient DB contention.

The main pool retains up to 10 connections and permits 5 overflow connections; the checkpoint pool permits 2 and direct connections are bounded at 2. Pools open lazily. The runtime role permits 20 connections; the server budget is 28 including 3 administrator reservations and operating headroom. A reservation does not create a session. See `core/postgresql_capacity.py`.

Lease renewal and tick completion retain ownership, epoch, expiration and CAS checks. Instrument bounded queue, acquisition, SQL, commit and cleanup measurements without adding a diagnostic DB write at every stage. Memory and relationship maintenance share one execution slot and continue the selected character's prepared work at safe short-transaction boundaries. SNS, Chat and retrieval remain available.

## 8. HTTP, validation, and asynchronous execution

Pydantic validates input and response shapes. Services check the current owner, World, and target state. Disabled UI buttons and client-supplied IDs are not authorization evidence. Dependencies and shared API modules handle HTTP concerns such as authentication, cookies, and CSRF.

ORM models and response schemas serve different purposes. Do not serialize ciphertext, credentials, or internal state directly. Preserve response fields, time formats, nullability, and error bodies. Returning a Pydantic model and declaring a FastAPI `response_model` can be used together.

Convert business errors to HTTP responses in the router or shared HTTP boundary. A shared error may map to different HTTP responses under different domain contracts. Shared cursor utilities convert bytes; each domain owns encryption, World scope, ordering, and defaults.

Call asynchronous I/O with `await`. Calling a synchronous helper inside `async def` does not automatically run it in a thread pool. Check the actual execution boundaries of database, file, and SDK calls. Do not bundle a synchronous-Session-to-`AsyncSession` migration or a library upgrade into a structural change.

## 9. Canonical data, retrieval, and AI

PostgreSQL stores canonical data, management state and checkpoints. PostgreSQL full-text/trigram indexes, pgvector exact-cosine projections and LadybugDB relationship graphs are derived data. A search hit does not establish current read permission or deletion state; recheck the canonical World's scope, observation scope, and visibility.

The LLM interprets allowed context and produces plans, summaries, and character responses. Code determines actual IDs, permissions, allowed operations, persistence eligibility, and call limits. Do not execute model-generated SQL or Cypher directly. Validate the plan and use an allowed executor.

Recurring work uses job identity, claims, leases, and versions to control duplicate execution and late results. Do not replace Memory batch consent, call budgets, retries, or terminal persistence with a simple HTTP background task. A late response must not reapply work that has already been cancelled or terminated.

Stream only allowed response events. Do not expose internal planner output, reasoning, or raw provider errors. Do not save a failed partial response as a successful source or downstream memory evidence. Hidden SDK retries and fallbacks count toward actual provider calls.

## 10. Runtime composition and key files

These files are starting points for tracing actual responsibilities and callers. Their existence does not
justify introducing another service abstraction layer.

| Workflow | Starting file | Collaboration boundary |
| --- | --- | --- |
| App creation, startup, shutdown | `app/main.py` | `create_app`, `create_lifespan`, existing profiles and resource lifetimes |
| Chat service configuration | `app/runtime/chat/message_composition.py` | `configure_chat_services` wires Thread, Settings, Message, Generation, and Evidence services |
| Chat service access from HTTP | `app/domains/chat/dependencies.py` | Returns configured services from `request.app.state`; does not create an executor per request |
| SNS execution graph | `app/runtime/autonomous_activity/graph.py` | `build_autonomous_graph`, `LanePorts`, parent/lane state, checkpoints |
| Scheduler and leases | `app/runtime/resident/scheduler.py`, `app/runtime/resident/lease_executor.py` | Periodic execution, actual DB work, cancellation, heartbeat recovery |
| Feed candidate decisions | `app/domains/social/service/world_feed.py` | Settings, authorization, candidates, claims, final revalidation |
| Feed-owned SQL | `app/domains/social/repository/world_feed.py` | Queries and conditional state access in the same Session; no external AI calls |
| Default SNS relationship policy wiring | `app/runtime/relationships/` and `app/domains/relationships/` | Atomic registration with World creation, preserving existing activation times |
| Paginated queries | `app/domains/chat/service/message_pages.py`, `app/domains/social/service/feed_pages.py` | Domain-specific cursors, scope, ordering, query limits |

Chat configuration follows **create concrete services in runtime → attach to app.state → retrieve through HTTP
dependencies → execute the service**. Do not reverse this by making `GenerationService` import `app.main`
to locate a global runtime object. For SNS graph changes, inspect the actual composition and lane ports in
`autonomous_activity/graph.py` instead of guessing an old path.

## 11. Scheduler and autonomous activity

FastAPI lifespan owns scheduler and projector startup/shutdown. Browser-screen lifetime is separate from
server-work lifetime. Android process survival is also separate from application scheduler guarantees.

Classify a heartbeat deadline failure at its specific waiting boundary. Clear readiness, stop accepting new
activity, and wait for actual database and child-task cleanup. Recover only after verifying a valid lease and
a successful heartbeat. On expiration, acquire a new epoch through the existing procedure; wait if another
owner holds the lease. Remain failed if cleanup is uncertain, and propagate cancellation and shutdown.

LangGraph composes Inbox, Feed, and Routine in `runtime/autonomous_activity/graph.py`. Checkpoint state
contains serializable values, never Sessions, credentials, or SDK objects. Code selects candidates, permissions,
and allowed actions; the model chooses and writes within that scope. A Feed item available for reaction
does not by itself authorize a new root post.

Check committed canonical results and effect receipts first. Checkpoint success does not mean publication
succeeded. An uncertain result is not a reason to repeat a paid call or publish again. Resume only supported
durable drafts, preserving cancellation reason, lease, attempt budget, and the original window. Reuse
successful effects and keep internal proof out of public results.

Changes to active hours, intervals, or OFF→ON state conditionally update only that character's idle slot in
the owning settings transaction. Existing owners handle active claims, unresolved leases, and recovery due
times. Identical settings or unrelated edits must not create extra writes, new activity, or enable another character.

## 12. Memory retrieval and result application

Distinguish PostgreSQL canonical data from full-text, pgvector and LadybugDB results. A hit does not prove current
permissions, deletion state, revision, visibility, or observation scope. Check canonical state during hydration
and before final delivery or persistence. Distinguish empty results, retrieval not selected, unavailable, and timeout.

The official PostgreSQL runtime uses `PostgresMemoryHybridRuntime` in the single backend process. It does not start the legacy SQLite retrieval processes. Return read connections before provider I/O and keep request cancellation/deadlines separate from pool capacity. The former SQLite process/IPC preparation rules remain in compatibility code and historical ADRs; they are not PostgreSQL runtime defaults.

Chat and SNS freeze accepted starting input and deliver stored original snapshots with selected memories. Do not silently fetch current original content to replace those snapshots. Relationship review groups situation-memory bodies by counterpart and supplies only those bodies and the existing relationship perception to the model; it does not fetch or validate original snapshots. Preserve ownership, deletion, lease, duplicate and conflict fences.

Current social-hybrid Chat retrieval allows at most 20 seconds, bounded by the parent's remaining time and
response reserve. Selected SNS batch retrieval shares a 30-second budget measured before queue entry,
including time reserved for final validation. Retries do not silently change accepted time, model, locale, or schema contracts.

Interpreting a date question, applying a filter, executing retrieval, and recording event time, source scope,
and memory-creation time are different things. A relevant result without a date filter does not establish that
an event occurred on a specific date. Pass validated plans to bounded executors; do not run LLM-generated SQL or Cypher directly.

Memory storage, memory review, and relationship review check settings, consent, and scope. Rechecking or
discarding an experience whose memory write failed is different from deleting the original Chat/SNS source.
Report stored, rejected, skipped, and unresolved recheck outcomes separately.

## 13. Relationship policies and SNS evidence

Default SNS World creation must receive the relationship-policy initializer wired by Runtime. World,
membership, owner binding, and initial policy registration share one Session and transaction. Paths that
reuse or adopt an existing World, use the World selected after concurrent creation, or register an older
draft repair only missing policies. Existing activation time, mode, and version remain unchanged.
Already initialized paths perform no UPDATE or commit.

Failure during registration, flush, or commit rolls back the entire change. Commands that own a new commit
must not include a caller's unrelated pending or already flushed writes. GET and memory queries do not
create policies or retroactively process previously excluded memories or receipts.

Source events for manual like/unlike/post/reply actions remain `audit_only`; they are not automatically
eligible for general event recall or relationship projection. Only material actually delivered to a situation
is validated for its purpose through a typed source basis, restored delivery manifest, and canonical digest.
Distinguish the event-time hash from the currently delivered post revision. Unlike does not require a current PostLike row.

Apply, recall, hydration, detail, and preflight validation use the same source adapter. Operation-local caches
cover only bounded queries in that execution; they do not replace fresh validation at the final transaction
fence. Do not rewrite supported historical receipt formats or hashes.

## 14. Query APIs, images, and UI collaboration

Chat's latest/before/after cursors bind owner, World, thread, and `(created_at, integer id)`. The default page
size is 50, the maximum is 100, and limit+1 determines whether more results exist. Project attachments and
committed evidence only for the current page, and provide an initial boundary for an empty thread.
Status responses and pages share the same evidence projection.

World Feed owns its separate owner/World/actor cursor, pages of 30 root posts, and single-root-post summary
queries. Do not mix replies into the 30 and filter them out on the client. GET does not create records, call
providers, or retain transactions between requests. Preserve existing write idempotency and reply-page contracts.

Media owns authenticated files, validation, format, size, and managed references. Perform PNG-card handling
and image preparation outside the writer where read/file work allows it; recheck permissions and draft
revision when applying results. On cancellation or an uncertain commit, check canonical references and leases
before cleaning up only temporary files owned by the operation.

Source images, generation requests, received results, local attachments, and successful delivery are distinct
states. Provider timeouts or unconfirmed results do not justify blindly repeating paid work. ComfyUI settings,
Partner credentials, URL restrictions, and payload limits follow the existing Media wiring contracts.
Do not hide media SQL in shared transport code.

## 15. Local sessions, time, and secrets

Only the Local preparation POST creates a new installation owner and session. Existing unbound data
requires explicit owner selection; GET does not create users. Preserve Origin, Host, bootstrap-challenge,
and desktop-launch-token validation. A client ID is coordination metadata, not an authentication credential.

Explicit session stop invalidates the client generation and rejects even late-issued cookies. It does not
delete other clients, user data, or settings. Ordinary authenticated reads do not create writes.

Environment confirmation precedes creation of a new default World or user profile. Accepted jobs reuse
an immutable environment snapshot on retries. Stored instants, leases, and retention use UTC and elapsed
time; display and activity calendars follow the saved language and IANA time zone. DST and time-zone
changes do not reset usage budgets or alter already accepted inputs.

Supported execution uses local encryption based on the installation secret. Do not infer key replacement
or recovery from names or logs. Preserve ciphertext-reading/migration contracts and the original root
secret. Do not interpret an unavailable historical hosted credential as a new key.

## 16. Startup, migrations, shutdown, and logs

`app/main.py` owns one `create_app` and one `create_lifespan`. Local execution passes an explicit
RuntimeConfig to `create_public_app`. Do not confuse the public profile of `app.main:public_app` with
general factory defaults or create a duplicate factory.

Keep installed-user, Docker, development, and TEST data roots separate. Supported 0.1.3 SQLite migration uses
immutable backup, staging, explicit type/state conversion, schema/FK/content checks and selection after verification.
PostgreSQL schema changes use the owner-only schema initializer; serving uses a restricted runtime role. Do not modify
frozen predecessors or Alembic history. File moves alone do not increment the schema. Follow the
[retention policy](../docs/operations/embedded-retention.md) for generations, use pins, maintenance locks, secrets, and media.

On shutdown, cancel requests, stop accepting new work, wait for worker tasks to finish, and release owned
resources. Do not report cleanup success while actual work remains unfinished. Failure to clean up one
resource must not prevent attempts to clean up the remaining owned resources.

Termux's `angmoo-service-log.v1` policy binds launch, service, and expiration. Basic mode retains lifecycle,
warning, and error records; temporary detailed mode adds allowed access, worker, and lease summaries.
Each service enforces monotonic expiration. Distinguish the host's UTC estimate from service acknowledgement.
Do not silently change legacy runs without a policy, sidecar JSON, or handler ownership.

Diagnostics do not record search terms, conversations, keys, SQL parameters, or prompts. General log mode
and dedicated detailed Chat/SNS observation are separate features. Do not report missing samples as 0ms
or healthy. Distinguish queue wait, actual execution, writer hold, commit, and cleanup; do not simply add
parent/child or parallel durations.

## 17. Validation and detailed contracts

Select checks for the changed domain, callers, and failure boundaries. Use fake providers, isolated PostgreSQL and frozen SQLite input fixtures,
fixed clocks, and cancellation/resume scenarios. Changes to shared DB behavior, app factories, migrations,
or packaging need appropriately broader consumer coverage. Required remote coverage follows the
[CI policy](../docs/operations/ci-validation.md).

```sh
uv run --project backend python scripts/ci/generate_architecture_inventory.py --check
uv run --project backend python scripts/ci/check_architecture_boundaries.py
```

The inventory records current facts; policy defines allowed dependencies. Do not widen exceptions or
deadlines, or delete behavioral assertions, merely to pass checks. Historical source-body comparisons are
for investigating earlier migrations, not a substitute for routine feature validation.

- [Domain boundaries](../docs/architecture/backend-domains.md)
- [Supported historical and extension compatibility paths](../docs/architecture/backend-compatibility.md)
- [PostgreSQL migration](../docs/public/postgresql-migration.md)
- [PostgreSQL backup and recovery](../docs/public/postgresql-backup.md)
- [Legacy SQLite recovery and received results](../docs/operations/sqlite-recovery.md)
- [Local runtime](../docs/public/local-runtime.md)
- [LangGraph nodes](../docs/public/adding-langgraph-node.md), [provider adapters](../docs/public/adding-provider.md)

Consult the relevant validation records for implementation, test, and deployment status. This document
defines current design rules; it is not evidence of functionality or performance on every device, model, or runtime condition.

### Design references and historical material

- [FastAPI Best Practices — Project Structure](https://github.com/zhanymkanov/fastapi-best-practices#project-structure): reference for domain-oriented organization and role separation.
- [Current boundary policy](../security/architecture_import_policy.json) and [boundary checker](../scripts/ci/check_architecture_boundaries.py): Angmoo's actual dependency and responsibility rules.
- [Backend migration record](../docs/architecture/refactor-backend-results.md): historical evidence for earlier structural changes. It does not determine where to implement a new feature or prove a new release succeeded.
