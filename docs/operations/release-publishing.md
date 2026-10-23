# Release publishing

The publisher verifies fixed candidate identities before creating a release, uploading its assets or
publishing it. The public 0.1.0 release already exists; this document
describes the reusable publishing procedure, not a request to republish it.
All ten dispatch inputs are identities, not an approval bypass:

- `source`: full main-history candidate SHA; `tag`: `release-v0.1.0`.
- `windows_run`, `windows_attempt`, `windows_artifact`: successful full Windows
  run and original build artifact, including its final validation receipt.
- `candidate_run`, `candidate_attempt`, `candidate_artifact`: successful
  Container Candidate main run and complete, unexpired four-image artifact.
- `review_ref`: full main-history commit containing reviewed release evidence and
  release notes. A documentation-only commit can follow the fixed product source.
- `operation`: defaults to `verify`; publication uses `draft` or `publish`.

The workflow runs only from main in the canonical repository. It checks out the
reviewed main publisher in `release-tools`, checks product source ancestry, then
checks out that exact product revision separately in `product`. The product must
be a clean Git root at the requested SHA. Adapter files, the bootstrap template,
LICENSE and Termux guides are packaged only from that product checkout. A release
API repair can therefore resume an immutable candidate without rebuilding it or
silently packaging newer launcher code. The operation receipt separately records
the tooling SHA; it does not change existing release asset bytes.

The publisher verifies actual run event,
attempt, source, artifact ID/digest/expiry, Windows full receipt, source metadata,
SPDX subject and signed GitHub EXE attestation. It checks the attestation's
producer workflow, source digest and hosted-runner requirement; local provenance
JSON alone cannot establish producer trust.

Before publication, add these files through normal main review under
`docs/releases/0.1.0/`: `p5.json`, `notes.ko.md`, `notes.md`.
Use `p5.example.json` as the schema outline, replacing all placeholders with
actual records. The report references exact successful Core CI, Local Smoke and
Security workflow runs, the tested EXE, four platform digests, and the Windows
user's concrete test record. The verifier retrieves referenced CI outcomes and
requires the installer/candidate identities to agree. A single approval boolean is
insufficient. Android remains `experimental-not-certified`; physical-device findings and
limitations must be described in both notes. Remove `NOT_RELEASED`/TODO only
after the actual release review. Templates are intentionally not publishable evidence.

`verify` can validate candidates before official tags/images exist. It reports
candidate validity and publication readiness separately and makes zero remote
writes. `draft`/`publish` additionally require the existing tag to resolve to
the same source, both matching GHCR indexes and completed release review. Missing or
expired artifacts require renewed validation of the new actual bytes; never
reuse an old EXE receipt for a rebuilt EXE.

Only the original bilingual NSIS EXE, original Windows SHA256SUMS, SPDX,
provenance, LICENSE, THIRD_PARTY_NOTICES, verified attestation bundle, reviewed
Termux tools/guides, KO/EN notes, release-manifest.json and RELEASE-SHA256SUMS
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
GITHUB_TOKEN triggers another workflow; inspect the actual image run and both
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
New note sources compose English before Korean; frozen legacy sources keep
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
