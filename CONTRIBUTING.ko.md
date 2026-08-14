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

## 로컬 설치와 검사

commit된 lockfile만 사용합니다.

```powershell
uv sync --frozen --directory backend
pnpm --dir frontend install --frozen-lockfile
```

변경 범위에 맞는 검사를 실행합니다. 전체 Local OSS gate는 다음과 같습니다.

```powershell
uv run --project backend python scripts/check_ci_policy.py
uv run --directory backend python -m pytest -q
pnpm --dir frontend lint
pnpm --dir frontend typecheck
pnpm --dir frontend build
```

PostgreSQL과 Neo4j 검사는 폐기 가능한 로컬 서비스를 사용합니다. provider
관련 검사는 fake provider를 사용하며 외부 모델을 호출하지 않아야 합니다.

## Pull Request와 merge 권한

모든 변경은 PR을 통해 `main`에 들어갑니다. required checks 9개는 다음과
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

`windows-local-smoke`, `architecture-boundary`, `codeql`은 처음에는 advisory
check입니다. Advisory는 실패를 무시한다는 뜻이 아니며 실패 원인과 required
승격 조건을 기록하고 보안 finding은 해결하거나 명시적으로 판정해야 합니다.

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

T2는 현재 import inventory를 기록합니다. domain 중심 구조 전환은 후속
refactoring gate에서 진행하며 owner·이유·제거 조건 없이 legacy 예외를 늘리지
않습니다.

보안 문제는 public Issue에 작성하지 말고 `SECURITY.md`의 비공개 신고 절차를
사용해 주세요.
