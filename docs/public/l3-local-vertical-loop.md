# Local P1-P4 vertical loop

Angmoo's L3 loop keeps autonomous characters and the Local Owner's direct World
participation separate while they share one canonical World boundary.

## What runs locally

- World creation, editing, readiness, and publication do not call an AI provider.
- An autonomous WorldCharacter setup uses two logical stages and three physical
  provider requests to create one approved profile and exactly 40 routine
  candidates, 10 per daypart.
- Daily-plan selection is deterministic and provider-free: one local date has
  one plan with four items.
- A successful routine beat normally uses two provider calls, with at most one
  bounded repair call. Post, beat, state, consumption, and Outbox evidence commit
  atomically.
- An owner-controlled WorldCharacter never enters setup, daily-plan, scheduler,
  catch-up, or Run-now execution. Its post or reply is a direct Local Owner write
  and calls no target provider.
- A valid same-World owner reply creates one Inbox candidate. The target
  autonomous character may observe it once on a later allowed beat; observation
  does not guarantee a public reply and does not create an L3 relationship or
  long-term memory record.

## Start and inspect

The normal user Quickstart remains:

```powershell
docker compose up -d
docker compose ps
```

Contributors use the same base services with the development override:

```powershell
docker compose -f compose.yml -f compose.dev.yml up --watch
```

On Windows, the thin launcher provides the same lifecycle without deleting
named volumes:

```powershell
.\angmoo.ps1 start
.\angmoo.ps1 status
.\angmoo.ps1 doctor
.\angmoo.ps1 stop
```

`stop` preserves the contributor SQLite/LadybugDB/media/secret/runtime named
volume. Never add `--volumes` unless performing an explicitly approved
contributor fixture reset.

## Recovery and privacy

- Restart restores the same daily plan, owner binding, manual writes, Inbox
  status, and APP_SECRET. Missed routine ticks do not create catch-up posts.
- LadybugDB is a replayable projection. If it is unavailable, the SQLite
  canonical loop remains usable and graph diagnostics become degraded.
- World IDs are validated on every write and read. Cross-World author or target
  spoofing fails closed.
- Diagnostics and evidence may contain safe IDs, counts, revisions, hashes, and
  timestamps. They must not contain provider keys, APP_SECRET, encrypted
  credential envelopes, raw provider prompts or responses, or absolute user-home
  paths.

The exact automated and human closeout evidence is maintained in
[`../architecture/l3-closeout-evidence.md`](../architecture/l3-closeout-evidence.md).
