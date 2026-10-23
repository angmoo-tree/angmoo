# Manual social source admission

## Problem and implementation

Successful manually written like/unlike/post/reply events are deliberately
`audit_only`. Today previously delivered these events while situation capture
used generic event visibility (`eligible` only). Capture could consequently
raise `situation_source_not_admitted` before an Inbox/Feed/Routine provider call.

The fix preserves event classification and generic recall/projection policies.
A pure Relationships source-basis contract validates event/evidence identity,
current Social visibility, participant access and bounded ancestry. Runtime
composes that contract through Today's references port and Memory's canonical
adapter. Event-time content fingerprints and current delivered post versions
remain separate; neither a retained `PostLike` row nor an AI execution is
required for a valid manual transition.

Only a final delivered background record with its canonical source revision can
be captured. Restored delivery proofs and current source facts must agree again
at apply/read boundaries. Situation validation v6 retains v2-v5 support and the
existing language, parent/result binding, deletion-summary and correction rules.
Raw evidence remains invisible and permission caches remain context-specific.
There is no migration, provider retry, timeout increase, new writer or automatic
replay of failed historical activities. No user-facing UI text changed.

## Local verification

The focused regression uses real source writers, Today, durable SQLite receipts,
application, canonical recall/hydration and bounded read batches. Negative cases
cover changed sources, missing/forged delivery, legacy revisions, blocks,
membership, visibility, evidence ambiguity, ancestry cycles and invalid results.
Actual FTS5 and the verified Windows Vec1 0.7 extension are used with synthetic
embeddings; no external provider is invoked. A 13-event canonical batch performs
five SELECTs and no writes. Reusing a reader does not retain capture permissions.

The final source regression passed 32 cases, and the subsequently added bounded
batch regression passed one case (33 distinct focused cases). The architecture
inventory/boundary check and whitespace check passed. Wider affected regression
results and deployment evidence are recorded separately in the task report.

Run from `backend` with the verified Vec1 extension path and external network
isolation enabled:

```powershell
$env:ANGMOO_TEST_VEC1_EXTENSION = '<verified vec1.dll path>'
$env:ANGMOO_DENY_EXTERNAL_NETWORK = '1'
.\.venv\Scripts\python.exe -m pytest -q tests/runtime/test_manual_social_situation_sources.py
```

Also verify affected Today/source writers, SNS capture, receipt/apply, proof guards,
prepared pages, language eligibility, parent/result recovery and Chat receipt
regressions. The architecture inventory/boundary checker and `git diff --check`
cover the changed import graph. Full backend/frontend suites are not required
for this internal backend change. Execution outcomes are recorded in the local
task evidence and implementation plan; local tests are separate from remote CI.

## Deployment and rollback boundary

Build both ARM64 OCI images from the same clean local source SHA. Preserve the
current launcher, image roots, complete data directory, encryption secret and
logs. Verify a stopped-state backup before installation, verify every existing
data file unchanged after installation and before starting, then compare health,
source identity, stored counts and the actual phone screen.

An old image does not understand a new v6 run. If rollback is needed after new
work has been accepted, stop and assess those runs first; do not downgrade a
live canonical store or silently discard post-upgrade data. The pre-upgrade
archive remains a recovery option, not an automatic restore command.

Natural AI activity quality, all phone power-management behavior and release
publication are distinct gates. This patch neither adds test AI calls nor
changes the user's autonomous-activity settings.
