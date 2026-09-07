# Angmoo Backend Architecture

Angmoo 백엔드는 **업무별 폴더 안에서 HTTP, 업무 흐름, 저장, 입출력 형식을 나누는 FastAPI 애플리케이션**입니다. 게시물 문제는 `social`, 대화 문제는 `chat`, 기억 문제는 `memory`에서 시작합니다. 같은 업무 안에서는 `router`, `service`, `repository`, `models`, `schemas`처럼 역할을 드러내는 이름을 사용합니다.

이 문서는 기능을 추가하거나 버그를 수정할 때 코드의 위치와 연결 방식을 이해하기 위한 설명서입니다. 구조 전환의 PR·테스트·설치 결과는 [백엔드 전환 결과](../docs/architecture/refactor-backend-results.md)에 기록합니다. 이 문서에 구조가 설명돼 있다는 사실과 특정 배포판의 검증 완료 여부는 구분합니다.

[FastAPI Best Practices](https://github.com/zhanymkanov/fastapi-best-practices#project-structure)의 업무별 구성을 참고했습니다. 원문의 `src/auth`에 해당하는 Angmoo 경로는 `app/domains/identity`입니다. Angmoo의 로컬 실행과 AI 작업에 필요한 `runtime`, `integrations`, `credentials`도 각자의 책임을 가집니다.

## 1. 먼저 어디를 보면 되나요?

문제를 찾을 때는 **업무 → 역할 → 실제 호출자와 테스트** 순서로 따라갑니다.

| 관찰한 문제 | 시작할 위치 | 함께 확인할 내용 |
| --- | --- | --- |
| 다른 World의 게시물이 보임 | `domains/social/service/`, `repository/` | 현재 actor·World 권한, 정렬과 pagination |
| 채팅의 취소 후 늦은 답변이 저장됨 | `domains/chat/service/generation.py` | 요청 상태·lease·버전·결과 적용 transaction |
| 삭제한 기억이 검색 결과에 남음 | `domains/memory/service/`, `repository/` | 원본 상태, 검색 색인, 반환 직전 재검증 |
| 자율활동이 두 번 실행됨 | `domains/routines/service/`, `runtime/resident/` | tick identity, claim, 재시작과 재시도 |
| API의 필드나 HTTP 오류가 다름 | 해당 업무의 `schemas`와 `router` | 응답 모델·nullable·상태 코드·오류 변환 |
| 설치 앱에서만 DB를 열지 못함 | `runtime/persistence/`, `runtime/migrations/` | 실제 데이터 경로·업그레이드·bundle 자원 |
| AI 응답을 해석하지 못함 | `integrations/llm/`, `providers/gemini.py`, 해당 업무의 parser | provider 형식·허용 schema·timeout·호출 수 |

예를 들어 기억이 중복 저장된다면 화면에서 중복 행을 숨기기 전에 Memory의 원본 식별자와 job identity, 조건부 저장, transaction을 확인합니다. HTTP 요청과 worker가 같은 서비스로 들어가는지도 봅니다.

## 2. 프로젝트 구조

```text
backend/
├── app/
│   ├── domains/
│   │   ├── identity/
│   │   ├── characters/
│   │   ├── worlds/
│   │   ├── world_characters/
│   │   ├── social/
│   │   │   ├── router.py
│   │   │   ├── dependencies.py
│   │   │   ├── schemas/
│   │   │   ├── models/
│   │   │   ├── service/
│   │   │   ├── repository/
│   │   │   ├── contracts/
│   │   │   ├── policies/
│   │   │   ├── constants.py
│   │   │   └── exceptions.py
│   │   ├── chat/
│   │   ├── memory/
│   │   └── ...                    # 나머지 업무도 같은 역할 기준 사용
│   ├── config.py                  # 공통 환경 설정
│   ├── models.py                  # 단일 ORM Base
│   ├── database.py                # engine·session 생성과 연결
│   ├── exceptions.py              # 공통 오류
│   ├── pagination.py              # 공유 cursor bytes 변환
│   ├── main.py                    # 앱·lifespan 생성과 서비스 연결
│   ├── api/                       # 공통 HTTP 연결·지원 route 조립
│   ├── runtime/                   # 실행·여러 업무의 협력·시작·종료
│   │   ├── persistence/           # SQLite 구성·모델 등록
│   │   ├── migrations/            # 설치 데이터의 embedded upgrade
│   │   ├── chat/
│   │   ├── memory/
│   │   ├── resident/
│   │   ├── graph_projection/
│   │   └── ...
│   ├── integrations/              # 외부 통신·미디어 변환·SDK 연결
│   ├── providers/                 # 공유 provider 계약·Gemini adapter·registry·fake
│   ├── credentials/               # 비밀 해석·공유 credential 연결
│   ├── core/                      # 공통 보안·동시성·작은 기반 도구
│   └── contracts/                 # 여러 업무가 함께 사용하는 값의 계약
├── alembic/
│   ├── env.py
│   └── versions/                  # 역사적 revision·연결 그래프 보존
├── tests/
│   ├── identity/
│   ├── characters/
│   ├── social/
│   ├── chat/
│   ├── memory/
│   ├── runtime/
│   ├── integrations/
│   ├── migrations/
│   └── conftest.py
├── ARCHITECTURE.md
├── pyproject.toml
├── uv.lock
├── .python-version
├── .env.example
├── logging.ini
└── alembic.ini

저장소 root/
├── .gitignore
├── scripts/ci/
├── security/
└── .github/workflows/
```

위 트리는 역할을 설명하는 대표 구조입니다. 모든 도메인에 같은 파일을 만들 필요는 없습니다. 작은 업무는 `service.py`, 큰 업무는 `service/`를 사용합니다. Python 패키지 해석이 겹치지 않도록 같은 위치에 두 형태를 동시에 두지 않습니다.

`templates/`는 서버 HTML 템플릿을 사용할 때 필요합니다. 현재 의존성 관리 원본은 `pyproject.toml`과 `uv.lock`이므로 `requirements/*.txt`를 별도 수동 관리 원본으로 만들지 않습니다. 개발용 `.env`는 Git과 제품 배포에서 제외하며 저장소 루트의 `.gitignore`를 사용합니다.

## 3. 도메인 안의 역할

| 이름 | 무엇을 담나요? | 무엇을 결정하지 않나요? |
| --- | --- | --- |
| `router` | URL·HTTP method·입출력·HTTP 오류·streaming transport | worker에도 적용돼야 하는 업무 권한·상태 전이 |
| `schemas` | Pydantic 요청·응답의 필드와 값 검증 | DB에 실제로 존재하는 대상의 권한 |
| `dependencies` | 인증·요청 Session·앱에 구성된 서비스 연결 | 업무 처리 순서 전체 |
| `service` | 업무 판단·권한·실행 순서·상태 전이·저장 경계 | HTTP transport나 앱 프로세스 시작 |
| `repository` | 해당 업무의 SQL 조회·저장·조건부 갱신 | 다른 업무의 정책을 우회하는 임의 변경 |
| `client` | 해당 업무의 외부 서비스 연결·요청 문맥·응답 변환 | 공개 여부·권한·저장 자격 판단 |
| `models` | 해당 업무의 table·column·relationship | API에 노출할 필드 선택 |
| `exceptions` | 안정적인 업무 오류 타입·의미 | provider 오류 원문을 그대로 공개하는 처리 |
| `constants` / `config` | 해당 업무의 상수·설정 | 다른 업무 전체의 설정 집합 |
| `policies` | 입력된 값에 대한 순수 업무 판단 | DB·파일·네트워크 I/O |
| `contracts` | 업무 값·명령·결과·필요한 협력 객체의 타입 | 모든 서비스에 강제하는 추상 계층 |
| `utils` | 업무 판단 없는 작은 변환·보조 함수 | 권한·공개 여부·저장 자격 |

기본은 역할별 파일입니다. `repository`, `policies`, `contracts`는 실제 분리할 책임이 있을 때 사용합니다. 간단한 저장은 service에서 SQLAlchemy를 직접 사용할 수 있고, 복잡한 조회나 여러 서비스가 함께 쓰는 SQL은 repository로 분리합니다. 한 함수를 전달하기 위해 서비스·유스케이스·인터페이스를 각각 추가하지 않습니다.

Chat과 Memory처럼 큰 업무는 역할별로 나눕니다. 예를 들어 Chat의 `service/threads.py`, `settings.py`, `messages.py`, `generation.py`, `evidence.py`는 서로 다른 사용자 동작을 소유합니다. `service/` 안에 다시 `application/domain/ports/infrastructure` 전체 계층을 만드는 규칙은 없습니다.

## 4. 업무별로 찾아보기

| 도메인 | 책임 |
| --- | --- |
| `identity` | 로그인·세션·Local owner bootstrap·사용자 설정·credential 정책 |
| `characters` | 캐릭터 정의·초안·Creator·프로필·이미지 설정 |
| `worlds` | World 정의·생성·배너·membership·정의 version·readiness |
| `world_characters` | World 참여·owner control·설정 생성과 승인·Studio lifecycle |
| `device_home` | Local World 목록·Home/Studio 진입·실행 가능 표면 |
| `world_packages` | World 패키지 계약·export/import·검사·lineage·원자 적용 |
| `social` | 게시물·댓글·반응·Feed·Inbox·수동 작성·공개 활동·이미지 요청 |
| `relationships` | 관계 사건·포인트·후보·관계 그래프 조회와 적용 정책 |
| `routines` | 자율활동 설정·계획·슬롯·tick·행동 허용·결과와 활동 로그 |
| `routine_posts` | 자율 글쓰기 입력·문맥·생성 결과·중복과 provenance |
| `chat` | thread·message·검색 계획·근거·응답 생성·취소·streaming |
| `memory` | 기억 후보·항목·회상·원본 재검증·AI 배치·예약·Daypart |
| `runtime` | 실행 상태·진단·lease 판단에 필요한 업무 계약과 서비스 |
| `local_bot` | 로컬 Bot 인증·owner key·지원 HTTP 동작 |
| `character_lore` | 캐릭터 참고 문서·파싱·청크·임베딩·검색 |
| `media` | 여러 업무가 공유하는 미디어 값·오류·검증 계약 |
| `tree` | Tree 게시판의 업무 동작 |
| `operations` | 기존 운영 설정의 의미·조회·저장 |

`domains/runtime`은 실행 상태의 의미와 lease 규칙을 담습니다. 앱을 띄우고 worker를 시작하는 상위 `app/runtime`과 책임이 다릅니다. `Character`는 캐릭터 자체이고 `WorldCharacter`는 특정 World의 참여입니다. 캐릭터가 같아도 다른 World의 대화·기억·관계를 합치지 않습니다.

## 5. 요청과 worker가 서비스를 사용하는 방식

```text
HTTP 요청 → router → service → 같은 업무의 DB 접근 / repository
                         └─→ 필요한 협력 객체·외부 client

runtime의 예약·작업 실행 → 같은 service

main → runtime 조립 → 서비스 생성·연결 → app.state → HTTP dependency
```

Router는 요청을 해석하고 응답으로 바꿉니다. Service는 actor와 대상 scope를 받아 무엇을 허용하고 어떤 변경을 저장할지 결정합니다. 검증을 router에만 넣으면 worker가 같은 규칙을 빠뜨릴 수 있습니다. worker에 같은 정책을 복사하면 두 진입점의 동작이 달라질 수 있습니다.

실제 예는 [Chat 서비스 조립](app/runtime/chat/message_composition.py)과 [Chat dependency](app/domains/chat/dependencies.py)입니다. 조립 모듈이 실제 Thread·Message·Generation 서비스를 만들고, dependency가 앱에 연결된 객체를 요청에 제공합니다. Runtime이 업무 서비스를 역으로 가져오는 방향이며, 서비스가 `app.main`을 import해 실행 객체를 찾지 않습니다.

Memory 후보 저장은 [items service](app/domains/memory/service/items.py)에서 시작합니다. scope·설정·원본의 성공 여부와 공개 범위를 확인하고, 같은 원본의 중복 후보를 판정한 뒤 저장합니다. worker가 돌아간다는 사실이나 LLM의 성공 응답만으로 유효한 기억이 되지는 않습니다.

## 6. 다른 업무와 연결하기

필요한 함수와 타입은 **실제 소유 역할에서 명시적으로 import**합니다.

```python
from app.domains.worlds.service import definition as world_definition
from app.domains.identity.contracts import CredentialMaterial, CredentialPurpose
```

지원되는 호출은 입력·출력·오류와 transaction 참여 방식을 설명합니다. 파일이 `service`라는 이유만으로 모든 내부 helper가 외부 계약이 되는 것은 아닙니다. 다른 도메인의 model이나 repository를 가져와 그 업무의 상태 전이·권한·저장 규칙을 우회하지 않습니다.

```text
main / runtime 조립 → 도메인의 지원 service·schema·contract
도메인 service      → 자기 업무 내부 + 필요한 다른 업무의 지원 기능
도메인 model        → app.models.Base
공통 Base·오류·도구  → 도메인에 의존하지 않음
```

여러 업무의 데이터를 함께 읽거나 원자적으로 지워야 하면 구체적인 협력을 `runtime/<업무>/`에 둡니다. 예를 들어 [계정 삭제](app/runtime/account_deletion.py)는 Identity·Character·World·Memory와 비공개 미디어 정리를 같은 작업으로 조립합니다. Identity 서비스가 삭제 요청을 허용하는지 판단하고, 조립은 같은 Session과 기존 commit/rollback 순서를 유지합니다.

Runtime의 다중 업무 조회는 읽는 범위·권한 재검증·Session 계약이 있는 구체적인 조회입니다. 모든 DB 접근을 runtime으로 옮기거나 임의 cross-domain SQL을 허용하는 규칙이 아닙니다. 순환 의존이 생기면 업무 소유권과 협력 방향을 먼저 확인합니다.

외부 provider, clock, 다른 업무의 제한된 조회처럼 실제 교체 경계가 있으면 작은 Protocol이나 callable을 전달할 수 있습니다. 모든 repository와 서비스에 별도 추상 인터페이스를 요구하지 않습니다. 새 코드에서 집합 `public.py`를 거쳐야 한다는 규칙도 없습니다.

공통 코드도 실제 책임으로 구분합니다. 활동 가능 시간은 [`routines/policies/active_hours.py`](app/domains/routines/policies/active_hours.py), 게시물 검색 문서의 필드·길이 규칙은 [`social/service/search_documents.py`](app/domains/social/service/search_documents.py)가 소유합니다. `core/search_text.py`에는 여러 업무가 쓰는 정규화·LIKE 변환만 남습니다. `core/public_media.py`는 공통 HTTP 미디어 mount, `core/image_generation.py`는 공유 이미지 모델·provider 설정을 연결합니다.

`integrations/llm`은 외부 AI 통신·SDK 연결을, 도메인의 `client`는 업무별 외부 요청과 응답 해석을, `providers/gemini.py`는 공유 Gemini 생성·embedding adapter를 제공합니다. `providers/registry.py`가 선택하는 실제 adapter와 업무별 parser를 함께 확인합니다. SDK 호출이 모두 한 폴더에 있다는 의미는 아닙니다.

`api/v1`에는 기존 URL 그룹·등록 순서를 유지하는 조립과 공통 HTTP 연결이 남습니다. `api/schemas/first_greeting.py`는 실행 결과와 Social 게시물을 합친 HTTP 응답 형식입니다. 이 조립 파일들에 업무 권한이나 SQL을 다시 모으지 않습니다. 지원되는 옛 route import가 필요한 경우에도 실제 HTTP·업무 구현은 한 소유 경로에서 제공합니다.

## 7. 모델·Session·transaction

[`app/models.py`](app/models.py)는 하나의 ORM `Base`를 소유합니다. 개별 table은 각 도메인의 models가 소유하고, [`runtime/persistence/model_registration.py`](app/runtime/persistence/model_registration.py)가 앱 시작과 migration에 필요한 모델을 등록합니다. 모델 등록은 모델의 업무 소유권을 바꾸지 않습니다.

[`app/database.py`](app/database.py)는 engine과 동기 SQLAlchemy `Session`의 생성·연결을 담당합니다. 모듈을 import하는 것만으로 engine을 만들지 않으며, 공식 Local 실행은 명시적인 runtime 구성과 데이터 경로를 전달합니다. 테스트의 `model_fixture_support.py`는 테스트에 필요한 ORM 참조를 모으는 도구이며 제품 코드의 전역 model registry가 아닙니다.

한 업무 변경에 참여하는 함수는 같은 Session을 전달받습니다. Repository를 새로 만들었다는 이유로 안에서 새 Session을 열거나 commit을 추가하지 않습니다. 원래 호출자가 commit하는 함수, flush만 하는 함수, 독립적인 활동 로그 저장은 서로 다른 계약입니다.

예를 들어 World Package import는 여러 모델과 lineage를 함께 반영합니다. World/WorldCharacter seed가 각자 commit하면 중간 실패 시 부분 데이터가 남으므로 Package가 원자 적용을 소유합니다. 반면 기존 Daypart 요약의 그룹별 저장은 실패한 그룹을 rollback하고 다음 그룹을 계속하는 계약을 유지합니다.

Session은 병렬 작업이 함께 쓰는 전역 객체가 아닙니다. 요청이 끝난 Session을 background 작업에 재사용하지 않습니다. 외부 AI 응답을 기다리는 동안 쓰기 transaction을 계속 열어 두지 않고, 결과 적용 시 현재 권한·version·lease를 다시 확인합니다.

## 8. HTTP·검증·비동기 처리

Pydantic은 입력과 응답의 형태를 검증합니다. owner·World·대상의 현재 상태는 service가 확인합니다. UI의 비활성 버튼과 클라이언트가 전달한 ID는 권한 증거가 아닙니다. 인증·cookie·CSRF 같은 HTTP 연결은 dependency와 공통 API 모듈이 담당합니다.

ORM과 응답 schema는 역할이 다릅니다. 암호문·credential·내부 상태를 그대로 직렬화하지 않으며 기존 응답 필드·시간 형식·nullable·오류 body를 유지합니다. Pydantic 모델 반환과 FastAPI `response_model`을 함께 사용할 수 있습니다.

업무 오류를 HTTP 상태로 변환하는 처리는 router 또는 공통 HTTP 경계에서 합니다. 같은 공통 오류도 업무 계약에 따라 다른 HTTP 응답이 될 수 있습니다. 공통 cursor 도구는 bytes 변환을 제공하고, 암호화·World scope·정렬·기본값은 각 업무가 소유합니다.

비동기 I/O는 `await`로 호출합니다. `async def` 안에서 동기 helper를 호출한다고 자동으로 thread pool에서 실행되는 것은 아닙니다. DB·파일·SDK의 실제 실행 경계를 확인합니다. 구조 변경에 동기 Session의 `AsyncSession` 전환이나 라이브러리 업그레이드를 함께 넣지 않습니다.

## 9. 원본 데이터·검색·AI

SQLite가 원본 데이터와 관리 상태를 저장합니다. FTS5와 LadybugDB는 검색·관계 탐색을 위한 파생 데이터입니다. 검색 hit만으로 현재 읽기 권한이나 삭제 여부를 결정하지 않고 원본의 World·관찰 범위·공개 상태를 다시 확인합니다.

LLM은 허용된 문맥을 해석하고 계획·요약·캐릭터 응답을 만듭니다. 코드가 실제 ID·권한·허용 연산·저장 자격·호출 상한을 결정합니다. LLM이 만든 SQL이나 Cypher를 그대로 실행하지 않고 검증한 계획을 허용된 executor로 수행합니다.

반복 작업은 job identity·claim·lease·version으로 중복 실행과 늦은 결과를 제어합니다. Memory 배치의 동의·호출 예산·재시도·종료 저장을 단순한 HTTP background task로 대체하지 않습니다. 이미 취소되거나 종료된 작업이 응답을 늦게 받았을 때 다시 적용되지 않아야 합니다.

Streaming에는 허용된 응답 event만 전달합니다. 내부 planner 출력·reasoning·provider 오류 원문을 공개하지 않고, 실패한 partial 응답을 성공한 원본이나 후속 기억 근거로 저장하지 않습니다. SDK의 숨은 재시도와 fallback도 실제 provider 호출 수에 포함됩니다.

## 10. 앱 생성·설치·마이그레이션

앱과 lifespan의 실제 생성 구현은 [`app/main.py`](app/main.py)의 `create_app`과 `create_lifespan`에 있습니다. `app`은 기존 full profile이고, `public_app`은 Local readiness를 제공하는 public profile입니다. `create_public_app`은 동일 factory에 public profile을 지정하는 연결입니다. 두 profile의 기존 기본값과 health 계약을 보존하며 별도 앱 생성 구현을 복제하지 않습니다.

개발 ASGI의 Local 경로는 `app.main:public_app`이고 공식 sidecar·contributor 실행은 명시적인 RuntimeConfig를 사용하는 `create_public_app`에 연결합니다. 옛 `public_main.py`는 전환을 위한 임시 호환 경로였으며 최종 구조의 진입점이 아닙니다. 파일 이름을 바꾸면서 기본 `create_app()`을 호출하면 profile이 달라질 수 있으므로 지원 export를 확인합니다.

Docker 브라우저 실행과 Windows 설치 앱은 같은 업무 코드를 사용하지만 데이터 경로와 lifecycle이 다릅니다. 설치 앱은 Tauri와 bundled sidecar를 사용합니다. 한 실행이 다른 실행의 DB를 초기화하거나 프로세스를 종료하지 않게 runtime 소유권을 유지합니다.

[`logging.ini`](logging.ini)와 [`runtime/logging_config.py`](app/runtime/logging_config.py)는 앱의 로그 구성을 연결합니다. 반복 factory 호출로 handler를 중복 설치하거나 기존 handler를 닫지 않습니다. sidecar의 JSON stdout·content-free fatal stderr·endpoint·종료 handshake는 서버 access log와 다른 실행 계약입니다. Docker와 bundle에 실제 설정 자원이 포함돼야 합니다.

Alembic은 [`alembic/`](alembic/)과 [`alembic.ini`](alembic.ini)를 사용합니다. `env.py`는 같은 Base의 등록된 metadata를 참조합니다. 역사 revision의 본문·ID·연결 그래프는 보존합니다. 별도로 `runtime/migrations`의 embedded SQLite upgrade가 설치 데이터의 버전을 올립니다. ORM 파일 이동만을 이유로 table·constraint·schema version을 변경하지 않습니다.

과거 migration이 import하는 몇몇 옛 model/schema helper 경로와 지원 Hosted 확장이 사용하는 최소 alias는 명시적인 호환 계약입니다. 실제 구현은 소유 역할 한곳에 있고 같은 객체를 제공합니다. 새 제품 코드가 이 경로를 사용하지 않습니다. 임시 업무 집합이나 사용자가 없는 전달 서비스를 이런 역사적 호환과 혼동하지 않습니다.

## 11. 테스트와 구조 검사

기능 테스트는 업무 가까이에 둡니다. `tests/social`, `tests/chat`, `tests/memory`는 실제 업무 회귀를, `tests/runtime`과 `tests/integrations`는 실행 조립과 통신 경계를 검증합니다. 여러 업무가 사용하는 fixture는 명시적인 공통 지원 파일 또는 소유 테스트 패키지에서 가져옵니다. `conftest.py`의 수집 범위와 네트워크 차단은 그대로 유지합니다.

검증은 사용자가 관찰하는 결과와 저장·권한·실패 경계를 확인합니다. Fake provider로 성공·오류·timeout·호출 횟수를 고정하고, transaction과 업그레이드는 격리된 SQLite 데이터로 확인합니다. 파일 이름만 비교하는 테스트가 기능 회귀를 대체하지 않습니다.

아래 명령은 저장소 루트에서 실행합니다. 환경 준비는 [기여 가이드](../CONTRIBUTING.ko.md)를 따릅니다.

```powershell
uv run --project backend python scripts/ci/generate_architecture_inventory.py --check
uv run --project backend python scripts/ci/check_architecture_boundaries.py
uv run --project backend python scripts/ci/check_refactor_preservation.py --contracts --nodes
uv run --directory backend python -m pytest -q tests/chat
uv run --directory backend python -m pytest -q tests
```

Import inventory는 현재 파일과 의존 관계의 사실이고 import policy는 허용 규칙입니다. Inventory를 다시 생성했다고 새 의존이 승인되는 것은 아닙니다. 다른 도메인의 저장 우회, 순환 의존, 옛 계층의 재도입을 검사하고, 파일 이동으로 테스트가 덜 수집돼 통과하지 않도록 원래 source·test node·API·ORM 계약을 대조합니다.

불변 기준 자료는 새 코드로 덮어쓰지 않습니다. 옛 경로의 임시 호환을 제거할 때는 원래 호환이 제공한 실제 객체와 현재 소유자를 확인하고, 기능 단언을 현재 경로에서 유지합니다. 최종 설치 후보는 새 bundle에서 시작·업그레이드·재시작·실패 복원을 검증합니다. 단위 테스트 통과와 설치 검증·CI·post-merge 결과는 각각의 증거입니다.

## 12. 자세한 계약

- [도메인 경계와 검사](../docs/architecture/backend-domains.md), [역사·확장 호환 계약](../docs/architecture/backend-compatibility.md)
- [기능 보존 지도](../docs/architecture/refactor-feature-preservation.md), [실행 결과](../docs/architecture/refactor-backend-results.md)
- [Embedded runtime 결정](../docs/architecture/embedded-runtime-adr.md), [SQLite 동시성](../docs/architecture/l3-er2-sqlite-concurrency.md)
- [World Chat identity](../docs/architecture/p8-l-d-world-chat-identity.md)
- [Canonical recall](../docs/architecture/p8-l-h-canonical-recall.md), [Graph recall](../docs/architecture/p8-l-i-graph-recall.md)
- [응답 생성과 streaming](../docs/architecture/p8-l-p-evidence-response-streaming.md)
- [Memory batch와 종료 저장](../docs/architecture/p8-l-r-memory-batch.md)
- [Tauri sidecar lifecycle](../docs/architecture/l3-er5-tauri-sidecar-lifecycle.md)

이 문서는 구조·역할·연결·변경 예시를 설명합니다. 세부 API 필드, 모델별 예산 숫자, release 상태는 해당 코드와 상세 계약에서 관리해 중복된 기준이 생기지 않게 합니다.

기능·공통 기반을 함께 바꾸는 경우 [통합 시나리오와 실행 근거](../docs/architecture/refactor-integration-scenarios.md)에서 K/G별 회귀와 migration·실행 환경의 차이를 확인합니다.
