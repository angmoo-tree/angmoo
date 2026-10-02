# Frontend brace-expansion 보안 패치 검증 — 2026-10-02

SNS·Chat 이미지 PR #354의 merge SHA `39d912fe9c5c794a95d4e2c9833424386c91cb95`에서 제품 CI 필수 11개와 Windows 설치 네 job은 통과했다. 같은 SHA의 별도 Dependabot 보안 업데이트 run `36949048240`은 기존 `brace-expansion: 5.0.9` override 때문에 `security_update_not_possible`로 실패했다. 이 override는 이미지 브랜치 이전 main에도 있었다.

GitHub Advisory [GHSA-q2hr-2g5m-vwhr](https://github.com/advisories/GHSA-q2hr-2g5m-vwhr)는 v5 계열의 패치 버전을 `5.0.12`로 명시한다. 저장소 alert #23은 `frontend/pnpm-lock.yaml`의 개발용 transitive dependency를 지목했다. Production-only 감사의 성공과 이 개발 의존성 경고를 구별한다.

P13의 정상 후속 수정 절차로 main에서 `fix/frontend-brace-expansion-security` 브랜치를 만들었다. 기존 override를 `5.0.12`로 올리고 pnpm 11.22.0으로 lockfile을 생성했다. YAML 구조 비교로 바뀐 패키지·integrity·두 minimatch 참조만 확인했으며 다른 의존성·importer·설정·제품 코드·runtime deadline·CI 조건은 그대로다. integrity는 공식 npm registry의 배포 자료와 일치한다.

로컬 검증:

- `pnpm install --frozen-lockfile`: PASS. supply-chain 정책 430개 entry 검증.
- 개발 의존성을 포함한 `pnpm audit --json`: 430개 의존성, 모든 severity에서 취약점 0.
- license/NOTICE check: PASS. runtime inventory의 기존 NOTICE는 동일하고 별도 version 변경이 필요하지 않았다.
- lint·typecheck·Next build·static build: PASS.
- Frontend architecture·design·architecture inventory: PASS.

사용자 Docker watch 원본 HEAD·미커밋 변경은 별도로 보존한다. 제품·개인 설치판·실서비스 이미지 품질을 위 의존성 검사로 판정하지 않는다. 후속 PR의 최종 head CI와 병합 후 push main CI, alert의 실제 fixed 상태는 완료 후 workspace 실행 receipt 및 PR 본문에 기록한다. 원래 실패 updater run은 실패 기록으로 유지한다.

Refs #348 · 후속 대상 [PR #354](https://github.com/angmoo-tree/angmoo/pull/354).
