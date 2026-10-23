# Angmoo 0.1.0 verification scope

Product source: `a2ee4a6962b33806bfb48f9c94213f01287efffc`.
The release review is a subsequent documentation-only commit. It does not
rebuild or relabel the product payloads.

## Original producer evidence

| Evidence | Original source run, attempt 1 |
| --- | --- |
| Core CI | [39875906006](https://github.com/angmoo-tree/angmoo/actions/runs/39875906006) |
| Local Smoke | [39875905986](https://github.com/angmoo-tree/angmoo/actions/runs/39875905986) |
| Security and Governance | [39875906053](https://github.com/angmoo-tree/angmoo/actions/runs/39875906053) |
| Container Candidate | [39875922401](https://github.com/angmoo-tree/angmoo/actions/runs/39875922401), artifact `12467874849` |
| Windows full | [39875906000](https://github.com/angmoo-tree/angmoo/actions/runs/39875906000), EXE artifact `12469727071` |

All runs completed successfully at the product source. [p5.json](p5.json) binds
the four platform manifest digests, CI identities and exact EXE hash.
Full Windows validation covers clean install, rollback and upgrades using data
version fixtures 1–40, not forty previously released product versions.
The EXE is not Authenticode signed. Its exact-source GitHub hosted-workflow
attestation was verified separately.

## Human Windows acceptance, 2026-10-23

Maintainer `jingujeon` installed and used the candidate EXE with SHA-256
`c708dafbacfa6224705c944758f82269609f9967ba31e9331ebe75f90dd2693b`.
After checking detected English and timezone behavior, the maintainer stated
“window 설치 본 문제없는거같은데” and explicitly requested continuation of
L043–L063. This records that acceptance without inventing additional human
test cases. The confirmation was received in the release working session.

Read-only physical-install checks resolved actual opened file paths and matched
the payload manifest, desktop and sidecar hashes to the product source. The
final 10:50 KST check reported `identity_verified`, `installation_state=verified`
and `running_state=not_observed` after the application had been closed. Earlier
running checks were `corroborated` because mapped image names retained installer
staging paths; executable-code checks agreed, but those were not promoted to
fully verified running identity. No reinstall or LocalCache deletion was used.

During use, the actual DB recorded `en-US`. After a Pacific timezone change and
restart it recorded `America/Los_Angeles`, not `America/New_York`. The current
display and scheduling call paths use the confirmed user environment. Daily
memory scheduling was disabled in that sample, so no scheduled-memory execution
is claimed. Later OS changes are not represented as a permanent timezone lock.

The pre-upgrade stopped backup and post-upgrade read-only data-version-41 check
had equal counts: users 1, Worlds 5, characters 12, World memberships 11, provider
credential records 4, memories 6, threads 2, posts 160, relationship policies 5.
These counts corroborate preservation, not a full semantic comparison of every
record or a new credential-provider test. Private backups, keys, conversation
bodies and raw device logs are not published with this evidence.

## Scope boundaries

- Native amd64 and ARM64 candidate runners passed runtime, native-module,
  security and 19 selected memory contracts per architecture. Fresh-data restart
  checks preserved SQLite, media and the secret, with zero provider calls.
- The exact images passed 23 policy/first-memory regressions per architecture
  locally (ARM64 through QEMU). English/Korean UI selection persisted on reload
  in an isolated candidate browser check.
- The human acceptance does not certify every AI response, new autonomous SNS
  behavior, a long-duration run, or Android performance.
- Android remains `experimental-not-certified`. Earlier phone observations are
  source-specific. Some Samsung Android 14 firmware terminated a Termux native
  child during screen-off despite wake-lock and optimization exclusion. A
  universal Android memory threshold or background-execution guarantee is not
  claimed. Public-download smoke and any later device run are separate results.

## 한국어 요약

관리자는 후보 Windows 설치본을 사용하고 영어·Pacific 시간대 감지를 확인한 뒤
문제가 없다고 판단하여 나머지 정식 배포를 요청했습니다. 실제 설치 파일의 소스와
데이터 버전 37→41 전후 주요 레코드 수 보존을 별도로 확인했습니다. 실행 중
메모리 매핑 경로의 부분 확인과 종료 후 설치 파일의 완전한 식별을 구분했습니다.
이 사용자 확인을 새 AI 품질·장시간 자율활동·Android 실기기 인증으로 확대하지
않습니다. 한영 출시 안내와 P5에는 동일 원본 EXE·이미지·CI 식별자를 사용합니다.
