# SNS/Chat situation and SNS query language verification — 2026-10-18

Implemented on `feat/preparation-output-language`, following preparation commit
`3470e070aee1f87bb50becfe1fd96b06b248f7d9`. Local scope only.

## Change and preserved contracts

- A pure shared locale validator and language-name mapper retain ko/en variants
  as stored codes while naming Korean/English in generation instructions.
- Other valid tags are preserved; malformed or injected supplied tags fail
  before transport. A genuinely absent environment retains its English default.
- SNS Feed/Inbox/combined selectors and SNS/Chat situation descriptions use
  admitted snapshots. Changing the live locale never rewrites an accepted call.
- Chat Supervisor still follows the current question language. Character speech,
  target IDs, query fallback, call/repair budgets and prior preparation markers
  retain their existing policies. Tendency analysis is explicitly out of scope.
- No frontend, dependency, schema, worker or runtime environment change.

## Local evidence

All pytest commands used `ANGMOO_DENY_EXTERNAL_NETWORK=1` and the locked local
environment (`uv run --frozen --no-sync --directory backend python -m pytest -q`).

The eight related files in the integrated plan initially produced 172 passed,
8 failed. The failures were new-test assumptions, not product failures: one
BCP-47 tag was valid despite its name; CRG uses its own persona policy wording;
and SituationPolicySnapshot is a typed value rather than a dictionary. Tests
were corrected to the actual contract without weakening product validation.

The two affected test files then passed **59/59**. The additional actual
Supervisor transport regression passed **1/1**. Together the final versions of
these files cover **181 distinct related cases** (the original 180 plus one),
with unaffected passing cases reused rather than rerunning the whole suite.

Coverage includes ten locale variants at real selector transport, combined
selection, invalid restored input, absent/disabled situations, CRG reply versus
situation language, actual situation receipt and memory application, existing
query fallback, and prior routine/topic preparation. Fake provider transport
verifies instructions and persistence; it does not prove real AI prose quality.

The import inventory was regenerated for the new shared imports. The architecture
boundary checker passed without allowlist exceptions. No full backend/frontend
suite, GitHub Actions, real API request, Docker rebuild or installed-app test was
run for this change.
