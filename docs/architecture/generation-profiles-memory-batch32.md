# Generation profiles and Memory batches of 32

Issue [#319](https://github.com/angmoo-tree/angmoo/issues/319).
Implementation, automated tests, CI, direct user verification and merge remain
separate gates. This document specifies the product change after the original
[Memory batch contract](p8-l-r-memory-batch.md).

Follow [backend architecture](../../backend/ARCHITECTURE.md),
[frontend architecture](../../frontend/ARCHITECTURE.md) and
[frontend design](../../frontend/DESIGN.md). Domain policies own selection and
state rules, integrations own provider I/O, runtime composes credentials and
workers, and frontend features own their forms and API mappings.

## Model and thinking settings

The supported generation choices, in display order, are:

- Gemini 3.5 Flash-Lite (high)
- Gemini 3.5 Flash-Lite (medium)
- Gemini 3.1 Flash-Lite (high)
- Gemini 3.1 Flash-Lite (medium)

API requests and SQLite store the raw model ID and thinking level separately.
The frontend's select key is presentation only and is decoded at the feature
API boundary. Provider requests receive the raw model and selected thinking.
New defaults use Gemini 3.1 Flash-Lite (high). Existing 3.1/3.5 settings gain
`high`; historical retired model IDs remain readable, but owners must select
a supported profile before a new generation. There is no automatic fallback.

Autonomy belongs to each character's credential. Chat has an owner default and
an optional per-thread override. Memory has an owner-common profile and uses
the message credential's secret without inheriting its model or thinking.
Changing any one of these profiles does not overwrite the others. Model-only
changes preserve encrypted credentials and key fingerprints.

Accepted Chat requests and resident runs snapshot their pair. Memory claims
snapshot their pair too; changing the model or schedule does not discard an
already running result. Revoking Memory consent, losing source access, changed
source digests and invalidated credentials still prevent the result's commit.

**Chat and autonomous-activity output-token budgets are unchanged.** Their
model and thinking settings are configurable, but only Memory selection gains
the 65,536 output-token ceiling.

## Batch admission and recovery

Each batch contains up to 32 eligible candidates from one owner, World,
character and privacy partition. Public sources never share a request with
private conversations; different private threads remain separate. Eight or
thirteen compatible candidates use one request. Thirty-three use 32 plus one.
Zero eligible candidates use no request. Each opaque candidate ID must receive
exactly one decision, with only its own evidence and subjective references.

The offline input guard includes normalized prompt bytes and response schema.
It does not call a paid tokenizer or drop source content to claim a 32-item
batch. The conservative complete-prompt bound is 1,000,000; source text budgets
are 240,000 characters and 720,000 UTF-8 bytes. Smaller privacy/input partitions
are explicit constraints, not a two-item default.

The provider timeout is 180 seconds, Memory shutdown budget 185 seconds and
lease 240 seconds. Native and Docker outer shutdown bounds are 200 seconds.
The existing immediate-exit choice remains available. Deferred work keeps its
durable cutoff and resumes on restart.

An explicit retry releases only pending candidates from failed assignments.
Preparation re-reads and groups them under the current policy. Old failed jobs,
attempt counters and successful memory items remain intact. The retry key is
retained so repeated admission does not mint duplicate requests. `MAX_TOKENS`,
malformed output and validation failures are not automatically retried with an
identical request. Transient provider interruptions keep bounded retries.

Safe attempt logs include actual model, thinking, candidate count, output cap,
attempt, completion reason, usage and elapsed time. No raw source bodies,
prompts, keys, provider response text or reasoning are logged. Retained items
become canonical Memory items; the existing hot-brief limits remain 24 items
and 4,000 characters, so not every retained item must appear in the hot brief.

## Persistence and validation

Alembic `20260909_0090` and embedded SQLite v10 add thinking snapshots and
Memory execution/retry fields. Released v1-v9 manifests remain immutable.
Clean v10 and v9-to-v10 schema digests must match; upgrade verification compares
every pre-existing column value, including encrypted keys, without logging it.

Deterministic tests cover batch cardinality, four provider payloads, stopped
responses, exact ID matching, settings scopes, key preservation and migration.
Actual model quality is a separate direct user check: use the same 32 synthetic
experiences with similar events but distinct motives in each of the four
profiles; inspect each summary against its source and compare usage/time.
Do not reset real completed candidates or insert duplicate production memories
to perform this comparison. Automated fixture success is not a claim of
semantic accuracy from Gemini.

UI provenance: **LOCAL**. Existing feature components and form controls are
reused for browser and static/Tauri rendering; no additional design system,
remote asset, feature-to-feature import or source worktree is introduced.
