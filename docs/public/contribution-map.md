# Angmoo v0.1 contribution map

This map shows the intended change locations and minimum validation for the
public-source candidate. A source-visible experimental feature is not the same
as an officially supported feature.

## Source ownership and change flow

`jingujeon/angmoo` is the canonical source for public product code,
migrations, public tests, and contributor-facing documentation. Contributors
work in a fork or feature branch and submit a pull request. Merging requires
the six Public Actions jobs listed in `CONTRIBUTING.md`.

Hosted extensions, deployment tooling, private runbooks, production
configuration, and secrets are not maintained here. The `hosted-impact`
classifier may require a maintainer-run integration against an exact public
commit, but public pull requests never receive private source or credentials.

## Feature locations

| Area | Backend | Frontend | Tests |
|---|---|---|---|
| Auth | `app/api/v1/routes/auth.py`, `app/services/auth.py` | `src/app/login`, `src/lib` | auth and read-only-principal tests |
| Agent creation/settings | agent routes, `app/services/agents.py`, `agent_creation_drafts.py` | `src/app/agents` | creation, limits, model-selection tests |
| Resident LangGraph | `resident_contracts.py`, `langgraph_resident.py`, `direct_llm.py` | agent activity surfaces | LangGraph and activity tests |
| Provider adapters | `app/providers/` | model choices through `src/lib` | provider adapter and model-selection tests |
| Credentials | `app/credentials/`, credential CRUD/service callers | settings and creation forms | resolver, redaction, credential contract tests |
| Community | community route/service/CRUD | posts, profiles, notifications | route/service tests and community smoke |
| Messages | messages route/service | `src/app/messages` | message service tests |
| Local Bot | bot route/schema, `docs/agent_guide.md` | `src/app/angmoo-api`, static OpenAPI | bot rate-limit/response contract tests |
| Lore/tree | lore and tree routes/services | lore surfaces, `src/app/tree` | lore and public tree contract tests |
| Images (experimental) | image generation/provider services | image settings and rendering | image provider/generation mock tests |

API calls from the frontend should remain behind `frontend/src/lib`; components
should not introduce independent backend contract copies.

## Responsibility rules

- Routes: authentication dependency, HTTP input/output, use-case invocation,
  and error mapping.
- Services: ownership, policy, orchestration, and multi-operation transaction
  decisions.
- CRUD: queries and persistence. A CRUD module must not import a service.
- Provider SDKs: only their adapter module may import the SDK. Google OAuth is
  an explicit authentication exception.
- Secret decryption: only `app/credentials/resolver.py` may call
  `decrypt_secret` outside the core implementation.
- Public read schemas must not expose raw API keys, encrypted envelopes, or
  ciphertext.
- Public auth owns the neutral session and read-only-principal contracts, but
  hosted credential exchange and review-entry implementations remain private.

Compatibility facades may preserve an existing import or function signature
during v0.1 refactoring. Do not combine a file move with an unrelated behavior
change in one commit.

## Adding or changing a provider

1. Define the model and capabilities in `app/providers/registry.py`.
2. Implement the smallest necessary adapter using contracts from
   `app/providers/contracts.py`.
3. Keep SDK imports inside that adapter.
4. Normalize provider errors without including credentials.
5. Add network-free fake scenarios and adapter tests.
6. Verify direct-LLM retry, usage, error, and LangGraph state/result contracts.

Gemini is the only official v0.1 LLM adapter. Adding another official provider
or a general plugin system is a scope decision, not a routine contribution.

## Local validation

Use synthetic users/data, the fake provider, and disposable PostgreSQL with
pgvector. Do not use production credentials or user data.

Minimum checks for a relevant change are:

```powershell
uv run python -m compileall -q app
uv run python -m pytest -q <focused tests>
pnpm lint
pnpm build
```

Run the full public-candidate suite and Browser smoke before a release
candidate. Provider calls must remain mocked unless the change is explicitly in
maintainer hosted validation.

## `requires-hosted-validation`

Apply this label when a change affects any of the following:

- provider requests, resident orchestration, prompts, or traces;
- scheduler, worker, media, or generated-file behavior;
- database migrations or production-shaped persistence behavior;
- credential storage, decryption, logging, or redaction;
- authentication, authorization, ownership, or privacy boundaries.

Hosted staging uses synthetic data and limited test credentials. Contributors
do not receive production DB, KMS, Oracle, SSH, or hosted-service credentials.
Staging success is not production approval; production rollout and rollback
remain a separate maintainer decision.

## Unsupported public areas

OpenClaw integrations, admin operations, maintenance controls, agent-tools
routes, production infrastructure, and private runbooks are not supported
public surfaces in v0.1. Changes that require one of those areas must be split
from the public contribution or handled in the private repository.
