# Angmoo 기여 가이드

[English](CONTRIBUTING.md) | 한국어

Angmoo 개선에 참여해 주셔서 감사합니다. 공식 저장소는
`angmoo-tree/angmoo`입니다. Issue와 Pull Request는 한국어와 영어 모두
사용할 수 있으며 번역 내용이 다르면 영어 문서를 기준으로 합니다.

## 작업 전 확인

- `docs/public/architecture.md`와 `docs/public/contribution-map.md`를 읽습니다.
- 최신 `main`에서 branch 또는 fork를 만듭니다.
- synthetic data와 fake provider만 사용합니다. credential, 개인정보, 원문
  log, backup, 실제 사용자의 World Package를 제출하지 않습니다.
- 변경을 증명하는 가장 작은 deterministic test를 추가하거나 수정합니다.
- 기능 변경과 관계없는 대규모 refactoring을 한 PR에 섞지 않습니다.

기능·버그·구조 변경은 범위를 먼저 합의할 수 있도록 Issue 선행을
권장합니다. 작은 문서 수정과 오탈자 교정은 Issue 없이 PR을 제출할 수
있습니다. Issue 연결은 기계적으로 강제하지 않습니다. 관련 Issue가 있으면
PR 본문에 `Closes #번호` 또는 명시적 reference를 남깁니다.

## 로컬 개발과 검사

기여자 기준선에는 Git과 Docker Compose 2.22.0 이상이 필요합니다. repository
root에서 전체 개발 stack을 시작합니다.

```powershell
docker compose -f compose.yml -f compose.dev.yml up --watch
```

checkout한 공개 Dockerfile을 build하고 frontend, backend, PostgreSQL,
scheduler, Neo4j, projector를 모두 시작합니다. source 변경은 Compose Watch가
sync하거나 rebuild합니다. 개발 데이터를 지우지 않고 종료하려면 다음을
실행합니다.

```powershell
docker compose -f compose.yml -f compose.dev.yml down
```

host Python, uv, Node.js, pnpm version 차이를 막기 위해 같은 개발 container
안에서 검사를 실행합니다.

```powershell
docker compose -f compose.yml -f compose.dev.yml exec -T backend uv run python -m pytest -q
docker compose -f compose.yml -f compose.dev.yml exec -T backend uv run alembic upgrade head
docker compose -f compose.yml -f compose.dev.yml exec -T backend uv run python ../scripts/check_ci_policy.py
docker compose -f compose.yml -f compose.dev.yml exec -T frontend pnpm lint
docker compose -f compose.yml -f compose.dev.yml exec -T frontend pnpm typecheck
docker compose -f compose.yml -f compose.dev.yml exec -T frontend pnpm build
```

제품 shell 변경은 Core CI의 필수 Chromium smoke도 실행합니다. repository가
고정한 Node·pnpm 도구를 host에서 사용할 수 있는 기여자는 provider 호출이나
DB write가 없는 동일한 fake-backend suite를 다음처럼 실행할 수 있습니다.

```powershell
cd browser-tests
pnpm install --frozen-lockfile
pnpm exec playwright install chromium
pnpm test
```

기본 port는 `3100`이며 이미 실행 중인 frontend를 사용할 때는
`ANGMOO_E2E_BASE_URL`을 지정할 수 있습니다. 실제 사용자 데이터가 담긴
profile을 이 검사 대상으로 사용하면 안 됩니다.

required `local-core-smoke`는 release target build, image 취약점·secret scan,
SPDX SBOM 검증과 격리된 Linux clean-clone lifecycle fixture도 실행합니다.
PostgreSQL·Neo4j test state는 폐기 가능하며 provider 관련 검사는 fake
provider만 사용하고 외부 모델을 호출하지 않습니다.
## Pull Request와 merge 권한

모든 변경은 PR을 통해 `main`에 들어갑니다. required checks 10개는 다음과
같습니다.

- `backend`
- `frontend`
- `migration-postgres`
- `local-core-smoke`
- `local-autonomy-smoke`
- `local-full-graph`
- `oss-boundary`
- `dependency-license`
- `dco`
- `architecture-boundary`

`windows-local-smoke`, `codeql`은 advisory check로 유지합니다. Advisory는
실패를 무시한다는 뜻이 아니며 실패 원인과 required 승격 조건을 기록하고
보안 finding은 해결하거나 명시적으로 판정해야 합니다.

외부 기여자는 PR을 제출하며 `main`에 직접 push하거나 PR을 merge할 수
없습니다. required checks 통과와 conversation 해결 뒤 저장소 오너가 최종
검토하고 merge합니다. 1인 maintainer 기간의 `required approvals: 0`은 자기
PR에 공식 Approve를 할 수 없는 교착을 피하기 위한 설정이며, 오너 검토를
없애거나 외부 기여자에게 merge 권한을 준다는 뜻이 아닙니다.

## 라이선스와 DCO

별도 표시가 없는 기여는 `GPL-3.0-only`로 제공됩니다. 모든 사람의 commit은
Developer Certificate of Origin 1.1을 확인하는
`Signed-off-by: Name <email>` trailer를 포함해야 합니다.

```powershell
git commit -s
```

DCO 1.1은 기여물을 제출할 권리가 있음을 확인하는 절차이며 프로젝트
라이선스를 대신하지 않습니다. Dependabot에는 저장소 검사기가 확인하는 좁은
bot 예외만 허용합니다.

## 계약과 구조 변경

REST/OpenAPI, Alembic, 일과·SNS·관계 그래프, 권한, credential, lease/retry,
사용자 데이터 경계는 호환성 계약입니다. 의도적인 breaking change에는 Issue,
필요한 migration 또는 호환 계획, focused test와 rollback 경로가 필요합니다.

T2.5의 점진적 domain-first 계약은
`docs/architecture/backend-domains.md`에 있습니다. backend 동작을 추가하기
전에 그 문서에서 소유 domain 또는 runtime 영역을 정합니다. domain 간 import는
`app.domains.<name>.public`을 사용하며, 다른 domain의 내부 module이나 수평
`services`, `models`, `schemas`, `cruds` 경로에 새로 의존하지 않습니다.

L2.5 frontend 제품 shell 계약은
`docs/architecture/frontend-product-shell.md`에 있습니다. 이동을 완료한 route는
`@/features/<feature>/public`을 통해서만 feature를 import합니다. feature끼리 서로의
내부 module을 deep import하지 않으며, 제품 중립적인 `shared` primitive는 feature나
legacy data client를 import하지 않습니다.

import inventory는 현재 사실을 기록하고
`security/architecture_import_policy.json`은 목표 규칙과 검토된 exact legacy
예외를 기록합니다. 기존 예외는 줄일 수 있지만 CI를 통과시키기 위해 늘려서는
안 됩니다. 다음을 실행합니다.

```powershell
uv run --project backend python scripts/ci/generate_architecture_inventory.py --write
uv run --project backend python scripts/ci/check_architecture_boundaries.py
uv run --project backend python scripts/ci/check_frontend_architecture_boundaries.py
uv run --directory backend python -m pytest -q tests/test_t2_5_architecture_boundaries.py tests/test_l2_5_frontend_architecture_boundaries.py
```

구조 전용 PR은 범위를 좁게 유지합니다. package 이동 PR에 동작 변경, migration,
provider 설정, dependency major, transaction 의미, 일괄 formatting,
Hosted·Private·Production 설정을 섞지 않습니다.

보안 문제는 public Issue에 작성하지 말고 `SECURITY.md`의 비공개 신고 절차를
사용해 주세요.
