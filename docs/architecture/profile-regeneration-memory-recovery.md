# Local profile regeneration and Memory recovery

Issue #317 / PR #318 changes product behavior after the completed refactor.

Local profile/repertoire generation has no application daily character or owner
quota. Each explicit new request uses a fresh idempotency key; a transport retry
reuses its key. The running-job guard and explicit provider consent remain.
An unapproved candidate or failed generation does not replace the active approved
profile/repertoire. The preflight response no longer advertises daily quota fields.
No database migration or deletion of historical attempts is required.

The Gemini provider adapter reads SDK enum `.value` instead of Python's enum
display string. STOP remains STOP, MAX_TOKENS and SAFETY remain non-success reasons,
and unknown values cannot become STOP. Memory still validates the full structured
response, all decisions and canonical evidence before atomically storing items.

After a failed write transaction rolls back, the current lease can record elapsed
time and available token usage. A structured `memory_batch_outcome` event contains
only the job ID, safe model/code, attempt, normalized reason and numeric telemetry.
It excludes keys, prompts, response bodies and experience excerpts. A stale lease
cannot overwrite another worker's diagnostic state.
Failures use WARNING so the shipped default records them; completion diagnostics
remain INFO. This does not change application-wide logging configuration.

The Memory UI distinguishes a previous failure from the next scheduled run and
offers the existing explicit retry. Polling completion refreshes the item list and
evidence detail. Successful selection may choose skip for every experience, so
completion does not guarantee a new memory item. Existing bounded Memory retry,
source fences and opt-in rules are unchanged; simultaneous schedule times do not
need to be separated.

The immutable refactor evidence is retained. The append-only post-refactor change
manifest records exact preflight schema changes and removed quota bindings against
the signed implementation commit. Each removed binding must exist in that commit's
parent with the recorded AST and be absent both in the commit and current source.

The affected frontend surfaces are LOCAL. They use existing semantic styles and
shared Next/static components. Deterministic backend and browser fixtures verify
the transitions without calling a real provider or changing contributor data.
CI, Docker USER CHECK and installed-app USER CHECK remain separate gates.
