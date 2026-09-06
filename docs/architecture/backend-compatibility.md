# Backend historical and extension compatibility

새 업무 코드는 실제 소유 도메인의 역할 파일을 사용합니다. 여기에 기록한 옛 경로는 현재 앱을 구현하는 다른 계층이 아니라, **기존 설치 데이터의 업그레이드와 별도로 배포되는 지원 확장**이 사용하는 정확한 import 계약입니다. `backend/ARCHITECTURE.md`가 현재 코드 배치의 기준입니다.

## 왜 일부 옛 경로를 남기나요?

이미 배포된 데이터는 역사적 SQLite migration 순서를 통해 현재 버전에 도달합니다. Alembic revision의 본문과 연결 그래프도 그대로 보존합니다. 이 파일들이 가져오는 함수의 위치를 현재 구조에 맞춘다는 이유로 역사 파일을 다시 쓰면, 검증한 업그레이드의 입력 자체가 달라집니다. 그래서 실제 모델과 schema builder는 소유 도메인에 두고, 필요한 옛 이름만 같은 객체로 연결합니다.

반대로 현재 제품과 테스트의 호출처를 모두 옮긴 임시 `public.py`, 전역 DTO·service 집합, 전달만 하는 Chat 서비스는 이 이유에 해당하지 않습니다. 원래 제공하던 값·호출·검증을 현재 소유자에서 확인한 후 제거합니다. `public_main.py`도 이 목록의 영구 호환 대상이 아닙니다.

## 과거 migration이 사용하는 경로

아래 경로는 `backend/app/`을 기준으로 읽습니다.

| 기존 경로 | 실제 소비자 | 유지하는 책임 |
| --- | --- | --- |
| `domains/worlds/domain/reserved_roles.py` | SQLite v2→v3 | `worlds/contracts`의 예약 역할 값·판정과 동일한 객체 |
| `domains/worlds/infrastructure/definition_repository.py` | SQLite v2→v3 | `worlds/service/definition.py`의 정의 읽기·hash·readiness 함수 연결 |
| `domains/worlds/infrastructure/sqlalchemy_models.py` | SQLite v2→v3 | `worlds/models.py`와 같은 ORM class identity |
| `domains/worlds/infrastructure/sqlalchemy_reserved_roles.py` | SQLite v2→v3 | 실제 예약 역할 처리의 지원 함수 연결 |
| `domains/world_characters/infrastructure/__init__.py` | SQLite v2→v3가 역사 WC 하위 모듈을 import할 때의 package 초기화 | 실제 `world_characters/models.py`의 `CharacterActiveWorld`·`WorldCharacter` class 2개를 같은 객체로 re-export. 빈 package marker가 아님 |
| `domains/world_characters/infrastructure/sqlalchemy_models.py` | SQLite v2→v3 | `world_characters/models.py`와 같은 참여 모델 |
| `domains/world_characters/infrastructure/sqlalchemy_setup_models.py` | SQLite v2→v3 | 같은 설정·적용 모델과 schema 계약 |
| `domains/chat/infrastructure/world_scope_migration.py` | SQLite v3→v4·Alembic 0084·model binding migration·`runtime/persistence/sqlite_schema.py`의 과거 버전 metadata | 검증한 역사적 World Chat 변환 본문 |
| `domains/chat/infrastructure/sqlalchemy_models.py` | SQLite v5→v6·Alembic 0086 | 실제 Chat 모델 및 요청 schema builder의 같은 객체 |
| `domains/chat/infrastructure/model_binding_migration.py` | SQLite v6→v7·Alembic 0087 | 기존 model binding 데이터 변환 |
| `domains/memory/infrastructure/sqlalchemy_models.py` | SQLite v4→v5·Alembic 0085 | 실제 Memory 모델에서 제공하는 schema 상수·builder |
| `domains/memory/infrastructure/batch_models.py` | SQLite v8→v9·Alembic 0089 | 실제 배치 모델의 table 목록·schema builder |
| `domains/social/infrastructure/sqlalchemy_subjective_context_models.py` | Alembic 0088 | 실제 Social 모델의 create/drop schema 함수 2개 |
| `core/db.py` | 역사적 Chat 변환·Alembic 0089 | `app/models.py`의 단일 Base만 같은 객체로 연결 |

같은 namespace의 `__init__.py`가 필요한 경우에도 업무 구현을 추가하지 않습니다. WC infrastructure package는 위 두 같은 class를 제공하는 역사적 초기화 계약을 유지하며, 다른 빈 marker와 구분합니다. 이 목록의 정확한 경로를 유지한다는 결정이 형제 파일이나 새로운 하위 계층을 만드는 허용은 아닙니다. 특히 `world_scope_migration.py`의 역사적 변환 본문을 현재 데이터 모델로 자동 재생성하지 않습니다.

대표적인 실제 import는 SQLite v2→v3의 `World`, `WorldCharacter`, `WorldActivityRepertoire`, `WorldCommunityProfile`, 예약 역할 상수와 `ensure_no_specific_role`, `world_contract_hash`, `refresh_world_contract`입니다. Memory의 옛 두 파일은 `MEMORY_SCHEMA_V1_TABLES`·`create_memory_schema_v1`·`drop_memory_schema_v1` 및 `MEMORY_BATCH_TABLES`·`create_memory_batch_schema`를 실제 `memory/models/items.py`와 `batch.py`에서 가져옵니다. Social 0088의 두 함수는 `create_subjective_context_schema`, `drop_subjective_context_schema`입니다. Chat 0086은 실제 `chat/models.py`의 `create_response_request_schema`, `drop_response_request_schema`를 호출합니다. 각 파일의 명시적 import·`__all__` 또는 동일 module alias가 가리키는 실제 소유자에서 전체 export를 확인할 수 있습니다.

역사적 경로의 제거 조건은 지원 upgrade·downgrade·이전 버전 schema 생성 및 그 회귀의 소비가 종료되거나, 별도로 승인·검증한 호환 전환이 완료되는 것입니다. 폴더 정리의 일정만으로 지원 버전을 중단하지 않습니다. 현재 지원하는 migration이 소비하는 동안에는 제거 기한을 임의로 정하지 않습니다.

## 별도 배포되는 Hosted 확장

| 지원 import | 현재 구현 | 보존하는 계약 |
| --- | --- | --- |
| `app.services.hosted_configuration` | `app.runtime.extensions.hosted_configuration` | 설정·prompt provider 등록, 오류, 조회, 해제 및 동일 registry 상태 |
| `app.services.runtime_boundary` | `app.runtime.extensions.resident_adapter` | Resident adapter·오류·등록·해제 및 기존 Gateway 호출 계약 |

이 두 파일은 지원 버전의 확장이 이미 사용하는 import를 연결합니다. 별도 registry나 정책 구현을 복사하지 않습니다. Local 코드에서는 실제 `runtime/extensions` 소유자를 사용합니다. 확장 배포판의 소비자 전환과 호환 종료가 확인되기 전에는 현재 저장소 내부 소비자가 없다는 이유만으로 제거하지 않습니다.

제거 조건은 지원 확장의 설정·prompt provider와 Resident adapter 호출자가 실제 소유 경로 또는 새 명시적 버전 계약으로 전환되고, 등록·조회·해제·오류·동일 상태의 계약 검증을 완료하는 것입니다. 이 구조 전환에서 지원 Hosted 확장의 배포 또는 별도 제품 기능 완료를 선언하지 않습니다.

## 검증과 변경

- `security/architecture_import_policy.json`은 정확한 잔존 module과 문서화된 이유를 기록합니다. 완료된 scope의 미등록 옛 파일은 import되지 않아도 구조 검사에서 실패합니다.
- 잔존 경로가 같은 객체를 제공하는지, 모든 ORM이 하나의 Base·metadata를 사용하는지 확인합니다. module alias가 있어도 별도 모델이나 engine을 만들지 않습니다.
- 역사적 Alembic revision·embedded migration 원문과 schema 자료는 불변 기준에 대조합니다. 새 설치의 초기화뿐 아니라 지원 이전 버전에서의 업그레이드·재실행·실패 복원도 검증합니다.
- 호환 경로 등록은 도메인의 역방향 의존·다른 업무의 저장 우회·순환 의존을 허용하지 않습니다. 해당 코드의 실제 import도 일반 경계 검사를 통과해야 합니다.

최종 PR·설치·post-merge 상태와 정확한 commit은 [백엔드 전환 결과](refactor-backend-results.md)에서 확인합니다. 이 문서는 유지해야 하는 호출 계약의 이유를 설명합니다.
