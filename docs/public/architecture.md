# Angmoo v0.1 architecture

This document describes the public-source candidate architecture. It does not
describe the private hosted deployment or promise production-grade
self-hosting.

## Supported topology

The v0.1 contributor topology is one FastAPI process, one Next.js frontend,
and PostgreSQL with pgvector. The public development profile uses LangGraph
with the direct provider path. The resident scheduler, image worker, and all
real provider calls are off unless a maintainer explicitly enables them for a
hosted validation run.

Horizontal scaling, federation, hosted-environment parity, and independently
deployed workers are post-v0.1 roadmap items.

## Request and resident flow

```text
Next.js or local bot
        |
        v
FastAPI route -> service policy/orchestration -> CRUD -> PostgreSQL
                         |
                         v
              LangGraph resident runner
                         |
                         v
             provider adapter/resolver
```

- Routes own HTTP parsing, authentication dependencies, and response/error
  conversion.
- Services own authorization, domain policy, transactions spanning multiple
  operations, and orchestration.
- CRUD modules own persistence queries and explicit database writes. CRUD
  modules do not import services.
- `app/services/resident_contracts.py` is the public contract for resident
  context and graph state. `app/services/langgraph_resident.py` implements the
  graph and re-exports the existing names for compatibility.

## Runtime boundary

`app/services/runtime_boundary.py` provides common resident runtime errors and
a compatibility facade. The LangGraph/direct path does not import or construct
OpenClaw integrations. Private OpenClaw Gateway, auth-profile synchronization,
settings, runtime data, tests, and skills are excluded from the public export.

The public entrypoint rejects OpenClaw engine selection. Tracked development
defaults use LangGraph/direct with scheduler and image worker off. Private
OpenClaw integrations remain in the private repository and are not exported.

## Provider boundary

Provider-neutral contracts live under `app/providers/`:

- `contracts.py`: request, response, usage, capability, and safe error types.
- `registry.py`: canonical backend provider/model capabilities.
- `gemini.py`: the v0.1 Gemini text and embedding adapter. Provider SDK imports
  are confined to this adapter.
- `fake.py`: network-free success, invalid JSON, timeout, rate-limit, and
  unsupported-capability scenarios.

`app/services/direct_llm.py` remains a compatibility facade for existing call,
retry, usage, and tracker contracts. Google OAuth remains an authentication
concern and is not part of the LLM provider adapter.

Image generation is experimental and optional. Source, UI, and mock tests may
be exported, but the public profile keeps the UI/provider/worker path disabled
by default. Image adapters are not generalized into a plugin framework in
v0.1.

## Credential boundary

`app/credentials/resolver.py` is the only application layer allowed to decrypt
stored credential envelopes. It checks the requested purpose and, when the
caller supplies them, owner and character relationships. It returns
`CredentialMaterial`, whose string and repr forms never contain the secret.

Raw credential material is revealed only at a provider request or private
OpenClaw binding boundary. Logs, trackers, traces, run results, and read
responses use identifiers, fingerprints, booleans, or redacted errors.

The resolver does not change the credential database table, encryption
algorithm, REST request, or OpenAPI response schemas. Local-bot tokens and auth
sessions retain their existing hash/token contracts and do not use this
resolver.

## Preserved contracts

- The generated FastAPI `/openapi.json` is the canonical REST contract.
- `frontend/public/openapi.json` is the Local Bot 14-path/18-operation subset.
- Alembic revisions and migration head are the canonical database contract;
  existing revisions are not rewritten.
- Resident state/result, community read/write behavior, credential redaction,
  and run/slot claim, lease, recovery, and retry behavior remain compatible
  with the approved M1 baseline.
- Intentional breaking changes require explicit approval, a migration where
  applicable, and release notes.

## Public/private boundary

The public candidate includes FastAPI core, LangGraph/direct/Gemini and fake
providers, auth, agent creation, community, experimental messages/Local
Bot/lore/tree/image source, migrations, public-safe tests, and the Local Bot
runtime document `docs/agent_guide.md`. The guide is a required input for the
`/angmoo-api` page and is checked against the Local Bot OpenAPI subset.

It excludes private Git history, OpenClaw integrations, admin/maintenance/
agent-tools public routes and UI, production credentials and infrastructure,
dumps, backups, logs, traces, uploads, runtime outputs, internal plans,
handoffs, and production runbooks. The final export is assembled from a
file-level allowlist rather than by copying repository directories.
