# CI validation and release candidates

## Execution contract

Normal PR and main checks validate changed behavior. A conservative, source-controlled classifier selects a suite; unknown paths, unavailable diffs, shared build/security/CI changes and data migrations run full validation. Required workflow names remain unchanged and always report through a result gate. A justified `not_applicable` result names the change and the omitted scope; it is not a full validation pass.

Backend source edits still select the full backend corpus because runtime composition and cross-domain consumers make a narrow path-only map unsafe. Isolated test edits can select the affected test modules and their consumers. Frontend source changes retain the frontend suite and Windows product build. Runtime lock changes additionally run installer smoke. Installation, upgrade, recovery, data or CI policy changes run the full supported Windows matrix.

The classifier defaults to `active` after the hosted observer comparison recorded in `docs/verification/ci-validation-review-20261014.md`. The explicit `observe` option remains available for future classifier changes: it reports the recommendation while executing full validation. Manual `full` and weekly scheduled full runs may widen selection, never narrow it. Newer commits cancel superseded runs; a cancelled required job never becomes a successful result.

## Test decisions for the 2026-10-14 transition

This audit removes obsolete migration-proof obligations, not product behavior. It does not infer that a fake provider, synthetic database or old-named test is unnecessary. Current import boundaries, API authorization, database initialization, cancellation, terminal-state ownership, World isolation and original-character preservation remain protected.

| Candidate | Decision and replacement |
| --- | --- |
| Chat forwarding retirement replay | Retire `test_chat_forwarder_retirement.py`: its unique obligation was repeatedly proving exact signed historical bodies and assertion fragments. Current behavior remains in `chat/test_service_ownership.py`, `chat/test_response_lifecycle_owner.py`, `chat/test_p8_l_b_chat_domain.py`, identity/evidence/cancel tests and the complete-domain import checker. These execute real current service/repository contracts, including denial order and durable ownership. No Chat product test is deleted. |
| Public factory retirement replay | Retire `runtime/test_public_factory_retirement.py`: the G06 facade deletion was completed. `runtime/test_app_factory_ownership.py`, `runtime/test_asgi_preservation.py`, public-runtime and runtime-composition tests verify factory profile/default/lifespan/cold-import behavior directly. Architecture checks reject old layers. |
| Frozen public/private node counts | Retire `test_refactor_public_node_moves.py` and regular CI's M3/M4 node-name baseline invocation. Current full collection, selection and actual per-phase execution reports replace historical 604/641 counts. Removing a current selected node from a shard report still fails. |
| Refactor preservation CLI | Remove the routine historical source-body/API/ORM replay from CI. Historical records and CLI remain available for past-refactor review; they no longer force all future tests or implementation bodies to retain past names or ASTs. Current domain architecture, migration schema contract, functional tests, and complete collection are authoritative. |
| Other evidence/security tests | Retain tests of secret allowlists, provenance and append-only reviewed evidence: the secret scanner still consumes those records. A historical name does not make a live security consumer obsolete. |
| Search deadline diagnostics | Retain and repair: acknowledge arrival independently from progress, require an NN packet only when publication is acknowledged, and separately force a dropped packet. Both cases must deadline, terminate/join and reject late success; cancellation remains tested. Product timeout and nonblocking progress semantics are unchanged. |
| Frontend/browser fixtures | Retain Next/static, narrow viewport, locale and visual fixture checks. `ui-foundation` and fake providers are test infrastructure, not unused product features. They cover distinct shipped entry paths. |
| Native/installer matrices | Retain supported data predecessors, failure recovery, data/key preservation and Defender diagnostics. Separate execution timing and transfer payloads; old schemas are still supported user data. |

No deletion percentage or 10–20 minute time cap is a requirement. Rebalance shards only if measured remaining skew warrants it. Preserve previous proof records in Git rather than creating another immutable test-name census.

## Download trust and preparation reuse

`setup-uv` is pinned by full SHA, with uv/Python/tool versions unchanged. Vec1 sources and SQLite headers retain their source-controlled SHA-256 digests. Temporary network errors have three bounded attempts; invalid bytes, oversized inputs, permanent HTTP errors and TLS failures fail immediately. Every cache hit is rehashed. The optional source cache publishes complete verified bytes atomically; cold user/Docker builds still retrieve the same official sources. Native binaries are built per target rather than reused across incompatible platforms.

## Release validation

PR/main success and release-candidate validation are separate states. Select a fixed main commit and run the full candidate workflow. Record its source/tree, run/attempt, supported predecessor union, installer hashes, SBOM/provenance and signing status. Publish only the exact validated final files; rebuilding or signing changes bytes and requires identity reconciliation and applicable checks. These workflows do not automatically publish a release or install into a developer's existing Angmoo profile.

## Recovery and evidence

For classifier uncertainty, widen to full. For cache corruption, quarantine only the named CI cache entry and retrieve the original fixed source. Never disable hashes, remove required checks or use an administrator merge override to obtain green status. Retry transient infrastructure errors; repair deterministic failures first.

Coverage reports belong to one source/tree and one run attempt. A retry of backend shards therefore needs a fresh complete four-partition proof: rerun the affected Core workflow as a unit, not one failed partition mixed with three earlier successes. Independent successful Local Smoke or Windows Installer workflows do not need to be restarted. The same rule applies to the installer's selected predecessor report set. Diagnose the failed step first; a retry is not a substitute for fixing a reproducible test or workflow error.

Track local implementation, focused local checks, hosted checks, human review, main checks, candidate checks and user checks independently. Compare wall/queue/retry time and artifact bytes by profile, not a blended average. Execution evidence and the I00–I55/R00–R08 ledger are recorded in `artifacts/ci-modernization-20261014/`; this guide describes contracts, not an assertion that all those stages have passed.
