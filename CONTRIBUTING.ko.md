# Angmoo 기여 가이드

[English](CONTRIBUTING.md) | 한국어

공개 workflow는 각 Pull Request를 `public-only`, `hosted-fast`,
`hosted-full` 중 하나로 분류하지만 private workflow를 자동 실행하지
않습니다. hosted validation이 필요하면 maintainer가 정확한 commit SHA를
검토한 뒤 직접 실행합니다. fork 코드는 private source, repository secret,
production credential을 전달받지 않습니다.

Angmoo 공개 실험 버전 개선에 참여해 주셔서 감사합니다. Issue와 Pull Request는
한국어와 영어 모두 사용할 수 있습니다. 번역 내용이 다르면 영어 문서를
기준으로 합니다.

## 개발 환경

1. `README.ko.md`의 빠른 시작 순서로 PostgreSQL+pgvector, backend, frontend를
   실행합니다.
2. dependency는 `uv sync --frozen`과 `pnpm install --frozen-lockfile`로
   설치합니다.
3. 실제 provider key나 production data 대신 synthetic data와 fake provider를
   사용합니다.
4. 변경에 맞는 최소 테스트와 frontend lint/build를 실행합니다.

production credential, 실제 사용자 데이터, OpenClaw runtime 자료, admin 또는
maintenance control, backup, log, trace, upload, hosted infrastructure 설정을
Issue나 PR에 포함하지 마세요.

## Issue와 작업 범위

- 작업을 시작하기 전에 Issue에서 해결할 문제와 public 범위를 합의합니다.
- API, DB migration, LangGraph state/result, community, credential/security,
  lease/retry contract에 미치는 영향을 적습니다.
- 큰 설계 변경은 바로 구현하지 말고 Issue 또는 Discussion에서 먼저 논의합니다.

## Branch, commit과 Pull Request

- 공개 범위 안에서 가장 작은 변경으로 나눕니다.
- 변경 이유, 사용자 또는 contract 영향, 실행한 테스트와 남은 gap을 기록합니다.
- intentional breaking change는 maintainer 사전 승인, 필요한 migration과
  release note가 있어야 합니다.
- 제출한 기여는 별도 표시가 없는 한 Apache License 2.0으로 제공하는 데
  동의한 것으로 처리됩니다.

## GitHub Actions Gate

변경에 해당하는 backend test, frontend lint/build, public exporter와 security
검사를 실행합니다. Pull Request에서는 다음 CI job이 통과해야 합니다.

- `hosted-impact`
- `backend-contract`
- `frontend`
- `quickstart`
- `security-export`
- `dependency-audit`

이 저장소가 공개 기여의 공식 원본입니다. `hosted-impact` 결과는 maintainer가
별도 private integration을 실행해야 하는지 분류할 뿐, public workflow에서
private source를 읽거나 실행하지 않습니다.

## Hosted validation

다음 변경에는 `requires-hosted-validation`이 필요합니다.

- provider request와 credential
- resident orchestration, prompt와 trace
- scheduler, worker와 media
- migration
- authentication, authorization, ownership와 privacy

hosted validation은 maintainer가 production과 분리된 환경에서 synthetic data와
제한된 test credential로 수행합니다. contributor에게 production DB, KMS,
Oracle, SSH 또는 hosted-service credential을 제공하지 않습니다. staging
성공은 production 승인이나 배포를 의미하지 않습니다.

보안 문제는 public Issue에 작성하지 말고 `SECURITY.md`의 비공개 신고 절차를
사용해 주세요.
