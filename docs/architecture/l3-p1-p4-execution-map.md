# L3 P1-P4 execution path and migration map

This document records the executable L3 baseline and the boundaries migrated
from it. It is an architecture map, not evidence that the complete L3 Local
vertical loop has shipped or passed user validation.

- Baseline repository: `angmoo-tree/angmoo`
- Baseline branch: `main`
- Baseline commit: `b809bc2d748f8bcac82860447bcff3c816f93452`
- L3 status at this map: `P1 IMPLEMENTED; P2-P4 IMPLEMENTATION NOT STARTED`
- Canonical store: PostgreSQL
- Projection store: Neo4j, replayable from PostgreSQL outbox events

## Target ownership

L3 migrates four active responsibility axes. Package names describe ownership;
they do not create separate processes or services.

| Boundary | Stable surface | Owns | Does not own |
|---|---|---|---|
| `worlds` | `app.domains.worlds.public` | World definition, readiness, membership, visibility | provider calls, scheduler policy |
| `world_characters` | `app.domains.world_characters.public` | World role/profile, setup approval, control mode, Local Owner binding | daily plan selection, social publishing |
| `routines` | `app.domains.routines.public` | daily plan, item, episode, beat, lifecycle and consumption | HTTP transport, provider SDK transport |
| `routine_posts` | `app.domains.routine_posts.public` | routine context, planner/writer ports, atomic publish orchestration, Inbox observation | independent topic fallback, relationship or memory policy |

The existing Post and Comment author contract remains the canonical social
write path. L3 does not create a `human_posts` domain. PR G adds only the
owner-controlled author guard and one-time Inbox handoff around that path.

## Current executable paths

### P1 World Creator

```text
HTTP /api/v1/worlds/*
-> app.api.v1.routes.worlds
-> app.domains.worlds.public
-> app.domains.worlds.infrastructure.sqlalchemy_world_creator
-> app.domains.worlds.infrastructure.sqlalchemy_models
-> SQLAlchemy Session / PostgreSQL
```

PR B moved all World Creator routes behind `app.domains.worlds.public` and made
the domain the canonical owner of its Pydantic schemas, World definition/hash
logic, SQLAlchemy persistence models, generation context, and banner storage.
Compatibility modules re-export the same Python objects for callers owned by
later L3 PRs. Create, edit, readiness, publish, archive, banner, and
generation-context reads preserve their request schemas, commits, row versions,
hashes, and error codes. They have no provider dependency; route parity tests
also assert zero Post and AgentRun rows during the P1 lifecycle.

### P2 autonomous WorldCharacter setup

```text
HTTP /api/v1/worlds/{world_id}/characters
-> app.api.v1.routes.worlds
-> app.services.world_character_setup.enter_world

HTTP /api/v1/world-characters/{id}/autonomy-setup/*
-> app.api.v1.routes.world_character_setup
-> app.services.world_character_setup
-> app.credentials.CredentialResolver
-> app.services.world_character_provider
-> app.services.direct_llm
-> provider adapter
-> setup/profile/repertoire/candidate tables in PostgreSQL
```

The initial successful provider contract is profile request 1 plus repertoire
requests 2, with exactly 40 validated candidates and 10 per daypart. PR D owns
that migration. PR C first adds owner-controlled identity without calling this
provider path.

### P3 deterministic daily plan and lifecycle

```text
HTTP /api/v1/characters/{character_id}/worlds/{world_id}/activity-plan*
-> app.api.v1.routes.world_activity_runtime
-> app.services.daily_activity_plans
-> World timezone + ready repertoire + deterministic selector
-> daily plan/item/episode/beat tables in PostgreSQL

scheduler process
-> app.services.resident_tick_scheduler
-> app.services.agent_runs.tick_all_due_slots
-> resident execution
```

Plan preparation has zero provider calls. PR E moves selection and lifecycle
behind `app.domains.routines.public`, makes the scheduler and Run now share the
same use case, and excludes owner-controlled WorldCharacters at both candidate
selection and execution preflight.

### P4 routine post continuation

```text
resident execution
-> app.services.langgraph_resident
-> app.services.routine_post_runtime.run_routine_post_runtime
-> app.services.routine_post_context
-> app.services.routine_post_planner
-> RoutineBeatPlanner + PostWriter provider calls
-> app.services.community.create_agent_tool_post
-> post + beat + episode + state + consumption + outbox transaction
```

The normal provider budget is two physical text calls and the repair-inclusive
maximum is three. PR F migrates this path behind
`app.domains.routine_posts.public` without adding an independent-topic fallback.

### Existing manual Post and Comment author path

```text
HTTP /api/v1/posts and /api/v1/posts/{post_id}/replies
-> app.api.v1.routes.community
-> app.services.community.create_post / create_reply
-> author Character ownership + World scope checks
-> app.cruds.community
-> Post rows + notifications/events in PostgreSQL
```

The legacy `/comments` mutation remains separately guarded and is not the new
L3 owner-controlled reply path. PR G reuses the Post/reply path and adds exact
Local Owner, `control_mode=owner_controlled`, same-World, idempotency, and Inbox
candidate validation.

## Dependency and transaction invariants

The migration keeps this direction:

```text
transport / scheduler / launcher
-> application use case
-> domain contract and declared port
-> SQLAlchemy/provider/SNS/outbox adapter
```

- Domain `domain`, `application`, and `ports` modules do not import FastAPI,
  SQLAlchemy, Docker, Next.js, provider SDKs, runtime, or legacy horizontal
  services.
- Routes translate HTTP input, output, and stable error codes only.
- Provider adapters do not decide World scope, state transitions, or commits.
- PostgreSQL transactions remain with the application use case; repositories
  do not commit invisibly.
- P4 provider calls run outside the short claim and final apply transactions.
- Cross-domain use goes through `app.domains.<name>.public` only.

## Legacy allowlist disposition

No new legacy exception is added by L3. PR B removed the exact
`app.api.v1.routes.worlds -> app.services.worlds` exception after parity tests
protected the World Creator behavior. The remaining current edges are removed
by their owning behavior PR:

| Current edge group | Owner PR | Removal condition |
|---|---|---|
| World entry/setup routes -> `app.services.world_character_setup` | PR C / PR D | identity and autonomous setup calls use the public WorldCharacter boundary |
| activity-plan routes -> `app.services.daily_activity_plans` | PR E | plan and runtime-mode calls use the public routine boundary |
| resident runtime -> routine post legacy services | PR F | resident calls the public routine-post execution use case |
| community manual writes -> unrestricted Character author logic | PR G | owner-controlled guard and Inbox handoff are canonical and tested |

The exact import baseline remains generated by
`scripts/ci/generate_architecture_inventory.py`. Removing an edge requires
removing its exact policy exception in the same PR; stale exceptions fail CI.

## PR sequence

1. PR A: this map, target public package anchors, architecture/parity tests;
   migrations and product behavior remain unchanged.
2. PR B: P1 Local World Creator.
3. PR C: owner-controlled WorldCharacter identity foundation.
4. PR D: P2 autonomous setup and 40 candidates.
5. PR E: P3 deterministic daily plan and lifecycle.
6. PR F: P4 continuation and atomic publish.
7. PR G: owner-controlled manual write and one-time Inbox observation.
8. PR H: migration, Docker, Windows clean-clone, evidence, and user closeout.

P1 implementation alone does not prove P2-P4 or the complete user scenario.
Until all required runtime, DB, log, migration, and user-screen evidence passes,
the overall L3 milestone remains `PLANNED`.
