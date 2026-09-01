# P8-L-G Memory candidate, write, and lifecycle

Status: **IMPLEMENTED · LOCAL TECH PASS · EXTERNAL LIFECYCLE TRACKED SEPARATELY**

P8-L-G turns the seven-table P8-L-F persistence foundation into a provider-free canonical Memory write path. It does not add a migration or table. `app.domains.memory` remains the backend owner and `app.domains.memory.public` remains the supported consumer boundary.

The foreground application service receives no LLM/provider dependency. It first normalizes the bounded source identity, validates the active owner + World + remembering-subject scope and the explicit opt-in setting, and then reads a bounded canonical evidence snapshot through `MemorySourceEvidenceReaderPort`. It fails closed on unsuccessful, hidden/deleted, cross-World, inactive, blocked, unobserved, or empty-summary sources. An eligible source produces one deterministic idempotency key from contract version, normalized source type and identity, exact scope, and `MemoryKindV1`. Replaying the same source returns the same candidate; a changed source digest is a conflict rather than a second memory.

The SQLAlchemy evidence reader supports the closed v1 source catalog: committed Chat messages and explicit owner-memory requests, Post and reply rows, reactions, successful SocialEvent rows, successful ActivityBeat results, applied directional relationship changes with source-event observation, and scheduled accepted joint commitments. An explicit owner-memory request must resolve to a successful user message in an owner-matching resolved World thread; an Assistant message cannot be relabelled as an owner request. The reader records canonical source digest, source/event/observation references, actor and target direction, same-World counterpart, and thread when applicable. Character persona, World configuration, transient runtime mood, failed activity, partial stream text, and provider output are not eligible sources.

Acceptance uses a deterministic canonical-source summary in P8-L-G. A single savepoint writes the active memory item, exact evidence row, candidate accepted decision, hot-brief invalidation, and idempotent maintenance job. A provenance FK or any other write failure rolls the entire set back, leaving the candidate pending. Ordinary turns therefore create no maintenance provider call; an optional maintenance LLM remains later non-scope.

Lifecycle behavior is canonical and immediate:

- correction creates a new item + evidence, then marks the old item `superseded` with `superseded_by_id`;
- explicit deletion and source invalidation set `deleted` before any asynchronous cleanup;
- retrievable reads require opt-in, active status, no deletion or supersession, and an unexpired validity window;
- pin bypasses retention expiry only when it was set before expiry; an already expired item cannot be pinned to resurrect it, and pin never bypasses explicit deletion or supersession;
- expiry leaves audit history intact and enqueues cleanup only once per item version;
- every item-changing operation invalidates active hot briefs and records a durable maintenance job;
- maintenance claims lock the scope, reload the candidate job under that lock, and allow only one unexpired running job per scope; expired or superseded lease tokens cannot complete or fail a job.

The P0 `memory_opt_out_blocked` and `memory_deleted_blocked` artifacts are now executable behavior Gates. The former proves candidate, item, maintenance-job, and provider writes are all zero while OFF. The latter proves deleted or superseded memory is rejected by the canonical read guard with `memory_not_retrievable`, before P8-L-H adds FTS5 projection.

The machine-readable successor artifact is `p8-l-g-memory-write-lifecycle-inventory.json`. It freezes the P8-L-F inventory digest, proves that the schema/migration set is unchanged, records the source catalog and lifecycle, and keeps FTS5/LadybugDB retrieval, Retrieval Router/Planners, Character Response Generator, Chat streaming, owner UI, and maintenance LLM outside this stage. P8-L-G exposes the after-commit proposal and deterministic acceptance boundaries but does not invent an unapproved consolidation threshold or wire the later Chat generation producer; those callers remain owned by their later P8-L stages.

Local evidence at the implementation closeout is the focused Memory/P0 bundle, the architecture-boundary bundle, every generated inventory check, and the full backend regression. Exact counts and external Issue/PR/Hosted-CI state are recorded in the canonical P8-L plan rather than frozen into this architecture contract.
