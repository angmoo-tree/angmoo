# Backend domain map and import contract

현재 백엔드는 `app/domains/<업무>/<역할>`로 구성합니다. 기능과 코드 위치를 이해하려면 [Backend ARCHITECTURE](../../backend/ARCHITECTURE.md)를 먼저 읽고, 여기에서는 **검사하는 경계와 예외의 의미**를 확인합니다. `public.py`, `application`, `ports`, `infrastructure`를 모든 업무에 만드는 규칙은 현재 기여 규칙이 아닙니다.

이전 T2.5·L1~L4 구조와 당시 수치는 [역사적 도메인 지도](backend-domains-t2-5-history.md)에 보관합니다. 그 문서의 옛 target tree와 public API 의무는 당시 전환의 기록입니다. 실제 PR·설치·후속 CI 결과는 [백엔드 전환 결과](refactor-backend-results.md)에 있습니다.

## 업무와 역할

`identity`, `characters`, `worlds`, `world_characters`, `device_home`, `world_packages`, `social`, `relationships`, `routines`, `routine_posts`, `chat`, `memory`, `runtime`, `local_bot`, `character_lore`, `media`, `tree`, `operations`가 현재 업무 소유 범위입니다. 새 업무를 추가할 때는 실제 기능과 호출 관계를 설명하고 소유 범위도 함께 등록합니다. 모든 업무에 같은 파일 세트가 필요한 것은 아닙니다.

- `router`는 HTTP 입출력과 오류 변환을 담당합니다. HTTP와 worker에 공통인 권한·상태 전이는 `service`가 담당합니다.
- `service`는 해당 업무의 실행 순서와 저장 경계를 소유합니다. 필요할 때 `repository`로 SQL을 분리합니다. 같은 업무의 Session과 기존 commit/rollback 계약을 유지합니다.
- `models`는 소유 업무의 ORM 모델이고 `schemas`는 입출력 형태입니다. 공통 `app.models`는 하나의 Base를 제공하며 도메인 모델을 역으로 import하지 않습니다.
- `contracts`, `policies`, `utils`, `exceptions`, `constants`는 실제 값·판정·오류·도구가 있을 때 사용합니다. 순수한 판정에 DB·HTTP·SDK 실행을 섞지 않습니다.

## 다른 업무의 기능 사용

다른 업무의 지원 `service`, `schemas`, `contracts`를 실제 소유 경로에서 명시적으로 사용합니다. 하위 파일을 외부 계약으로 제공할 경우 정확한 경로를 정책의 `entries`에 기록합니다. 형제 파일이나 모든 하위 파일까지 자동 공개하는 wildcard는 사용하지 않습니다. 검토한 오류 타입도 정확한 entry로 노출할 수 있습니다.

다른 업무의 `models`, `repository`, `router`를 도메인에서 직접 가져와 상태 전이·권한·저장 계약을 우회하지 않습니다. 여러 업무를 함께 읽거나 같은 transaction에서 처리해야 하는 구체적 협력은 상위 `app/runtime`에서 구성합니다. 도메인이 `runtime`을 역으로 import해서 서비스를 찾지 않습니다.

순환 import, 서비스가 자기 router를 호출하는 흐름, 공통 Base·오류·도구가 제품 업무를 역으로 불러오는 의존은 금지합니다. `main`은 앱과 runtime을 생성·연결합니다. 공유 통신·SDK 연결은 `integrations`, 업무별 외부 요청·응답 처리는 해당 도메인의 `client`, 공유 Gemini 생성·embedding adapter와 provider 계약·registry는 `providers`, credential 해석은 `credentials`가 담당합니다.

## 파일과 검사의 관계

| 파일 | 의미 |
| --- | --- |
| `security/architecture_import_baseline.json` | 현재 Python 파일·import edge·외부 import의 재현 가능한 목록 |
| `security/architecture_import_policy.json` | 업무 소유 범위·역할·정확한 지원 entry·필요한 잔존 계약 |
| `scripts/ci/generate_architecture_inventory.py` | 현재 코드로 목록을 생성하고 stale 결과를 확인 |
| `scripts/ci/check_architecture_boundaries.py` | 방향·역할·순환·예외·완료 범위의 파일 배치를 검사 |
| `scripts/ci/check_refactor_preservation.py` | 불변 원본과 현재 source·함수·test node·API·ORM 계약을 대조 |

전체 전환 범위는 정책의 `refactor.complete`와 업무 목록으로 표현합니다. 개별 파일만 선택해 새 규칙을 적용하는 부분 scope는 종료합니다. 새 도메인과 사용되지 않는 옛 계층 파일도 검사하므로, import가 없다는 이유로 소유권 없는 파일이 통과하지 않습니다. 제거한 scope·entry·호환 항목을 정책에 남겨 두어도 실패합니다.

Import 목록을 재생성하면 사실이 갱신됩니다. 허용 규칙이 자동으로 완화되는 것은 아닙니다. 새 의존 때문에 실패하면 실제 책임과 호출을 확인합니다. 예외나 지원 entry를 추가할 때도 저장 계층 전체를 열거나 도메인 역방향·순환 검사를 끄지 않습니다.

## 필요한 잔존 경로

역사 migration이 사용하는 schema helper와 지원 Hosted 확장의 import는 [호환 계약](backend-compatibility.md)에 정확한 소비자·실제 구현·유지 이유를 기록합니다. 정책의 `retained_modules`는 이 파일의 존재를 허용할 뿐, 그 import를 일반 경계 검사에서 제외하지 않습니다. 새 제품 코드는 실제 소유 역할을 사용합니다.

임시 업무 집합과 전달 서비스는 소비자 전환·원래 객체/동작의 검증 후 제거합니다. 제거를 위해 빈 파일이나 같은 전달 클래스를 다시 만들어 두지 않습니다. `public_main.py`의 기능은 `app/main.py`의 단일 앱 생성 구현으로 승계하며 과거 migration alias와 구분합니다.

## 검증할 때

기여 내용에 해당하는 업무 회귀와 구조 검사를 실행합니다. 공통 DB·앱 생성·패키징 변경은 전체 백엔드와 지원 실행 경로를 함께 확인합니다. 테스트 위치를 옮기면 기존 node의 일대일 이동과 수집·fixture·CI 명령을 연결합니다. 이전 경로가 없어서 pytest가 아무 테스트도 실행하지 않은 결과를 통과로 기록하지 않습니다.

SQLite가 원본이며 FTS5·LadybugDB는 재구성 가능한 파생 데이터입니다. 과거 PostgreSQL·Neo4j 자료는 역사 또는 정적 비교 증거입니다. 해당 문자열이 있는 파일을 삭제 대상으로 추정하지 않고, 현재 runtime·migration·fixture의 실제 역할을 확인합니다.
