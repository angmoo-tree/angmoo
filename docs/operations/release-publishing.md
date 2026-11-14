# Release publication

## Current policy: 0.1.5 and later

Publish backend, frontend and PostgreSQL for Linux amd64/ARM64 (six immutable OCI payloads, three indexes), plus the source-bound Termux tools. Do not build or publish a Windows NSIS installer. Preserve existing Releases unchanged.

Run `Release Common Assets` at the same final main source as `Container Candidate`. It packages matching Psycopg source and licenses and project notices without the native installer. Supply `assets_run`, `assets_attempt` and `assets_artifact` to `Release Publish`; leave the three `windows_*` inputs empty. The verifier checks source, workflow, successful main run, attempt, archive digest and every bounded file hash. Legacy 0.1.3 → 0.1.4 migration tools remain at the 0.1.4 Release and their original source; do not rerun that migration for PostgreSQL → PostgreSQL updates. The historical native ARM64 SQLite migration qualification below remains a manual 0.1.4 check, not a Windows gate for new releases.

P5 still binds exactly the final source, six image digests and three successful main CI runs. For 0.1.5 use `postgresql_update` with `source_version: 0.1.4`, `target_schema: 5`, and exactly `docker-amd64`, `docker-arm64`, `termux-arm64`; each records fresh install, update, backup/restore, recovery and current features with evidence. Keep 600-second Termux idle evidence and bounded real AI evidence. Omit `windows` and `windows_user_check`; foreign/native receipts are rejected, not accepted as a substitute. This PR's S0–S5 does not perform or claim those later release checks.

Write matching English/Korean release notes: dependency and compatibility changes, supported artifacts, Windows native retirement/no migration, Docker/Termux update and backup commands, verified scope and limits. A green PR does not constitute release acceptance. Reuse tested original bytes; never rebuild only for publication. Tag/registry/Release publication remains separately authorized after review.

## Historical publication contract: through 0.1.4

The following describes frozen releases and the retained native manual tooling. Windows requirements here do not apply to 0.1.5+.


The publisher verifies fixed candidate identities before creating a release, uploading its assets or
publishing it. The public 0.1.0 release already exists; this document
describes the reusable publishing procedure, not a request to republish it.
All ten dispatch inputs are identities, not an approval bypass:

- `source`: full main-history candidate SHA; `tag`: the matching product tag,
  for example `release-v0.1.4` for the PostgreSQL transition.
- `windows_run`, `windows_attempt`, `windows_artifact`: successful full Windows
  run and original build artifact, including its final validation receipt.
- `candidate_run`, `candidate_attempt`, `candidate_artifact`: successful
  Container Candidate main run and complete, unexpired six-image artifact (three services × two architectures).
- `review_ref`: full main-history commit containing reviewed release evidence and
  release notes. A documentation-only commit can follow the fixed product source.
- `operation`: defaults to `verify`; publication uses `draft` or `publish`.

The workflow runs only from main in the canonical repository. It checks out the
reviewed main publisher in `release-tools`, checks product source ancestry, then
checks out that exact product revision separately in `product`. The product must
be a clean Git root at the requested SHA. Adapter files, the bootstrap template,
LICENSE, Docker migration tools, PostgreSQL source/license bundle and bilingual
migration/runtime/backup guides are packaged only from that product checkout. A release
API repair can therefore resume an immutable candidate without rebuilding it or
silently packaging newer launcher code. The operation receipt separately records
the tooling SHA; it does not change existing release asset bytes.

The publisher verifies actual run event,
attempt, source, artifact ID/digest/expiry, Windows full receipt, source metadata,
SPDX subject and signed GitHub EXE attestation. It checks the attestation's
producer workflow, source digest and hosted-runner requirement; local provenance
JSON alone cannot establish producer trust.

Before publication, add these files through normal main review under
`docs/releases/<version>/`: `p5.json`, `notes.ko.md`, `notes.md`.
Use [the existing schema outline](../releases/0.1.0/p5.example.json), replacing all placeholders with
actual records. The report references exact successful Core CI, Local Smoke and
Security workflow runs, the tested EXE, six platform digests, and the Windows
user's concrete test record. The verifier retrieves referenced CI outcomes and
requires the installer/candidate identities to agree. A single approval boolean is
insufficient. Android remains `experimental-not-certified`; physical-device findings and
limitations must be described in both notes. Remove `NOT_RELEASED`/TODO only
after the actual release review. Templates are intentionally not publishable evidence.

`verify` can validate candidates before official tags/images exist. It reports
candidate validity and publication readiness separately and makes zero remote
writes. `draft`/`publish` additionally require the existing tag to resolve to
the same source, all three matching GHCR indexes and completed release review. Missing or
expired artifacts require renewed validation of the new actual bytes; never
reuse an old EXE receipt for a rebuilt EXE.

Only the original bilingual NSIS EXE, original Windows SHA256SUMS, SPDX,
provenance, LICENSE, THIRD_PARTY_NOTICES, verified attestation bundle, reviewed
Termux tools/guides, source-bound `angmoo-migrate.exe` and `.py`, the migration-tool
manifest, native PostgreSQL resource manifest, PostgreSQL/Psycopg source bundle,
bilingual migration/runtime/backup guides, KO/EN notes, release-manifest.json and
RELEASE-SHA256SUMS
are staged. The manifest hashes assets except itself and the aggregate checksum;
the aggregate checksum includes the manifest and excludes itself. DB, credentials,
fixtures, Defender tools and raw internal logs are never Release assets.
Authenticode status must be described from actual candidate inspection, never inferred
from GitHub attestation.

Creation always starts as a draft. Uploads are downloaded and hashed again before
publication. A failed upload leaves the draft available to resume: rerun the same
inputs, which re-verifies evidence and reuses matching files. Extra assets,
different hashes or changed notes fail; no `--clobber`, deletion or tag movement.
A fully matching already-public Release is reported without republishing.

Release discovery uses the authenticated, paginated release list, including
drafts visible to a writer. The tag lookup endpoint only finds published releases.
Multiple matches, API errors, malformed responses or an exhausted pagination
bound fail closed rather than being treated as absence. See the
[GitHub release API contract](https://docs.github.com/en/rest/releases/releases#list-releases).

Images publish separately on the official tag. Do not assume a tag created with
GITHUB_TOKEN triggers another workflow; inspect the actual image run and all three
registry indexes before Release publication. Publication needs the intended human/API tag
operation and its actual trigger result. No tag is created by Release Publish.

Use the fixed source, run, attempt, and artifact identities above with the default
`verify` operation first. Deleting earlier development releases is outside this workflow's scope.

## Post-publication changes

Source documentation uses `docs/public/termux.md` for English and
`termux.ko.md` for Korean. Release-note sources use `notes.md` and `notes.ko.md`.
The prepared asset names remain `termux.en.md`, `termux.ko.md`,
`release-notes.en.md` and `release-notes.ko.md`.

Preparation selects one complete language pair from the fixed product root or
review ref. Older fixed sources using `.en.md` are supported explicitly; missing
or ambiguous pairs fail instead of falling back to the publisher checkout.
New note sources compose English, a Markdown horizontal rule, then Korean; frozen legacy sources keep
their original order. Tool ZIP contents must match the same product source's
literal bootstrap allowlist, including the command-registration helper only in
sources that declare it. This does not modify an already published release.

Treat released asset identity separately from GitHub's editable description.
If the description changes after publication, keep the asset manifest and
original checksum evidence intact and record the presentation-only difference.
Do not overwrite published checksums or candidate receipts to make an edited
description appear byte-identical to the originally staged notes.

The publisher can leave an existing release unchanged only if its
comparison confirms a complete match. Changed notes, assets or missing registry evidence
may make a later replay fail. Diagnose that state instead of weakening checks,
moving a tag or clobbering files. Preserve multi-platform execution manifests
and any evidence needed by the published verification path when cleaning up tags.

## PostgreSQL 0.1.4 acceptance record

Current P5 adds `postgresql_adoption` with the fixed `source_sha`, source version
`0.1.3` and target schema `5`. Its `platforms` object has exactly `docker-amd64`,
`docker-arm64`, `termux-arm64` and `windows-x64`. Each contains `result: PASS`,
`fresh_install`, `migration`, `backup_restore`, `recovery`, `current_features`
(all true), and an `evidence` reference to the reviewed execution record.

`termux_idle` contains the actual 600-second observation, result, evidence and
`cpu_one_core_percent` (at most 10). `provider_budget` contains cumulative actual
`transmissions` (at most 50), `maximum_rolling_60s` (at most 14), and
`minimum_interval_seconds` (at least 5 when multiple requests were sent).
`real_ai` records its actual result and representative provider evidence. Build
success does not create these records. A missing observation or NOT_RUN cannot
become publication-ready. This acceptance check runs at M8/M9; implementing it
at M6 does not authorize a long load test or claim that final-source tests ran.

Windows full receipts use the three actual PostgreSQL cases; old published
SQLite receipts retain the legacy four-job verification path. The source-bound
resource manifest, EXE, migration tools and OCI labels must agree before public
staging. Actual GUI acceptance remains separate from silent hosted checks.

### Preserved Docker migration host tools

`docker-migration-tools.yml` independently packages the existing Windows Docker host EXE and portable Python adapter, without building the native Angmoo installer. Its explicit `source` must be an immutable main ancestor with product version 0.1.4. `postgresql-docker-qualification.yml` consumes its `tools_run`, `tools_attempt`, and `tools_artifact`; it verifies both the workflow tooling source and the historical product SHA, artifact digest, and individual tool hashes. This retained SQLite 0.1.3 → PostgreSQL 0.1.4 lane does not introduce another migration for 0.1.5. Existing PostgreSQL users use the normal image update path. Common 0.1.5 source/license assets come from `release-assets.yml`.

Docker 호스트용 기존 `angmoo-migrate.exe`·Python 도구는 독립 수동 workflow에서 생산합니다. 이는 Windows 네이티브 설치본 또는 Windows 설치판 → Docker 이전 도구가 아닙니다. 역사적 0.1.3 → 0.1.4 검증은 도구의 별도 run·attempt·artifact를 사용하며, 0.1.4 → 0.1.5는 PostgreSQL 데이터 보존 업데이트입니다.
