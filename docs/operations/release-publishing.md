# Release publishing evidence and operation

P1 implements the tools; P6 alone creates/attaches/publishes the official Release.
All ten dispatch inputs are identities, not an approval bypass:

- `source`: full main-history candidate SHA; `tag`: `release-v0.1.0`.
- `windows_run`, `windows_attempt`, `windows_artifact`: successful full Windows
  run and original build artifact, including its final validation receipt.
- `candidate_run`, `candidate_attempt`, `candidate_artifact`: successful
  Container Candidate main run and complete, unexpired four-image artifact.
- `review_ref`: full main-history commit containing reviewed P5 evidence and
  release notes. A documentation-only commit can follow the fixed product source.
- `operation`: defaults to `verify`; P6 uses `draft` or `publish`.

The workflow runs only from main in the canonical repository, checks source
ancestry before checking out an input revision, then verifies actual run event,
attempt, source, artifact ID/digest/expiry, Windows full receipt, source metadata,
SPDX subject and signed GitHub EXE attestation. It checks the attestation's
producer workflow, source digest and hosted-runner requirement; local provenance
JSON alone cannot establish producer trust.

At P5, add these files through normal main review under
`docs/releases/0.1.0/`: `p5.json`, `notes.ko.md`, `notes.en.md`.
Use `p5.example.json` as the schema outline, replacing all placeholders with
actual records. The report references exact successful Core CI, Local Smoke and
Security workflow runs, the tested EXE, four platform digests, and the Windows
user's concrete test record. The verifier retrieves referenced CI outcomes and
requires the installer/candidate identities to agree. A single P5 boolean is
insufficient. Android remains `experimental-not-certified`; P4 findings and
limitations must be described in both notes. Remove `NOT_RELEASED`/TODO only
after the real P5 review. Templates are intentionally not publishable evidence.

`verify` can validate candidates before official tags/images exist. It reports
candidate validity and publication readiness separately and makes zero remote
writes. `draft`/`publish` additionally require the existing tag to resolve to
the same source, both matching GHCR indexes and completed P5 review. Missing or
expired artifacts require renewed validation of the new actual bytes; never
reuse an old EXE receipt for a rebuilt EXE.

Only the original bilingual NSIS EXE, original Windows SHA256SUMS, SPDX,
provenance, LICENSE, THIRD_PARTY_NOTICES, verified attestation bundle, reviewed
Termux tools/guides, KO/EN notes, release-manifest.json and RELEASE-SHA256SUMS
are staged. The manifest hashes assets except itself and the aggregate checksum;
the aggregate checksum includes the manifest and excludes itself. DB, credentials,
fixtures, Defender tools and raw internal logs are never Release assets.
Authenticode status must be described from actual P5 inspection, never inferred
from GitHub attestation.

Creation always starts as a draft. Uploads are downloaded and hashed again before
publication. A failed upload leaves the draft available to resume: rerun the same
inputs, which re-verifies evidence and reuses matching files. Extra assets,
different hashes or changed notes fail; no `--clobber`, deletion or tag movement.
A fully matching already-public Release is reported without republishing.

Images publish separately on the official tag. Do not assume a tag created with
GITHUB_TOKEN triggers another workflow; inspect the actual image run and both
registry indexes before Release publication. P6 needs the intended human/API tag
operation and its actual trigger result. No tag is created by Release Publish.

## 한국어 운영 계약

P1은 구현, P6는 실제 생성·첨부·공개 단계입니다. 위 입력에 고정된 소스·run·attempt·
artifact ID를 넣고 기본 `verify`로 먼저 확인합니다. 공개 전 후보 검사 성공과
공개 준비 완료는 구분됩니다. 태그·양쪽 GHCR 이미지·P5 자료가 없으면
`draft`/`publish`는 실행을 거부합니다.

P5 자료는 정상 main 검토를 거친 문서 커밋의 `p5.json`, 한국어·영어 출시
안내입니다. 실제 CI 링크·EXE 해시·4개 이미지 digest·Windows 사용자 확인을
기록하며 예제나 P5 완료 체크 하나로 대체하지 않습니다. Android는 실험 범위로
표시하고 P4 실기기 결과와 미검증 제한을 한영 안내에 함께 적습니다.

공개 파일은 검증한 원본과 명시된 공개 자료만 허용합니다. 초안을 만들고 파일을
첨부한 뒤 다시 내려받아 해시를 확인해야 공개합니다. 실패하면 같은 입력으로
재실행하여 동일 파일을 재사용할 수 있으며 다른 내용의 기존 파일·태그를
덮어쓰지 않습니다. 이전 개발 배포 삭제도 이 workflow의 범위가 아닙니다.
