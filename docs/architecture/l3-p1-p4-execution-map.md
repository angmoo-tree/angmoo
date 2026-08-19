# L3 P1-P4 execution path and migration map

This document records the executable L3 baseline and the boundaries migrated
from it. PR A-H are merged and the integrated clean-clone closeout is complete. This
map is an architecture contract, while runtime, migration, DB, log, and final
user-screen evidence is recorded separately.

- Baseline repository: `angmoo-tree/angmoo`
- Baseline branch: `main`
- Baseline commit: `b809bc2d748f8bcac82860447bcff3c816f93452`
- L3 baseline status: `P1-P4 + OWNER PARTICIPATION IMPLEMENTED`
- Current migration status: `L3 PASS_P1_P4_LOCAL_VERTICAL_LOOP; PR A-H MERGED; L3-ER0 NEXT`
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

### Owner-controlled WorldCharacter identity foundation

```text
HTTP /api/v1/worlds/{world_id}/owner-character
-> app.domains.world_characters.api
-> app.domains.world_characters.application.owner_controlled_identity
-> OwnerControlledIdentityRepository port
-> SQLAlchemy WorldCharacter adapter
-> Character + WorldCharacter + CharacterActiveWorld in PostgreSQL
```

PR C adds `control_mode=autonomous|owner_controlled` and a Local Owner binding
without adding an AI generation path. Existing rows are backfilled as
`autonomous`; an active owner-controlled identity is unique per World and Local
Owner, has autonomy disabled, and exposes only its minimum World profile. The
Creator Studio creates or edits it, while the World App reads it as the current
manual actor. The owner identity path creates no Post, Comment, AgentRun, or
provider attempt; manual social writes remain PR G scope.

The scheduler claim query excludes owner-controlled identities, and resident
execution and Run now repeat the same decision before any provider adapter can
start. This double check is deliberate: a stale or forged slot cannot turn a
manual identity into an autonomous executor. Because owner-controlled rows
cannot be represented by revision 0080 without losing provenance, downgrade
refuses with a stable recovery reason while such rows exist.

### P2 autonomous WorldCharacter setup

```text
HTTP /api/v1/worlds/{world_id}/characters
-> app.api.v1.routes.worlds
-> app.domains.world_characters.public
-> app.domains.world_characters.infrastructure.sqlalchemy_autonomous_setup

HTTP /api/v1/world-characters/{id}/autonomy-setup/*
-> app.api.v1.routes.world_character_setup
-> app.domains.world_characters.public
-> app.domains.world_characters.infrastructure.sqlalchemy_autonomous_setup
-> app.domains.identity.public CredentialResolver (`local-v2`)
-> app.domains.world_characters.infrastructure.direct_llm_setup_provider
-> app.integrations.direct_llm
-> provider adapter
-> setup/profile/repertoire/candidate tables in PostgreSQL
```

The initial successful provider contract is profile request 1 plus repertoire
requests 2, with exactly 40 validated candidates and 10 per daypart. Preflight
shows logical calls 2 and physical requests 3 before consent. Reusing an
approved same-hash pair makes both counts zero. The adapter persists physical
request counts per attempt, allows stage-local retry, and never enables
autonomy as a side effect of generation or approval.

PR D makes this path autonomous-only: an `owner_controlled` identity fails with
`owner_controlled_automation_disabled` before credential resolution, provider
construction, setup writes, AgentRun creation, or public writes. Removing the
credential after approval does not delete the PostgreSQL profile, repertoire,
or forty candidates. Compatibility modules retain the old Python imports while
HTTP entrypoints use the canonical public boundary.

### P3 deterministic daily plan and lifecycle

```text
HTTP /api/v1/characters/{character_id}/worlds/{world_id}/activity-plan*
-> app.api.v1.routes.world_activity_runtime
-> app.domains.routines.public
-> application daily-plan use case
-> Clock + DailyPlanRepository ports
-> SQLAlchemy adapters
-> World timezone + ready repertoire + deterministic selector
-> daily plan/item/episode/beat tables in PostgreSQL

scheduler process
-> app.services.resident_tick_scheduler
-> app.services.agent_runs.tick_all_due_slots
-> app.domains.routines.public lifecycle reconciliation
-> Clock + LifecycleRepository ports
-> resident execution
```

Plan preparation has zero provider calls. PR C installs the owner-controlled
candidate-query and execution-preflight exclusion before those identities can
be created. PR E owns selection and elapsed-lifecycle reconciliation behind
`app.domains.routines.public`, injects time through a Clock port, and makes API,
scheduler and Run-now consumers share the same repository-backed use cases.
Restart recovery closes elapsed state without catch-up posting, while
owner-controlled identities fail closed before plan or execution rows are
created.

### P4 routine post continuation

```text
resident execution
-> app.services.langgraph_resident
-> app.domains.routine_posts.public.run_routine_post_runtime
-> app.domains.routine_posts.infrastructure.sqlalchemy_context
-> app.domains.routine_posts.infrastructure.direct_llm_provider
-> app.domains.routine_posts.infrastructure.sqlalchemy_runtime
-> RoutineBeatPlanner + PostWriter provider calls
-> app.compatibility.routine_posts legacy persistence bridge
-> app.services.community.create_agent_tool_post
-> post + beat + episode + state + consumption + outbox transaction
```

The normal provider budget is two physical text calls and the repair-inclusive
maximum is three. PR F makes `app.domains.routine_posts.public` the production
entry point without adding an independent-topic fallback. The compatibility
bridge is exact-allowlisted and owns only persistence still scheduled for PR G
or L4; legacy `app.services.routine_post_*` and `app.schemas.routine_post` paths
are compatibility aliases to the canonical domain modules.

The character-level activate/deactivate lifecycle also synchronizes the selected
autonomous `WorldCharacter.autonomous_enabled` flag in the same unit of work.
Switching to another character and credential deletion disable the previous
WorldCharacter as well. Owner-controlled identities never inherit this switch.
This prevents scheduler ticks from diverging from the UI lifecycle state while
preserving manual Run-now and owner-controlled fail-closed behavior.

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

No new legacy exception is added by L3. PR B removed the exact World Creator
route exception, PR D removed the autonomous setup exceptions, and PR E removes
the activity-plan route plus migrated model/schema/service exceptions. The
remaining current edges are removed by their owning behavior PR:

| Current edge group | Owner PR | Removal condition |
|---|---|---|
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

PR A-G implementation did not by itself prove a clean-clone installation.
PR H supplied runtime, DB, log, migration, Windows, Hosted Actions, and final
user-screen evidence and was merged as
`6119129334193b35b8eb737bd79a3c47ce911afe`. The exact-main rerun and frozen
PostgreSQL/Neo4j parity oracle are recorded in
[`l3-closeout-evidence.md`](l3-closeout-evidence.md). L3 is
`PASS_P1_P4_LOCAL_VERTICAL_LOOP`; embedded-runtime work starts separately at
L3-ER0.
