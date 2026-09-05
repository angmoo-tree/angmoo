# Angmoo Backend Architecture

Angmoo 백엔드는 **업무별 도메인 안에 HTTP 처리, 업무 흐름, 데이터 모델을 함께 두는 구조**를 사용합니다. 게시물 동작은 `social`, 대화는 `chat`, 기억은 `memory`에서 찾고, 그 안에서 `router.py`, `service.py`, `models.py`처럼 역할을 드러내는 파일을 따라갑니다.

이 문서는 기능을 추가하거나 버그를 수정하는 기여자가 코드의 위치와 연결 방식을 이해하기 위한 설명서입니다. [FastAPI Best Practices](https://github.com/zhanymkanov/fastapi-best-practices#project-structure)의 도메인별 구성을 바탕으로, Angmoo의 로컬 실행·AI 호출·기억·World 경계를 설명합니다.

> **적용 상태 — 2026-09-05:** AR-0 기준선과 AR-1 검사 지원은 PR #259에서 병합됐습니다. `device_home` 첫 backend 파일럿은 PR #260, merge commit `a55c521b9adad624ae1342b2a7b270abc2237f79`로 병합됐고 역할별 파일과 새 경계 검사를 사용합니다. §8.2의 AR-G0 후속 보존·부분 전환 검사를 바탕으로 공통 설정을 `app/config.py`로, identity 실제 구현을 역할 파일로 옮겼습니다. identity의 옛 `public.py`는 미전환 소비자의 동일 객체 호환만 남아 부분 scope로 관리합니다. 다른 업무와 공통 기반의 상태, 검증·PR·병합 결과는 [보존 지도](../docs/architecture/refactor-feature-preservation.md)와 [백엔드 전환 결과](../docs/architecture/refactor-backend-results.md)에 기록합니다.

> **AR-G2 적용 범위:** 공통 오류 4개는 `app/exceptions.py`, Device Home·Social profile이 함께 사용하는 cursor bytes 변환은 `app/pagination.py`가 소유합니다. 기존 core 모듈은 동시성·middleware 구현과 동일 오류 객체의 export를 유지합니다. 다른 업무 오류·cursor payload·query·실행 계약은 기존 소유 모듈에서 계속 관리합니다. 병합 및 통합 검증 상태는 위 실행 결과 문서에서 구분합니다.

> **AR-B2 Worlds 적용 범위:** World 정의·readiness·생성·배너와 10개 HTTP 경로는 `worlds/models.py`, `schemas.py`, `contracts.py`, `exceptions.py`, `storage.py`, `service/`, `router.py`가 소유합니다. WorldCharacter의 입장·퇴장 HTTP는 WC router가 소유하고, 입장에 필요한 World/membership 조회·seed·정의 version 변경은 Worlds service가 같은 Session으로 협력합니다. Worlds 전체를 완료 scope로 올리지 않고 실제 이전된 역할 module만 검사합니다. `worlds.public` 및 frozen SQLite v2→v3가 사용하는 옛 경로 4개는 같은 객체를 제공하는 추적된 호환 경로입니다.

> **AR-B2 WorldCharacter 기반 적용 범위:** 6개 ORM은 `world_characters/models.py`, 입출력은 `schemas/identity.py`·`schemas/setup.py`, 순수 업무 계약은 `contracts/`, 오류는 `exceptions.py`가 소유합니다. 생성기 통신은 `client.py`, 응답 검증은 `service/setup_validation.py`, Package용 seed는 `service/seed.py`에 있습니다. 소유자·입장·승인·Studio·퇴장·runtime mode·readiness의 실제 업무 흐름은 `service/`, HTTP는 `router/profile.py`·`entry.py`·`setup.py`가 소유합니다. 여러 업무 join과 삭제·runtime busy 검사 및 시작 조립은 `runtime/world_characters/`에 있습니다. 미전환 외부 소비자는 정확한 bridge만 허용합니다. immutable SQLite migration이 사용하는 옛 ORM 경로 두 개는 같은 class 객체의 alias로 유지합니다.


> **AR-B5-A Social 기반 적용 범위:** 게시물·반응·미디어 작업은 `social/models/posts.py`, Feed cursor·관찰·block은 `models/feed.py`, owner 수동 작성·inbox 후보는 `models/manual_writes.py`, 성공 행동의 당시 자기 설명은 `models/subjective_context.py`가 실제 ORM을 소유합니다. 수동 쓰기·관찰·프로필·Today·subjective context의 값과 오류는 `contracts/`, 수동 HTTP 요청·응답은 `schemas/manual.py`에 있습니다. 일반 게시물/agent tool 서비스와 Relationship/projection 전환은 뒤이은 B5 범위입니다. immutable SQLite v7→v8와 Alembic 0088의 subjective-context import는 같은 클래스와 schema helper의 호환만 남습니다. 기존 공통 model export도 같은 클래스를 사용하고 G5에서 최종 조립 위치를 정리합니다.

> **AR-B5-B1/B2 Social 읽기 적용 범위:** `repository/{posts,profiles,media,inbox}.py`는 Social 테이블의 실제 SQL을 소유하고, `service/notifications.py`는 수신자·자기 알림 판단을 수행합니다. `service/posts.py`는 게시물·스레드 읽기, `service/visibility.py`는 삭제·신고·인용·조상 게시물 공개 판단, `service/presentation.py`는 응답 조립을 담당합니다. User와 Character 조회는 각 소유 도메인의 service를 같은 Session으로 호출합니다. 멘션 조회의 한 번의 SQL, 입력 순서·삭제/정지 필터와 nullable 조회를 유지하며, 조회 협력은 flush/commit을 추가하지 않습니다. 기존 `services/community.py`의 쓰기·프로필·Inbox·agent 동작은 아직 실제 남은 구현이며 이어지는 B5에서 이전합니다.

> **Social 저장과 협력:** `service/source_posts.py`는 원본 글·타임라인 글 생성, `repository/reactions.py`는 반응·신고 저장, `repository/profiles.py`는 팔로우 저장을 소유합니다. 이미 검증된 actor의 id/name/display_name을 읽는 협력은 외부 ORM 조회를 대신하는 우회 저장소가 아닙니다. `service/joint_posts.py`의 각 필드 대입과 `notifications.ensure_joint_started_notification`의 query/add는 기존 공동 활동 caller의 Session과 저장 순서를 유지합니다.

> **Social timeline 업무 흐름:** `service/timeline.py::SocialTimelineService`가 원본 글·대꾸·인용·반응·신고·삭제의 실제 권한/흐름/저장 순서를 소유합니다. `runtime/social/timeline.py`는 이미 존재하던 활동 로그·quota·관계 이벤트 처리만 같은 Session으로 연결합니다. WorldCharacter의 현재 World와 멤버십 판단은 `world_characters/service/social_scope.py`에서 수행하며 캐릭터 값을 복사하거나 먼저 읽지 않고 원래 읽기 순서를 보존합니다. 순수 문맥 정제는 `core/context_text.py`, 제한된 topic/게시 결과 표현은 `social/service/activity_results.py`에 있습니다. Identity quota 모델의 역사적 공개 별칭은 G5/B8에서 종료 조건을 검토합니다.

Social의 SQL은 `repository/posts.py`, `profiles.py`, `inbox.py`, `media.py`에서 읽습니다. 다른 업무 ORM을 사용하는 복합 조회는 아직 남은 runtime 전환 범위입니다. `service/notifications.py`는 수신자 없음·자기 자신 알림 제외와 실제 저장 순서를 함께 소유하고, `utils/text.py`·`cursors.py`는 IO 없는 변환만 담당합니다. 기존 SQL helper가 호출하는 `finish_write`는 caller의 지연 commit 구간에서 flush만 하므로, 새 위치를 이유로 commit을 추가하거나 제거하지 않습니다. Community/World Feed의 HTTP DTO는 `schemas/community.py`·`feed.py`에 있습니다. `cruds/community.py`에는 아직 이전하지 않은 여러 업무 조회와 정확한 같은 함수 export가 남으며 B5/B4/G5에서 각 실제 소비자를 전환합니다.

## 목차

1. [프로젝트 구조](#1-프로젝트-구조)
2. [도메인 안에서 코드 찾기](#2-도메인-안에서-코드-찾기)
3. [요청과 작업이 서비스를 사용하는 방식](#3-요청과-작업이-서비스를-사용하는-방식)
4. [다른 도메인과의 연결](#4-다른-도메인과의-연결)
5. [공통 모델과 데이터베이스](#5-공통-모델과-데이터베이스)
6. [HTTP·검증·동시성](#6-http검증동시성)
7. [실행 환경과 외부 서비스](#7-실행-환경과-외부-서비스)
8. [원본 데이터·검색·AI의 역할](#8-원본-데이터검색ai의-역할)
9. [설정·로그·의존성·마이그레이션](#9-설정로그의존성마이그레이션)
10. [변경 위치와 테스트](#10-변경-위치와-테스트)
11. [현재 코드와 목표의 연결](#11-현재-코드와-목표의-연결)
12. [설계 근거와 상세 문서](#12-설계-근거와-상세-문서)

## 1. 프로젝트 구조

Python 패키지 이름은 `app`이고, 업무 패키지는 `app/domains`에 모읍니다. 참고 예제의 `src/auth`에 해당하는 Angmoo 위치는 `app/domains/identity`입니다. `domains`는 업무 모듈을 모으는 폴더이며, 모든 파일에 프레임워크나 DB 의존을 금지하는 계층 이름이 아닙니다.

```text
backend/
├── alembic/                         # 역사 migration 이력의 루트 배치
│   ├── env.py
│   └── versions/
├── app/
│   ├── domains/
│   │   ├── identity/
│   │   ├── social/
│   │   │   ├── router.py            # HTTP 요청·응답
│   │   │   ├── schemas.py           # Pydantic 요청·응답
│   │   │   ├── models.py            # 이 업무의 ORM 모델
│   │   │   ├── dependencies.py      # 요청에 필요한 객체·인증 연결
│   │   │   ├── config.py            # 업무별 설정
│   │   │   ├── constants.py         # 업무 상수
│   │   │   ├── exceptions.py        # 업무 오류
│   │   │   ├── service.py           # 업무 흐름·권한·상태 전이
│   │   │   └── utils.py             # 업무 판단 없는 보조 함수
│   │   ├── chat/
│   │   ├── memory/
│   │   ├── worlds/
│   │   └── ...                     # 나머지 기존 업무도 보존
│   ├── config.py                   # 공통 환경 설정
│   ├── models.py                   # 하나의 ORM Base·공유 모델 기반
│   ├── exceptions.py               # 공통 오류 기반
│   ├── pagination.py               # 공통 cursor·limit 도구
│   ├── database.py                 # engine·session factory
│   ├── main.py                     # 목표: 단일 앱 생성·지원 실행 구성 연결
│   ├── runtime/                    # 실행·작업·종료·복구 조립
│   │   ├── persistence/            # 설치 DB 구성·모델 등록 조립
│   │   └── migrations/             # embedded SQLite upgrade
│   ├── integrations/               # 외부 통신·응답 변환
│   ├── providers/                  # 기존 provider 계약·adapter·fake
│   ├── credentials/                # 비밀 해석·접근
│   ├── api/                        # 필요한 공통 HTTP·라우터 조립
│   └── compatibility/              # 실제 소비자가 남은 호환 코드
├── tests/
│   ├── identity/
│   ├── social/
│   ├── chat/
│   ├── memory/
│   └── ...                         # 나머지 업무·runtime·공통 기반
├── templates/                      # 조건부: 서버 HTML을 사용할 때
├── requirements/                   # 조건부: 이 관리 방식을 선택할 때
│   ├── base.txt
│   ├── dev.txt
│   └── prod.txt
├── ARCHITECTURE.md
├── pyproject.toml                  # 현재 의존성·개발 group 유지
├── uv.lock                         # 재현 가능한 의존성 기준
├── .python-version
├── .env.example                    # 비밀 없는 개발 설정 예시
├── .env                            # 선택적 개발 설정·Git/제품 배포 제외
├── logging.ini                     # 앱 기본 level·Uvicorn console 설정
└── alembic.ini                     # backend/alembic 연결

저장소 root/
└── .gitignore                      # 저장소 전체의 제외 규칙
```

`social`의 목록은 역할 설명입니다. 설정이나 보조 함수가 없는 작은 도메인에는 해당 파일이 없어도 됩니다. 현재 `characters`, `world_characters`, `device_home`, `routines`, `routine_posts`, `relationships`, `world_packages` 등의 업무도 자신의 도메인에서 계속 소유합니다. 예제에 없는 기능을 삭제하거나 하나의 거대한 서비스로 합치지 않습니다.

`runtime`, `integrations`, `credentials`는 Angmoo 실행에 필요한 영역입니다. 참조 저장소와 폴더 이름을 맞추기 위해 실행 기능을 없애지 않습니다. `templates`와 `requirements`는 조건부이며, 이번 구조 전환에서 현재 `pyproject.toml`·`uv.lock`을 다른 의존성 관리 방식으로 교체하지 않습니다.

현재 존재하는 `public_main.py`는 G06 전환 중에만 호환 경로로 유지합니다. Local의 명시적 `RuntimeConfig`, 복구, Memory 시작·종료와 각 지원 profile의 계약을 `main.py`의 단일 앱 생성 구현으로 통합한 뒤, 실행·테스트·CI·패키징 소비자를 옮깁니다. 검증 후 호환 파일을 제거하고 그 파일이 없는 후보에서 다시 실행을 확인합니다. 이 목표를 현재 구현 완료로 읽지 않으며, scheduler·DB·Memory의 세부 처리는 소유 runtime과 도메인에 둡니다.

## 2. 도메인 안에서 코드 찾기

### Character 정체성 기반의 현재 위치

AR-B2-B의 첫 전환 범위는 캐릭터 자체의 ORM·입력 schema·handle/프로필 저장·상태 저장·Package seed입니다. `characters/models.py`, `schemas.py`, `exceptions.py`, `contracts.py`, `service/profile.py`, `service/state.py`, `service/seed.py`가 실제 구현을 소유합니다. 관리 화면 전체, Creator workflow, 자율활동과 Local Bot은 아직 뒤이은 전환 범위입니다.

`profile.create_character`의 기존 commit/refresh와 `seed.seed_autonomous_character`의 caller-owned flush-only 저장은 별도 계약입니다. 전자는 일반 저장 캐릭터를 inactive 상태로 만들고, 후자는 World Package 등의 transaction에 참여합니다. `state.upsert_character_state`는 기존 `unit_of_work.finish_write`를 사용하므로 지연 commit 구간에서는 flush만 합니다. 이 차이를 일반적인 repository 규칙 하나로 바꾸지 않습니다.

현재 `app.cruds.community`와 `app.schemas` 등의 옛 소비자 경로는 필요한 같은 함수·class 객체를 단방향으로 재노출합니다. 새 Character 구현은 그 호환 경로를 다시 import하지 않습니다. `characters/public.py`도 WorldCharacter·Package·runtime 소비자 전환 동안 동일 모델/seed 객체를 제공하는 임시 표면이며, 전체 도메인 전환 완료를 뜻하지 않습니다.

### 역할별로 문제 찾기

먼저 **어느 업무의 동작인가**를 찾고, 다음으로 **어떤 역할이 달라지는가**를 찾습니다. 예를 들어 게시물 목록에 권한 없는 World의 글이 섞이면 `social`의 조회·권한 경로를 확인합니다. JSON 필드 이름만 잘못됐다면 같은 도메인의 응답 schema와 router 변환이 출발점입니다.

| 파일 | 담당하는 내용 | 판단 예시 |
| --- | --- | --- |
| `router.py` | URL·HTTP method·입출력·HTTP 오류 변환 | 응답 status나 streaming event가 잘못됨 |
| `schemas.py` | 요청·응답의 형태와 값 검증 | 필수 필드·nullable·형식이 잘못됨 |
| `dependencies.py` | 요청의 인증·session·CSRF·서비스 구성 | 필요한 owner나 실행 설정이 전달되지 않음 |
| `service.py` | 업무 순서·scope·권한·상태 전이·transaction 경계 | 삭제하면 안 되는 항목이 삭제됨 |
| `models.py` | 해당 업무가 소유하는 table·column·relationship | 저장 형태와 ORM 연결을 확인해야 함 |
| `config.py` / `constants.py` | 업무별 설정과 상수 | 설정 의미·고정 code의 소유 위치 |
| `exceptions.py` | 업무 오류와 안정적인 오류 의미 | 없는 항목과 권한 거부를 구분해야 함 |
| `utils.py` | 업무 판단 없는 작은 보조 함수 | 정해진 형식의 문자열을 변환함 |

DB 조회가 복잡하거나 여러 서비스에서 함께 쓰이면 **`repository.py`**에 모읍니다. 순수한 업무 판단을 따로 테스트하고 싶다면 **`policies.py`**, 실제 교체 가능한 외부 경계의 타입이 필요하면 **`contracts.py`**를 사용할 수 있습니다. 이 세 파일은 Angmoo에서 추가한 선택지이며, 모든 서비스가 반드시 통과하는 계층이 아닙니다.

Worlds의 `service/creator.py`는 권한·row version·상태 전이·commit을, `service/definition.py`는 canonical hash와 readiness·정의 조회를, `service/generation_context.py`는 생성에 제공할 World 정보를 소유합니다. 배너 파일 검증·변환·저장은 `storage.py`에 있고, DB commit 실패 시 새 파일을 정리하고 성공 후 이전 파일을 지우는 순서는 creator service에 있습니다. `seed_world`와 system role의 `ensure_no_specific_role`은 전달받은 Session에서 flush만 수행하므로 Package의 원자 import가 commit/rollback을 소유합니다.

World timezone 변경과 자율활동 슬롯 재예약은 기존과 같이 한 트랜잭션입니다. `service/scheduling.py`는 이 변경에 참여하는 한정된 기존 협력 query이며 worker를 시작하거나 commit하지 않습니다. active autonomous resident·enabled activity·idle slot 필터와 UTC/World timezone 의미를 유지합니다. 활동·scheduler 소유권의 AR-B4 전환은 이 함수의 같은 Session 계약을 이어받으며, creator service에서 runtime을 역으로 import하지 않습니다.

외부 서비스 통신을 한 도메인만 소유한다면 그 안의 `client.py`가 가능하고, 여러 업무가 사용하는 AI·이미지·graph 통신은 기존 `integrations`·`providers`에 둡니다. URL 호출·SDK 응답 변환과 업무 권한 판단은 구분합니다.

### 큰 업무도 역할별로 나눕니다

Chat과 Memory는 파일 하나에 모든 동작을 담기 어렵습니다. 필요하면 같은 역할을 작은 모듈로 나눕니다.

```text
memory/
├── router.py
├── schemas.py
├── models.py
├── service/
│   ├── lifecycle.py
│   ├── recall.py
│   └── batch.py
└── repository/
    ├── items.py
    └── batch.py
```

이것도 도메인별 역할 구성입니다. `service/` 안에 다시 `application/domain/ports/infrastructure` 계층을 만드는 규칙은 없습니다. Python이 어느 쪽을 import하는지 혼란이 생기지 않도록 `service.py`와 `service/`를 동시에 두지 않습니다. 작은 함수까지 class·Protocol·factory를 하나씩 만드는 것도 기본값이 아닙니다.

## 3. 요청과 작업이 서비스를 사용하는 방식

업무 동작의 중심은 서비스입니다. HTTP와 예약 작업은 서로 다른 진입점이지만 같은 업무 규칙을 사용합니다.

```text
HTTP 요청 → router → service → DB 접근 / 필요하면 repository
                          └─→ 외부 client

runtime의 예약·작업 실행 → 같은 service
```

Router는 요청을 해석하고 응답으로 바꿉니다. Service는 인증된 actor와 대상 scope를 받아 무엇을 허용하고 어떤 변경을 함께 저장할지 결정합니다. DB 접근이 간단하면 service가 SQLAlchemy session을 직접 사용할 수 있습니다. Repository를 분리했다면 SQL 조회·저장은 repository가 맡고 업무 결정은 service에 남습니다.

### 예: 기억 후보를 만들 때

기존 [Memory write lifecycle](app/domains/memory/application/write_lifecycle.py)은 source의 유효성과 Memory 설정을 확인한 뒤 후보를 저장합니다. 이 파일은 **현재 구조의 예시**이며, 목표에서는 같은 책임을 `memory/service.py` 또는 `memory/service/lifecycle.py`가 맡습니다.

```text
1. 호출자가 actor·World·WorldCharacter·source를 전달한다.
2. 서비스가 실제 scope와 Memory 설정을 확인한다.
3. 서비스가 원본의 성공·공개 범위·현재 유효성을 확인한다.
4. 서비스가 같은 source에 대한 중복 후보인지 판단한다.
5. 허용된 후보와 필요한 상태를 같은 저장 경계에서 반영한다.
```

이 판단을 HTTP router에만 넣으면 worker가 서비스를 사용할 때 빠질 수 있습니다. 반대로 worker 안에 다시 구현하면 같은 source에 서로 다른 규칙이 적용됩니다. `dependencies.py`는 요청 객체를 준비하고, worker는 필요한 실행 객체를 준비하며, 두 경로 모두 같은 서비스 판단으로 들어옵니다.

`utils.py`는 이런 판단을 모으는 이름이 아닙니다. 기억 보존 가능 여부는 업무 규칙이므로 service 또는 분리한 policy에서 찾을 수 있어야 합니다.

## 4. 다른 도메인과의 연결

다른 업무가 필요하면 **소유 도메인이 지원하는 함수와 타입을 명시적으로 사용**합니다. 목표 import 형태는 다음과 같습니다. 아래는 위치 설명이며, 현재 checkout에 이 파일이 이미 존재한다는 뜻은 아닙니다.

```python
from app.domains.worlds import service as worlds_service
from app.domains.worlds import schemas as worlds_schemas
```

이름을 보면 어느 업무의 기능인지 알 수 있고, 해당 서비스는 다른 도메인에 제공하는 함수의 입력·출력·오류·transaction 참여 방식을 설명합니다. `service.py`의 모든 이름을 자동으로 외부 계약으로 간주하지 않습니다. 내부 helper와 지원되는 호출을 구분합니다.

다른 도메인의 `models.py`나 `repository.py`를 직접 가져와 그 도메인의 저장 규칙을 우회하지 않습니다. 예를 들어 Chat이 Memory ORM을 직접 수정하면 Memory 삭제·중복·보존 정책을 빠뜨릴 수 있습니다. Memory가 제공하는 동작을 통해 변경합니다.

```text
상위 앱·runtime 조립 → 도메인의 지원 service·schema·contract
도메인 service      → 같은 도메인 내부 + 필요한 다른 도메인의 지원 기능
도메인 ORM          → app.models.Base
공통 Base·오류·pagination → 도메인에 의존하지 않음
```

- 목표에서는 `public.py`를 매번 거쳐야 한다는 규칙을 사용하지 않습니다. 기존 `public.py` 소비자는 전환 범위에 따라 유지하다가 지원되는 service·schema·contract로 연결합니다.
- 두 도메인이 서로 import하면 공동 작업의 조립을 `runtime`의 구체적인 workflow로 올리거나 필요한 계약을 분리합니다. 모든 업무를 전역 서비스로 옮기지는 않습니다.
- 여러 도메인의 테이블을 함께 읽는 기존 projection은 소유자·읽는 범위·권한 재검증·transaction 조건이 설명된 조회 모듈로 유지할 수 있습니다. 이것이 임의 cross-domain SQL을 허용하는 일반 규칙은 아닙니다.
- 테스트에서 교체해야 하는 provider·clock·저장 경계는 작은 Protocol이나 주입 가능한 객체로 남길 수 있습니다. 모든 서비스에 추상 인터페이스가 필요한 것은 아닙니다.

## 5. 공통 모델과 데이터베이스

### Identity 구현에서 경계를 찾는 예

로그인·세션·프로필 변경은 [identity/service/auth.py](app/domains/identity/service/auth.py), Local owner bootstrap은 [service/local_owner.py](app/domains/identity/service/local_owner.py), 자격 해석·변환은 `service/credential_resolution.py`와 `service/credential_migration.py`에 있습니다. HTTP 입력과 cookie 처리는 `router/`, `dependencies.py`, `browser_session.py`가 소유하고, ORM은 `models.py`, 요청·응답은 `schemas.py`, 비밀을 숨기는 credential과 Local snapshot 타입은 `contracts.py`에서 찾습니다.

Local owner 서비스는 기존 `SqlAlchemyIdentityRepository`에 있던 업무 판단·commit/rollback을 소유합니다. 별도의 전달 전용 use case를 거치지 않고 직접 메서드를 호출하며 테스트는 `clock` 또는 기존 `now`를 주입할 수 있습니다. 잘못된 owner claim의 시도 횟수를 commit하는 동작도 그대로입니다. `_owner_candidates`는 동일 session으로 본인 캐릭터 수·활성 World membership 수·credential 수만 읽는 bootstrap projection이며, 다른 업무의 테이블을 쓰는 일반 repository가 아닙니다.

계정 삭제는 여러 업무와 비공개 미디어를 함께 다루므로 [runtime/account_deletion.py](app/runtime/account_deletion.py)가 실행 순서·동일 session·단일 commit/rollback·미디어 quarantine의 복구와 purge를 소유합니다. Identity 서비스는 확인 문구·이미 삭제된 사용자·demo 계정 허용 여부를 확인하고 주입된 workflow에 같은 `Session`과 사용자 객체를 전달합니다. 두 앱 factory가 workflow를 연결하고 HTTP dependency가 이를 가져옵니다. Identity가 runtime을 import하거나 자기 DB session을 새로 만들지 않습니다.

다른 업무의 router는 공통 HTTP 연결인 [app/api/identity_dependencies.py](app/api/identity_dependencies.py)에서 인증 dependency와 cookie transport의 같은 객체를 사용합니다. 업무 서비스에서 이 HTTP 연결을 사용하지 않습니다. 기존 다른 도메인의 `identity.public` ORM/type 소비자는 후속 전환 때 service/schema/contract로 옮기며 정확한 목록과 종료 단계는 [이동표](../security/refactor_path_map.json)의 `AR-B2-identity`에 있습니다. 이 호환 때문에 전체 identity scope 완료는 AR-B8-A에서 확인합니다.

`models.py`는 위치에 따라 책임이 다릅니다.

| 위치 | 책임 |
| --- | --- |
| `app/models.py` | 하나의 ORM Base·metadata, 실제 공유하는 모델 기반·mixin |
| `app/domains/<업무>/models.py` | 해당 업무의 ORM 모델 |
| `app/domains/<업무>/schemas.py` | HTTP 등 경계의 Pydantic 요청·응답 |
| `app/database.py` | engine·session factory·공통 연결 기반 |
| `app/runtime/persistence` | 실제 설치 DB 경로·수명·필요한 모델 등록 조립 |

목표 관계를 최소한으로 표현하면 다음과 같습니다. **등록이나 engine 생성까지 포함한 구현 예제는 아닙니다.**

```python
# app/models.py: 공통 기반의 목표 형태
from sqlalchemy.orm import DeclarativeBase

class Base(DeclarativeBase):
    pass

# 각 domains/<업무>/models.py에서는 새 Base를 만들지 않고 사용합니다.
# from app.models import Base
```

공통 `models.py`에 업무 table을 모두 다시 모으거나 engine를 생성하지 않습니다. 도메인 ORM을 읽어 metadata를 채우는 등록 함수는 `runtime/persistence`가 소유하고, 앱 시작과 `alembic/env.py`가 필요 시 호출합니다. 공통 Base가 등록 함수를 역으로 import하면 순환 의존이 생기므로 방향을 유지합니다. 별도 필수 `model_registry.py`는 두지 않습니다.

### Transaction은 하나의 업무 변경을 묶습니다

게시물 저장과 관련 사건 기록이 함께 성공해야 한다면 두 작업은 같은 transaction에 참여합니다. 서비스 또는 해당 workflow가 원자성을 정의하고 기존 session·unit of work가 commit/rollback을 담당합니다. 호출받은 repository나 하위 서비스가 각각 commit해서 부분 저장을 만들지 않습니다.

```text
transaction 시작
  → 권한·현재 상태 확인
  → 원본 변경
  → 함께 남아야 하는 사건·작업 상태 기록
  → 한 번 commit
오류 → 함께 rollback
```

이미 시작된 transaction에 참여하는 서비스는 자신이 새 transaction의 소유자인 것처럼 동작하지 않습니다. HTTP에서 호출하는 경우와 여러 도메인을 묶는 workflow에서 호출하는 경우의 소유권을 함께 설명합니다.

외부 AI가 응답할 때까지 SQLite 쓰기 transaction을 열어 두지 않습니다. 필요한 상태를 읽은 뒤 외부 호출을 수행하고, 결과 적용 시 짧은 transaction에서 현재 권한·버전·lease를 다시 확인합니다. 저장과 후속 작업 전달은 기존 durable job/outbox의 누락·중복 복구 계약을 유지합니다. [SQLite 동시성 계약](../docs/architecture/l3-er2-sqlite-concurrency.md)

## 6. HTTP·검증·동시성

### 입력 형태와 업무 권한은 서로 다른 검증입니다

Pydantic은 필수값·타입·형식 같은 입력 검증을 담당합니다. 다음은 역할을 설명하는 독립적인 예제이며 Angmoo의 실제 API 필드 정의를 바꾸는 예제가 아닙니다.

```python
from pydantic import BaseModel, Field

class TextInput(BaseModel):
    text: str = Field(min_length=1)
```

이 검증을 통과했다고 사용자가 특정 World의 기록을 수정할 권한을 얻는 것은 아닙니다. `dependencies.py`에서 실제 owner·session·CSRF 등 요청 보안을 연결하고, 서비스에서 대상 객체와 actor·World·WorldCharacter의 관계를 확인합니다. 내부 worker도 자신의 실행 scope가 필요합니다. UI의 비활성 버튼이나 클라이언트가 보내 준 ID는 권한 증거가 아닙니다.

`Character`는 캐릭터 자체이고 `WorldCharacter`는 특정 World에서의 참여입니다. 같은 캐릭터라는 이유로 다른 World의 대화·기억을 합치지 않습니다. [World Chat identity 계약](../docs/architecture/p8-l-d-world-chat-identity.md)

### 응답은 필요한 데이터만 표현합니다

ORM과 응답 schema는 같은 객체가 아닙니다. ORM의 내부 필드·암호문·credential이 응답으로 나가지 않도록 기존 응답 계약을 유지합니다. Pydantic 응답 모델과 FastAPI `response_model`을 함께 쓰는 것은 유효한 방식입니다. 새 코드의 모델 직렬화는 Pydantic v2 API를 기준으로 하되, 공통 serializer를 도입하며 기존 필드·시간 형식·nullable 의미를 일괄 변경하지 않습니다. [FastAPI 응답 모델](https://fastapi.tiangolo.com/tutorial/response-model/)

업무 오류는 안정된 code와 의미를 가지고, HTTP 상태·응답 body로 바꾸는 처리는 router 또는 공통 HTTP 경계가 맡습니다. Provider 원문·stack trace·비밀을 그대로 사용자에게 전달하지 않습니다. `pagination.py`는 공유 가능한 cursor·limit 도구를 제공하며, API마다 다른 정렬·scope·기본값은 소유 도메인에서 보존합니다.

현재 [`app/exceptions.py`](app/exceptions.py)는 SQLite 동시성 오류 3개와 요청 body 크기 초과 오류를 정의합니다. DB retry·queue와 ASGI middleware는 오류를 발생시키고 처리하는 실행 코드입니다. 이 코드를 오류 선언 파일에 합치지 않습니다. 같은 SQLite busy라도 Social은 HTTP 503, 자율활동 설정은 기존 업무 오류를 거쳐 HTTP 409를 반환하므로 공통 class의 존재가 동일 HTTP 응답을 뜻하지 않습니다.

[`app/pagination.py`](app/pagination.py)의 `encode_cursor_bytes`·`decode_cursor_bytes`는 bytes와 URL-safe Base64 문자열만 변환합니다. Device Home은 JSON cursor를, Social profile은 AESGCM으로 인증·암호화한 cursor를 이 도구에 전달합니다. 암호화 key·version·World/캐릭터/tab scope·timestamp·정렬·limit·업무별 오류는 각 소유 모듈에 남습니다. 따라서 같은 보조 함수를 쓴다는 이유로 두 cursor 형식을 서로 바꿔 사용할 수 없습니다.

### `async def`는 호출하는 도구에 맞춥니다

현재 [DB 기반](app/core/db.py)은 동기 SQLAlchemy `Session`·`create_engine`을 사용합니다. 폴더를 바꾸는 작업에 `AsyncSession` 전환을 포함하지 않습니다. 비동기 I/O는 `await`로 호출하고, 동기 DB·파일·SDK 호출이 event loop를 막지 않도록 기존 실행 경계를 확인합니다. `async def` 안에서 보통의 동기 helper를 호출한다고 FastAPI가 자동으로 thread pool에 옮겨 주지는 않습니다. [FastAPI 동시성 설명](https://fastapi.tiangolo.com/async/)

Session은 변경 가능한 transaction 상태입니다. 같은 Session을 동시에 실행되는 thread·task·worker가 공유하지 않습니다. 작업을 다른 실행 문맥으로 옮길 때도 session의 생성·사용·종료와 transaction 범위가 맞아야 합니다. 요청 session을 종료 후 background 작업에 재사용하지 않습니다. [SQLAlchemy Session 동시성](https://docs.sqlalchemy.org/en/20/orm/session_basics.html#is-the-session-thread-safe-is-asyncsession-safe-to-share-in-concurrent-tasks)

## 7. 실행 환경과 외부 서비스

Angmoo는 Docker의 브라우저 실행과 Windows 설치 앱에서 같은 백엔드 업무 코드를 사용합니다. 설치 앱은 Tauri host와 bundled sidecar를 사용합니다. Host Tauri 개발은 기존 wrapper가 Docker backend를 재사용하며 설치용 sidecar를 별도로 띄우지 않습니다. 별도 Next.js 서버를 설치 앱의 새 필수 조건으로 넣지 않습니다. Docker·Host Tauri 개발·설치 앱은 데이터 경로와 lifecycle이 다르므로 한 실행이 다른 실행의 DB나 프로세스를 종료하지 않도록 기존 조립을 유지합니다. [공개 runtime 구조](../docs/public/architecture.md)

| 영역 | 담당하는 일 |
| --- | --- |
| `main.py` | 목표 단일 앱 생성과 지원 profile의 router·오류·startup/shutdown 연결. 현재 `public_main.py`의 Local 구현은 G06에서 통합·임시 호환·검증 후 제거 |
| `runtime` | 설정·DB·서비스 구성, scheduler·worker·lease·종료·복구 |
| `domains/runtime` | 현재 runtime 상태·진단 등 업무 계약; worker를 실행하는 폴더와 구분 |
| `integrations`, `providers` | 실제 통신, SDK별 요청·응답·오류·usage 변환, fake 제공 |
| `credentials` | 기존 resolver를 통한 비밀 접근과 해석 |
| `desktop/src-tauri` | native 창·sidecar·앱 전체 종료·설치 lifecycle |

Runtime에 어떤 업무 서비스가 필요할 수는 있지만, 그 이유로 Memory 보존 정책이나 World 권한 판단을 다시 구현하지 않습니다. Provider adapter 역시 모델 옵션·transport를 처리하며 사용자 권한이나 유료 호출 동의를 독자적으로 결정하지 않습니다.

반복 작업은 **실행 시점**과 **결과 적용 자격**이 모두 중요합니다. 중복 tick·재시작·늦은 응답에서도 같은 논리적 작업이 여러 번 저장되지 않도록 기존 job identity·idempotency·lease·version 확인을 유지합니다. 앱 전체 종료와 보조 창 닫기를 구분하고, 종료·취소 뒤 도착한 결과가 다시 적용되는지 확인합니다.

기존 Memory 배치·예약·종료 저장에는 호출 상한·동의·재시도·durable 상태 계약이 있습니다. HTTP `BackgroundTasks`나 새 큐로 이름만 바꾸면 이 계약을 대체할 수 없습니다. 자세한 실행 조건은 [Memory batch 계약](../docs/architecture/p8-l-r-memory-batch.md)과 [sidecar lifecycle](../docs/architecture/l3-er5-tauri-sidecar-lifecycle.md)에 둡니다.

## 8. 원본 데이터·검색·AI의 역할

SQLite는 원본과 관리 상태를 저장합니다. FTS5와 LadybugDB는 검색·관계 탐색용 파생 데이터입니다. 검색 결과가 있다는 사실만으로 현재 사용 가능한 근거가 되는 것은 아닙니다. 원본 삭제·숨김·World·관찰 범위를 다시 확인합니다.

예를 들어 기억을 삭제했는데 검색에 계속 나타난다면 Memory 상태 전이, projection 반영, 검색 후 원본 재검증을 함께 봅니다. 화면에서 해당 문자열만 숨기면 다음 검색이나 다른 진입점에서 같은 문제가 생길 수 있습니다. [Canonical recall](../docs/architecture/p8-l-h-canonical-recall.md), [Graph recall](../docs/architecture/p8-l-i-graph-recall.md)

LLM은 허용된 입력의 의미를 해석하고 계획·요약·캐릭터 응답을 만듭니다. 실제 ID·권한·실행 가능한 query·저장 여부·호출 상한은 코드가 결정합니다. LLM이 만든 SQL·Cypher를 직접 실행하지 않고, 검증한 구조화된 계획을 허용된 executor로 수행합니다.

AI 동작 수정에는 parser·provider schema·timeout·retry·비용 동의·물리 호출 수가 함께 영향을 받습니다. SDK 자동 재시도나 숨은 fallback을 더해 예산을 늘리지 않습니다. 모델별 상수와 예산 숫자는 상세 계약에서 관리하고 이 문서에 중복 목록으로 만들지 않습니다.

Streaming에서는 사용자에게 허용된 응답 event만 전달합니다. 내부 planner 출력·reasoning·provider 오류를 노출하지 않고, 실패한 partial 응답을 성공한 원본이나 후속 기억 근거로 저장하지 않습니다. [응답·streaming 계약](../docs/architecture/p8-l-p-evidence-response-streaming.md)

## 9. 설정·로그·의존성·마이그레이션

### 전역 설정과 업무 설정

[app/config.py](app/config.py)는 공통 환경 설정·타입·기본값과 단일 `Settings`/`settings`를 소유합니다. 소비자는 `from app.config import ...`로 이를 사용하고, 도메인 `config.py`는 그 업무의 설정 의미를 담당합니다. 같은 `.env`를 각 서비스에서 새로 읽거나 서로 다른 기본값으로 해석하지 않습니다. 실제 설치 경로·저장된 사용자 설정은 기존 `runtime/configuration.py`와 연결합니다.

기존 `app/core/config.py`는 제거했고 설정 구현을 중복하거나 호환 alias를 남기지 않습니다. `BACKEND_DIR`는 이동 후에도 `backend`를 가리켜 개발 `.env`, 기본 SQLite, media, graph 경로를 보존합니다. 작업 디렉터리가 달라도 `backend/.env`를 읽고, 환경 변수는 dotenv보다 우선하며 명시적 생성 인자는 환경 변수보다 우선합니다. 이 계약과 cold import의 단일 설정 사용은 [설정 경로 검사](tests/config/test_config_paths.py), 기존 시작 보안 계약은 [시작 보안 검사](tests/config/test_startup_security.py)에서 확인합니다. 설치 앱에 개발 `.env`를 필수로 추가하지 않으며, 비밀은 [credential resolver](app/credentials/resolver.py)의 경계를 따릅니다.

### 로그와 배포 파일

[`backend/logging.ini`](logging.ini)는 기존 root `WARNING` 기본값과 Uvicorn `INFO`·format·console stream 설정을 담습니다. [`runtime/logging_config.py`](app/runtime/logging_config.py)가 파일을 읽고, 앱 factory는 자원을 검증하면서 기존 root handler와 명시적 level을 보존합니다. Factory를 반복 호출해도 `fileConfig`·`dictConfig`로 외부 handler·pytest caplog를 닫거나 새 handler를 설치하지 않습니다. Uvicorn CLI와 contributor reloader는 기존 server 시작 지점에서 같은 설정 dictionary를 사용합니다. 기존 Python redaction 처리는 그대로 유지합니다.

Sidecar는 `log_config=None`·`access_log=False`를 유지합니다. 설치 작업의 JSON stdout, content-free fatal stderr, endpoint 파일과 종료 handshake를 일반 server access log로 바꾸지 않습니다. GUI 프로세스에서 stdout/stderr가 없더라도 logging 설정을 읽을 수 있습니다. 기존 앱에 파일 로그·rotation handler가 없었으므로 이 변경에서도 새 파일 저장 정책을 도입하지 않습니다.

소스 실행은 `backend/logging.ini`, PyInstaller OneFile·OneDir 실행은 `sys._MEIPASS/logging.ini`를 읽습니다. Docker `COPY`와 sidecar `--add-data`에 이 자원이 포함되며, 누락 시 다른 작업 디렉터리의 파일로 대체하지 않고 시작을 실패시킵니다. Alembic 자체의 logging section은 `alembic.ini`에 있으며 앱 설정과 역할이 다릅니다. AR-G3의 로컬 검증과 실제 제품 bundle·설치·CI 판정은 [백엔드 전환 결과](../docs/architecture/refactor-backend-results.md)에서 구분합니다.

현재 의존성은 [pyproject.toml](pyproject.toml)과 [uv.lock](uv.lock)이 관리합니다. `requirements/*.txt` 방식을 별도로 채택하기 전에는 수동 관리 원본을 둘로 만들지 않습니다. 개발·CI·sidecar 빌드의 필요한 의존성을 보존하며 구조 변경에 라이브러리 업그레이드를 섞지 않습니다. `.gitignore`는 저장소 루트의 파일을 사용하고, Git 제외와 Docker·installer 배포 제외를 각각 확인합니다.

### ORM 이동과 schema 변경은 다릅니다

ORM의 Python 위치가 바뀌어도 table·column·constraint·index·ID·시간·source provenance는 같아야 합니다. 구조 이동만을 이유로 DB migration을 추가하지 않습니다.

Alembic은 `backend/alembic`에 둡니다. `alembic.ini`의 `script_location = %(here)s/alembic`과 `prepend_sys_path = %(here)s`는 명령을 실행하는 작업 디렉터리와 관계없이 이 경로와 backend 패키지를 찾게 합니다. `env.py`는 앱 모델을 등록한 단일 metadata를 사용하고, Docker도 `alembic/`과 `alembic.ini`를 함께 포함합니다. 역사적 revision의 본문·ID·연결 그래프와 frozen predecessor 자료는 보존합니다. 필요한 과거 import는 호환 경로를 해결한 뒤 전환합니다.

AR-G4에서 88개 revision과 `env.py`·`script.py.mako`의 물리 경로를 옮겼습니다. 전체 revision의 #263 Git blob·연결 그래프·단일 head와 실제 SQLite 메모리 연결의 metadata 등록은 [Alembic 회귀 테스트](tests/migrations/test_alembic_layout.py)로 확인합니다. 이 검증은 PostgreSQL 역사 migration 전체를 SQLite에 실행하지 않습니다. ER0의 87개 역사 목록은 `20260825_0083`을 제외하는 기존 부분집합으로, 전체 revision 수와 다릅니다. AR-G5에서 최종 `app/models.py`·Base 등록 경로를 연결한 뒤 이 검증을 다시 통과해야 G13을 완료할 수 있습니다.

별도로 `app/runtime/migrations`의 embedded SQLite upgrade가 설치 사용자 데이터를 갱신합니다. Alembic 위치 변경이나 ORM 등록만으로 설치 DB 업그레이드가 완성되지 않습니다. PostgreSQL·Neo4j 역사 자료를 현재 runtime의 새 서버 의존성으로 바꾸지 않습니다. 신규 설치·지원 이전 버전 upgrade·재실행·실패 복구를 격리된 synthetic DB에서 확인합니다. [Embedded runtime 계약](../docs/architecture/embedded-runtime-adr.md), [마이그레이션 회귀](tests/test_embedded_data_migration.py)

## 10. 변경 위치와 테스트

테스트도 업무별로 모읍니다. 여러 업무가 사용하는 fixture는 공통 위치, 해당 업무만의 fixture는 그 업무 테스트 가까이에 둡니다. 단순한 파일 이동 테스트보다 사용자가 관찰하는 결과와 실제 변경 경계를 검증하는 테스트가 필요합니다.

| 수정하려는 문제 | 주요 변경 위치 | 확인할 결과 |
| --- | --- | --- |
| 다른 World의 게시물이 조회됨 | `social` service·조회 조건 | 허용 World만 반환, pagination·순서 유지 |
| Memory 삭제가 검색에 반영되지 않음 | `memory` service·repository·검색 재검증 | 삭제 후 직접 조회와 검색 모두 차단 |
| API 필드가 누락됨 | 도메인 schemas·router | 기존 응답·오류·nullable 계약 |
| 같은 예약 작업이 두 번 저장됨 | runtime claim·service의 조건부 적용 | 중복 실행·재시작·늦은 응답에서도 한 번 적용 |
| provider 응답 형식이 변경됨 | integration·provider 변환·도메인 parser | fake 성공/오류·timeout·호출 수 보존 |
| 설치 앱에서만 DB가 비어 보임 | runtime 경로·초기화·패키징 | 기존 데이터 경로 사용·upgrade·재시작 |

### 예: “앱을 재시작하면 기억 정리 결과가 중복된다”

시작점은 `runtime`의 재실행·claim 경로입니다. 다음으로 Memory 서비스의 논리적 job identity와 조건부 저장, repository의 transaction·unique 조건을 봅니다. 이미 처리한 작업, 취소된 작업, 이전 lease의 늦은 응답을 재현하면 문제 위치를 좁힐 수 있습니다. UI에서 중복 행을 가리는 것은 저장 문제를 해결하지 않습니다.

### 현재 사용할 수 있는 검사 명령

환경 구성은 [기여 가이드](../CONTRIBUTING.ko.md)를 따릅니다. 다음 명령은 **저장소 루트**에서 실행하며, 대상 checkout의 lockfile에 맞는 uv 환경을 전제로 합니다. 문서 작성 중 테스트가 통과했다는 보고가 아닙니다.

```powershell
uv run --project backend python scripts/ci/generate_architecture_inventory.py --check
uv run --project backend python scripts/ci/check_architecture_boundaries.py
uv run --directory backend python -m pytest -q tests/test_t2_5_architecture_boundaries.py
```

아래는 현재 경로의 기능 회귀 예시입니다. 수정한 문제의 범위에 맞는 테스트를 선택하고, 전체 회귀가 필요한 단계에서는 마지막 명령을 사용합니다.

```powershell
uv run --directory backend python -m pytest -q tests/test_p8_l_g_memory_write_lifecycle.py
uv run --directory backend python -m pytest -q tests/test_p8_l_h_canonical_recall.py
uv run --directory backend python -m pytest -q tests
```

목표에서는 테스트가 `tests/memory/` 등으로 이동하므로 old→new test node·`conftest.py` 범위·CI 명령도 함께 바뀝니다. 테스트가 덜 수집돼 통과한 것을 성공으로 보지 않습니다. 실제 구성은 [CI workflows](../.github/workflows)를 따릅니다.

Import inventory는 현재 사실을 기록하고 import policy는 허용 경계를 정합니다. Inventory 갱신만으로 새로운 의존을 승인한 것이 아니며, 구조 검사만으로 기능 동작이 검증된 것도 아닙니다. DB·provider·worker·설치 경계가 바뀌면 해당 실행 검증이 필요합니다. 테스트에는 synthetic data와 fake provider를 사용하고 실제 사용자 DB·credential을 fixture로 가져오지 않습니다.

## 11. 현재 코드와 목표의 연결

현재 checkout에는 `application/domain/ports/infrastructure/public.py`와 전역 `services/models/schemas/cruds`가 함께 남아 있습니다. 목표 문서는 이 코드가 이미 이동했다고 가정하지 않습니다. 전환 전의 버그 수정은 실제 호출 경로와 보호 규칙을 따르고, 구조 이전을 함께 수행할 때 해당 범위의 구현·소비자·문서·검사를 맞춥니다.

| 현재 위치 | 목표 책임 |
| --- | --- |
| 도메인 `api/routes.py`, `api/*schemas.py` | 같은 도메인 `router.py`, `schemas.py` |
| 도메인 `application/*` | 같은 도메인 `service.py` 또는 역할별 `service/` |
| 도메인 `domain/*` | schema·순수 policy·오류·필요한 contract로 역할별 분리 |
| 도메인 `infrastructure`의 ORM·SQL | 같은 도메인 `models.py`·필요한 repository |
| `ports`, `public.py` | 실제 교체 경계·지원 타입·호환 alias만 필요한 동안 유지 |
| 전역 `services/cruds/schemas`의 업무 구현 | 해당 업무 도메인 |
| `app/config.py` | AR-G1에서 전역 설정 구현·소비자 이전, `app/core/config.py` 제거 |
| `app/core/db.py` | 목표 전역 `app/models.py`, `app/database.py` |
| 기존 `app/models/`의 업무 ORM | 소유 도메인 모델, 등록은 실행 조립 |

`core`의 나머지 유틸리티와 기존 runtime·provider 코드는 각각의 실제 역할에 따라 유지하거나 옮깁니다. 모든 파일을 여섯 전역 파일에 합치지 않습니다. 사용 중인 구현과 위임만 남은 alias를 구분하고 import·동적 등록·migration·패키징 소비자가 없어진 뒤 옛 파일을 제거합니다.

### `app/models/`와 `app/models.py`는 한 번에 공존시키지 않습니다

현재 [`app/models/__init__.py`](app/models/__init__.py)는 업무 ORM export·등록을 포함하고, [`app/core/db.py`](app/core/db.py)가 Base를 정의합니다. 목표 `app/models.py`는 이 업무 모델 집합의 새 이름이 아니라 공통 기반입니다.

먼저 업무 모델과 `app.models.<하위모듈>` 소비자를 옮기고, 이전 기간에는 하나의 기존 Base와 같은 ORM class identity를 공유합니다. 미전환 하위 import와 필요한 역사적 호환 경로가 해결된 뒤, 패키지→모듈 전환 및 Base·database import 변경을 함께 적용합니다. `models/`와 `models.py`를 동시에 남겨 Python의 선택 순서에 의존하거나 같은 table을 두 class로 등록하지 않습니다.

### 목표 문서와 현재 검사의 관계

현재 [backend domain 계약](../docs/architecture/backend-domains.md)과 [import policy](../security/architecture_import_policy.json)는 이전 구조를 검사할 수 있습니다. 아직 이전하지 않은 범위의 보호는 유지됩니다. 목표 import 예시가 있다는 이유로 기존 검사를 우회하지 않습니다.

전환한 범위는 새 규칙과 허용·거부 사례를 검사에 반영하고, 미전환 범위는 좁게 남깁니다. 전체 규칙을 끄거나 legacy 예외를 무제한 늘리지 않습니다. 과거 migration·테스트의 증거와 현재 경로 inventory는 구분합니다. 파일 위치 변경에 API·데이터·provider 동작 변경을 함께 섞으면 기존 기능 보존 여부를 판단하기 어려워집니다.

## 12. 설계 근거와 상세 문서

[FastAPI Best Practices README](https://github.com/zhanymkanov/fastapi-best-practices/blob/master/README.md#project-structure)와 [AGENTS.md](https://github.com/zhanymkanov/fastapi-best-practices/blob/master/AGENTS.md#project-structure)에서 업무별 패키지와 역할별 파일 구성을 참고했습니다. 원문의 `src`를 `app/domains`와 전역 `app` 파일로 대응시켰고, 설명 방식은 구조·역할·이유·구체적인 변경 예시 순서로 구성했습니다. 원문의 제품 예제·본문·버전별 성능 주장을 그대로 복사한 문서가 아닙니다.

설계 결정의 작업용 배경은 2026-09-05 작성 시점에 참고한 「09-04 Angmoo 구조 리팩터링 — 기능 보존·Bulletproof React·FastAPI 도메인 중심 전환 계획」입니다. 이 계획은 저장소 밖 workspace 문서이며, 기여자가 구조를 이해하는 데 필요한 규칙은 이 문서와 아래 저장소 내 계약에 설명합니다.

- [기여 절차와 개발 환경](../CONTRIBUTING.ko.md), [기여 영역 안내](../docs/public/contribution-map.md)
- [공개 runtime 구조](../docs/public/architecture.md), [embedded runtime 계약](../docs/architecture/embedded-runtime-adr.md)
- [Memory write lifecycle](../docs/architecture/p8-l-g-memory-write-lifecycle.md), [Memory batch](../docs/architecture/p8-l-r-memory-batch.md)
- [World Package 계약](../docs/architecture/l3-5-world-package-v1.md)
- [프론트엔드 아키텍처](../frontend/ARCHITECTURE.md), [디자인 기준](../frontend/DESIGN.md)

안정적인 소유권·호출 방향·공통 파일 책임이 바뀌면 이 문서를 갱신합니다. 개별 모델 옵션·모든 파일 목록·PR 진행률은 상세 계약과 실제 코드에서 관리합니다. 기능 하나의 동작 변경 때문에 전체 아키텍처 설명을 매번 다시 작성할 필요는 없습니다.


### World Package의 계약과 lineage 저장

World Package v1의 Python 입력·출력은 `world_packages/schemas/{http,content,manifest}.py`에 있다. 배포되는 JSON schema는 기존 `schemas/v1/`에 그대로 두므로 `schemas.py` 파일을 동시에 만들지 않는다. 불변 export·preview·seed 기록은 `contracts/`, 오류는 `exceptions.py`, 상태 enum은 `constants.py`, archive·license·collision 판단은 `policies/`가 소유한다. JSON 정규화와 digest bytes는 `utils/canonical.py`에서 정의한다.

네 개 lineage ORM은 `models.py`에서 기존 단일 Base를 공유한다. `service/registry.py`는 같은 seed의 version 재사용, 실제 전달 기록의 충돌, 다음 version 소비를 판단하며 `repository/registry.py`가 동일 Session으로 SQL과 flush를 수행한다. 이 둘은 commit하지 않는다. `service/delivery.py`가 export 준비·전달의 commit/rollback을, `runtime/world_packages`가 여러 업무를 함께 저장하는 import의 commit/rollback을 결정한다. 특히 native download만으로 전달을 확정하지 않으며 Tauri의 저장 완료 acknowledgment까지 기다린다.

Package는 `router.py`의 HTTP 처리, `dependencies.py`의 요청별 Session·app state 연결, 서비스·codec·storage로 나뉜다. 이전 `api/application/domain/infrastructure/ports/public.py` 구현은 제거했다. 네 ORM을 읽는 기존 `app.models` aggregate만 G5의 등록 이전까지 정확한 임시 소비자로 남으며 같은 클래스 객체를 사용한다. 이 배치는 shared media 전체나 Hosted CI·설치 검증의 완료를 뜻하지 않는다.


Package 처리 구현은 `service/export.py`·`staging.py`, `archive/{export,validation,exclusions}.py`, `storage/{staging,exports,export_assets}.py`에서 찾는다. 파일을 읽고 정제하는 codec과 저장 수명 관리는 업무별 하위 package로 구분하며, ZIP 검사를 HTTP나 공용 utils로 복제하지 않는다. 사용 중인 fake/storage/UoW 계약 10개는 `contracts/interfaces.py`로 합쳤다. export-only asset 인터페이스에 있던 세 미구현 import 메서드는 호출자가 없었으며 제거했고, 실제 import media 구현은 별도 계약을 유지한다.

Portable ref/profile 변환은 `service/export_projection.py`, 로컬 export 근거·중복·변조·충돌 판단은 `service/preview.py`가 소유한다. World slug와 Character handle의 충돌 범위는 설치 전체다. SQL 읽기 projection과 World/Character/참여 관계를 함께 생성하는 작업은 `runtime/world_packages/{export_source,preview_probe,seed,seed_uow,import_commit}.py`에서 같은 Session으로 연결한다. Package service가 다른 도메인의 ORM을 직접 조회하거나 runtime을 import하지 않는다.

앱 생성 시 `runtime/world_packages/composition.py`가 구체 constructor를 `WorldPackageRuntimeFactories`로 연결한다. Package dependencies는 전달받은 요청 Session·session factory를 그대로 제공한다. import committer는 기존 초기 복구, 동시 실행 잠금, commit 결과 불명 시 관찰과 media journal 보상 순서를 유지한다. Browser stream의 정상 소진 뒤 전달을 기록하며 취소 시 artifact를 정리한다. Native download는 artifact를 유지하고 명시적인 저장 완료 acknowledgment가 성공적으로 commit된 뒤 정리한다. HTTP router는 권한·입력·상태 코드·응답을 처리하고 이 업무 결정을 중복 구현하지 않는다.

`contracts/__init__.py`는 v1의 순수 공개 타입을 모으며 `contracts/interfaces.py`는 실제 fake·archive·storage·UoW 교체 지점을 정의한다. 런타임 factory 계약은 `contracts/runtime.py`에 있다. 모든 함수에 별도 포트를 생성하지 않으며 같은 역할의 구현을 public 호환 파일로 복제하지 않는다. 아직 전환되지 않은 Worlds/Characters의 지원 계약을 사용하는 runtime 소비자는 해당 B2 source 합류 시 canonical 경로로 연결한다.

### Routines foundation의 현재 역할

AR-B4-A1에서 일일 활동의 입출력은 `domains/routines/schemas.py`, 아홉 ORM은 `models.py`가 소유합니다. 모델은 기존과 같은 Base·table·column·index·FK를 사용합니다. `policies/activity_state.py`는 mood/energy 등의 상태 범위와 delta를 검증하고, `service/scheduling.py`는 이미 지난 tick을 무더기로 재실행하지 않고 가장 최근 due tick과 건너뛴 횟수를 계산합니다. 안정적인 오류는 `exceptions.py`, immutable 결과와 clock 계약은 `contracts/`, 실제 SystemClock/FrozenClock은 `utils/clock.py`에 있습니다.

계획 생성·권한 scope·공동 예약의 실제 서비스는 아래 A2 역할을 사용합니다. A3a의 `service/lifecycle.py`는 autonomous 소유권을 검사하는 claim 회복·기간 종료·비활성 World 중단을 소유합니다. 전역 activity runtime의 같은 이름 함수는 manual 제외·선택적 now·오류/commit 의미가 달라 단순 별칭으로 통합하지 않습니다. 그 claim 실행은 A3 후속, provider/result 실행은 AR-B4-B, resident·lease·worker는 AR-B4-C에서 이어갑니다. 이 부분 전환의 정확한 기존 소비자와 제거 시점은 경계 검사 policy와 보존 지도에 기록합니다.

AR-B4-A2에서는 version/daypart/history 상수를 `constants.py`, 실제 DST boundary·후보 선택·snapshot 규칙을 `policies/planning.py`에 두고, routines ORM만 다루는 공동 예약 query와 materialization을 `service/joint_reservations.py`로 옮겼습니다. `service/plans.py`는 소유권·scope·40개 repertoire 후보·readiness·계획 생성/조회·모드 변경과 commit/rollback을 소유합니다. 과거 선택 이력 조회는 `repository/plans.py`, 응답은 `schemas.py`, HTTP 상태 변환은 `router.py`에 있습니다.

계획 요청에서 다른 업무를 읽는 SQL은 `runtime/routines/plan_references.py`가 기존 Session으로 수행합니다. 앱 생성 시 `runtime/routines/composition.py`가 factory를 등록하고 `dependencies.py`가 요청의 `get_db`와 같은 Session을 전달합니다. `contracts/plans.py`의 `PlanReferences`는 그 실제 협력 경계이며 서비스마다 반복해서 추가하는 계층이 아닙니다. WorldCharacter 모드·version 변경은 WC 소유 함수에 요청하고, 최종 commit은 기존 계획 서비스가 수행합니다. 이 조립에는 새 Session·worker 실행·별도 commit이 없습니다.

기존 `public.py`의 계획·guarded lifecycle 함수는 실제 서비스와 같은 객체를 제공하는 임시 별칭입니다. 단순 전달만 하던 daily-plan/lifecycle usecase·repository 클래스와 외부 ORM 집계 파일은 제거했습니다. Clock/FrozenClock 지원과 `now`·`clock` 동시 입력 거부는 `utils/clock.py`에 유지합니다. 옛 `services/daily_activity_plans.py`와 public 소비자는 A3 후속/B4-C에서 차례대로 정리합니다. 전체 routines 전환 완료를 뜻하지 않습니다.

공동 활동의 실제 참가자·차단·장소·시간대·역할 검증은 `service/joint_activity/eligibility.py`, 두 참여자의 예약과 계획 연결·revision은 `planning.py`, 시작 claim과 게시·종료 상태 전이는 `execution.py`가 소유합니다. `service/joint_activity/__init__.py`는 같은 구현 객체만 모읍니다. 별도 `service/joint_scheduling.py`의 accepted-unscheduled 계약은 참가 허용 상태와 오류가 다르므로 이 활성 참가자 전용 흐름에 합치지 않습니다.

공동 활동 서비스는 `contracts/joint_activity.py`의 `JointReferences`로 관련 업무를 읽고 변경을 요청합니다. `runtime/routines/joint_references.py`는 같은 Session의 차단·장소·게시 수·근거 SQL과 기존 SocialEvent 조립을 연결합니다. Post의 두 ID 대입과 add-only 알림은 Social 소유 함수를 사용합니다. Joint 자체와 참가자·계획·episode 변경은 Routines에 남습니다. 시작 게시의 마지막 flush와 호출자 commit/rollback, claim의 사전 commit, 종료 scan의 기존 commit 조건을 바꾸지 않습니다.

`runtime/routines/lifecycle_references.py`는 같은 Session에서 WorldCharacter·membership을 읽고, 만료 계획과 autonomous WorldCharacter를 연결하던 기존 join을 수행합니다. Lifecycle 서비스가 현재 업무의 상태 전이와 commit을 담당하고, scheduler가 이 조회 협력 객체를 전달합니다. 모든 캐릭터의 기간 종료를 한 번에 원자 처리하도록 변경하지 않습니다. 기존처럼 한 캐릭터의 종료 commit 후 다음 캐릭터를 처리하며, 뒤의 scope가 실패해도 앞서 완료한 commit은 유지됩니다. 조회 협력 객체는 별도 Session이나 commit을 만들지 않습니다.

실행기가 기존 admission을 확인한 뒤 사용하는 beat/소비 기록 처리는 `service/execution/claims.py`가 소유합니다. claim·재시도·실패·성공 저장의 실제 SQL과 규칙이 이곳에 있으며, `execution/lifecycle.py`는 그 실행 경로의 기존 회복·종료·중단 계약을 유지합니다. 위의 guarded lifecycle과 검사 조건이 다르므로 호출 경로에 맞는 함수를 사용합니다. `execution/__init__.py`는 같은 함수 객체를 공개하는 package 입구이며 별도 유스케이스나 실행 전달 계층이 아닙니다.

게시 결과를 확인할 때의 Post·WorldCharacter와 중단 시 membership 조회는 `runtime/routines/activity_references.py`가 같은 Session으로 수행합니다. `contracts/activity.py`는 그 실제 조회 계약입니다. 먼저 episode, 다음 beat를 잠그던 순서와 claim commit은 유지하며, 성공 처리의 `commit=False`는 flush만 수행합니다. 호출자가 게시물과 beat/episode의 성공 상태를 함께 commit하거나 rollback합니다. 소비 namespace는 `contracts/lifecycle.py`의 공통 계약을 사용합니다. 의미가 같음을 확인한 UTC/due 계산과 open-claim 종료 helper만 공유하고, 서로 다른 admission 규칙을 삭제하지 않습니다.

승인된 공동 활동의 기존 exact/window 예약과 대표 게시 claim은 `service/joint_scheduling.py`에 있습니다. stable scheduling 오류는 `exceptions.py`, 고유한 허용 daypart와 예약 불가 상태 값은 `constants.py`에 있습니다. 이 계약은 active membership 안의 pending/inactive/active 캐릭터를 허용하며, 이미 active인 계획 항목에는 새 예약을 넣지 않습니다. 기존 proposal opening 실행기는 active 캐릭터만 허용하는 별도 계약이므로 이름이 비슷하다는 이유로 이 서비스와 합치지 않습니다. 참여자 조회도 `ActivityReferences`를 통해 caller Session을 공유하고, 양쪽 계획·revision·대표 claim의 commit/rollback은 이 서비스가 그대로 소유합니다.
### Character/Creator 전환의 현재 위치

Character 입력과 상태·Creator 모델은 `characters/models.py`, `schemas.py`, `contracts.py`에서 찾는다. 생성·표시 프로필·페르소나·동의의 실제 변경은 `service/mutations.py`가 담당하고, `access.py`·`persona.py`·`promotion.py`가 해당 판단을 공유한다. Caller-owned World seed는 `service/seed.py`의 flush-only 계약을 따르며 일반 생성의 기존 commit을 합치지 않는다.

Creator 이미지 한도는 `service/image_quota.py`, draft 응답·파싱·쿨다운은 `service/creator.py`가 소유한다. 파일과 provider의 외부 작업, 여러 업무의 활동·credential·상세 응답 연결은 현재 `runtime/characters`에서 이어간다. 해당 runtime에는 후속 B2/B3/B4/B8 이전 대상이 남아 있어 전체 전환 완료로 보지 않는다. 새로운 Character 업무 판단을 이 혼합 runtime에 계속 추가하는 구조가 아니다. 기존 혼합 `/agents` router의 업무별 분리 역시 남아 있다.

#### Character 관리 HTTP와 런타임 연결

기본 Character 관리 6개 API는 `domains/characters/router.py` → `service/management.py` → profile/persona mutation으로 연결된다. HTTP dependency는 앱 생성 시 등록한 `CharacterManagementWorkflows`를 가져온다. 이 callback에는 활동 설정·credential·기록·상세 응답 조립이 들어가며 동일 DB Session을 받는다. Character의 소유권과 프로필 변경은 service가 판단하고, HTTP 계층에는 오류의 응답 코드 변환만 둔다.

기존 `/agents` 집계 파일은 아직 활동·LocalBot·이미지 API를 포함하므로 canonical Character APIRoute를 원래 위치에 조립한다. 일반 상세 조립의 최근 활동 20개와 단일 조회 200개 한도, drafts 우선 경로 매칭은 유지한다. `AgentDetailRead`는 Character schemas이며 credential/활동/slot의 읽기 계약은 각각 Identity/Runtime schemas에서 가져온다. 이 DTO 선행 추출이 다른 업무 실행 로직의 이전 완료를 뜻하지 않는다.

#### Creator 초안의 수명주기

초안 생성·조회·수정·페르소나 보강·완료와 만료 정리는 `domains/characters/service/drafts.py`가 담당한다. ORM 변경과 소유권·검증은 그곳에서 읽을 수 있고, 파일이나 LLM 작업은 `CreatorWorkflows`를 통해 runtime이 연결한다. callback은 기존 요청의 Session을 그대로 사용하며 초안 정리의 per-draft commit/rollback 정책을 바꾸지 않는다. get/update draft HTTP도 Character router가 담당한다.

파일 전송·이미지 candidate 생성/승격과 provider-specific 오류 변환은 아직 runtime/API 조립의 실제 책임이다. 기존 생성·보강·완료 HTTP에서 이어지는 임시 runtime entry는 canonical lifecycle을 호출할 뿐 업무 구현을 중복하지 않는다. 이를 특정 파일 이름만으로 다른 도메인에 통째로 옮기지 않으며 B3 media와 B4 activity 전환에서 남은 소비 경계를 정리한다.

#### 현재 Character 기본 구현의 완료 범위

Character/Creator 기본 HTTP 11개와 owner state API 1개가 Character router와 서비스에 연결된다. state URL은 역사적으로 community namespace이므로 같은 파일의 `state_router`를 사용하며, API assembly가 원래 자리에 연결한다. Creator provider 실패는 runtime-neutral 계약과 media validation 계약을 받아 기존 HTTP 상태로 변환한다. 이전 런타임/service 오류 export는 같은 클래스다.

순수 state admission/쓰기/응답은 Character 서비스가 소유한다. 기존 Social tool 소비자에게는 Community 오류 타입을 유지하는 호환 wrapper만 남는다. 활동/World readiness/미디어/Local Bot/복합 삭제와 공개 Social profile/search는 각각 해당 실제 업무의 후속 단계에 속하며, 기본 Character 완료를 이유로 섞어 옮기지 않는다. 자세한 종료 경계와 bridge 소비자는 `docs/architecture/refactor-backend-results.md`의 B2 Character 감사표를 따른다.

WorldCharacter의 소유자 identity는 `service/owner_identity.py`의 실제 조회·생성·수정 서비스가 담당합니다. 설치 소유자 확인은 Identity의 `service/owner_context.py`, 특수 Character seed·프로필 쓰기는 Character의 `service/owner_controlled.py`에 요청합니다. 일반 create/update의 commit/rollback/refresh는 WC 서비스가 유지하고 Package seed는 같은 Session에서 flush만 합니다. 이전 application forwarding 함수와 repository Protocol은 실제 호출 전환 후 제거했습니다.


WorldCharacter의 공개 프로필·Studio·후보 조회와 퇴장 정책은 `service/public_profile.py`, `service/studio.py`, `service/lifecycle.py`에 있습니다. World 권한 확인·프로필 표현·퇴장 버전 및 상태 판단은 이 서비스가 소유합니다. Character/WorldMembership을 함께 읽는 기존 SQL은 `runtime/world_characters/queries.py`가 같은 Session에서 실행하며 `contracts/queries.py` 계약으로 주입됩니다. API와 다른 runtime 소비자는 `runtime/world_characters/composition.py` 또는 공통 HTTP 연결 `app/api/world_character_dependencies.py`에서 조립합니다. 서비스가 runtime을 역으로 import하지 않으며 row 개수·DB 정렬·조회 횟수를 바꾸지 않습니다.

기존 프로필·Studio·소유자 HTTP 7개 경로는 `router/profile.py`에 있습니다. 단순 application forwarding 함수와 repository Protocol은 실제 호출을 옮긴 뒤 제거했으며, 퇴장 runtime guard는 `contracts/lifecycle.py`에 실제 협력 계약으로 남습니다. 선택된 World에서 퇴장할 때 Character의 비활성화도 Character 서비스의 같은 attached 객체 쓰기로 연결하고 commit/rollback은 원래 WC 트랜잭션이 수행합니다.


WorldCharacter의 생성·재시도·승인·거절·입장 정책은 `service/autonomous_setup.py`에 있습니다. Character 조회, nullable World/membership 조회·입장 membership seed·World contract version 쓰기, agent-purpose credential 조회는 각 소유 서비스와 같은 Session으로 협력합니다. `infrastructure/autonomous_setup_models.py`의 외부 ORM 집합은 제거했습니다. Provider budget·쿼터·실패 상태 기록과 commit 경계는 WC 서비스에 유지합니다. Runtime mode의 실제 repair 정책은 `service/runtime_modes.py`, 시작 시 Session factory·SQLite immediate 실행은 `runtime/world_characters/recovery.py`가 소유합니다. Runtime의 capacity query는 원래 WC/Character join을 그대로 유지합니다.


WorldCharacter의 활동 준비 상태는 `service/readiness.py`가 판단합니다. Character 상세 API에 들어가는 `AgentActivityProfileReadinessRead`는 `characters/schemas.py`에서 한 번만 정의하며 WC 준비 상태 서비스와 이전 `app.schemas.agents`가 같은 class를 사용합니다. Character 응답 조립이 WC 서비스를 역으로 import하지 않도록 사용하지 않는 Runtime alias와 WC 응답 파일은 제거했습니다. 준비 상태를 판단할 때 World 접근·profile hash·최신 ready repertoire·daypart별 후보 수의 기존 우선순위는 유지합니다.

입장·퇴장 HTTP 4개와 설정 HTTP 6개는 WC router가 소유합니다. 피드 상태 HTTP는 현재 feed 소유 경로에 남고, 두 앱의 route 조립은 기존 feed→setup 순서를 유지합니다. World 접근 오류의 HTTP 변환은 공통 `app/api/world_errors.py`가 소유하므로 한 도메인의 router가 다른 router를 호출하지 않습니다. Scheduler/AgentRun/Slot과 setup의 퇴장 busy 조회는 runtime guard를 공통 HTTP 연결에서 주입합니다.

여러 업무의 Character 데이터 삭제는 `runtime/world_characters/cleanup.py`가 원래 트랜잭션 안에서 조립합니다. Joint activity 참여자 ID를 먼저 읽는 순서와 원래 SQL delete/update 범위를 보존하며 새 commit을 추가하지 않습니다. 단순 옛 `app/services/worlds.py`, `world_character_setup.py`, `activity_profile_readiness.py`는 실제 소비자를 전환한 뒤 제거했습니다. `set_activity_runtime_mode`는 Routine의 기존 검증을 통과한 같은 WC 객체에 mode/version만 기록하고, 권한·readiness 검사와 commit은 호출하던 Routine 작업이 유지합니다.
### World Package의 계약과 lineage 저장

World Package v1의 Python 입력·출력은 `world_packages/schemas/{http,content,manifest}.py`에 있다. 배포되는 JSON schema는 기존 `schemas/v1/`에 그대로 두므로 `schemas.py` 파일을 동시에 만들지 않는다. 불변 export·preview·seed 기록은 `contracts/`, 오류는 `exceptions.py`, 상태 enum은 `constants.py`, archive·license·collision 판단은 `policies/`가 소유한다. JSON 정규화와 digest bytes는 `utils/canonical.py`에서 정의한다.

네 개 lineage ORM은 `models.py`에서 기존 단일 Base를 공유한다. `service/registry.py`는 같은 seed의 version 재사용, 실제 전달 기록의 충돌, 다음 version 소비를 판단하며 `repository/registry.py`가 동일 Session으로 SQL과 flush를 수행한다. 이 둘은 commit하지 않는다. `service/delivery.py`가 export 준비·전달의 commit/rollback을, `runtime/world_packages`가 여러 업무를 함께 저장하는 import의 commit/rollback을 결정한다. 특히 native download만으로 전달을 확정하지 않으며 Tauri의 저장 완료 acknowledgment까지 기다린다.

Package는 `router.py`의 HTTP 처리, `dependencies.py`의 요청별 Session·app state 연결, 서비스·codec·storage로 나뉜다. 이전 `api/application/domain/infrastructure/ports/public.py` 구현은 제거했다. 네 ORM을 읽는 기존 `app.models` aggregate만 G5의 등록 이전까지 정확한 임시 소비자로 남으며 같은 클래스 객체를 사용한다. 이 배치는 shared media 전체나 Hosted CI·설치 검증의 완료를 뜻하지 않는다.


Package 처리 구현은 `service/export.py`·`staging.py`, `archive/{export,validation,exclusions}.py`, `storage/{staging,exports,export_assets}.py`에서 찾는다. 파일을 읽고 정제하는 codec과 저장 수명 관리는 업무별 하위 package로 구분하며, ZIP 검사를 HTTP나 공용 utils로 복제하지 않는다. 사용 중인 fake/storage/UoW 계약 10개는 `contracts/interfaces.py`로 합쳤다. export-only asset 인터페이스에 있던 세 미구현 import 메서드는 호출자가 없었으며 제거했고, 실제 import media 구현은 별도 계약을 유지한다.

Portable ref/profile 변환은 `service/export_projection.py`, 로컬 export 근거·중복·변조·충돌 판단은 `service/preview.py`가 소유한다. World slug와 Character handle의 충돌 범위는 설치 전체다. SQL 읽기 projection과 World/Character/참여 관계를 함께 생성하는 작업은 `runtime/world_packages/{export_source,preview_probe,seed,seed_uow,import_commit}.py`에서 같은 Session으로 연결한다. Package service가 다른 도메인의 ORM을 직접 조회하거나 runtime을 import하지 않는다.

앱 생성 시 `runtime/world_packages/composition.py`가 구체 constructor를 `WorldPackageRuntimeFactories`로 연결한다. Package dependencies는 전달받은 요청 Session·session factory를 그대로 제공한다. import committer는 기존 초기 복구, 동시 실행 잠금, commit 결과 불명 시 관찰과 media journal 보상 순서를 유지한다. Browser stream의 정상 소진 뒤 전달을 기록하며 취소 시 artifact를 정리한다. Native download는 artifact를 유지하고 명시적인 저장 완료 acknowledgment가 성공적으로 commit된 뒤 정리한다. HTTP router는 권한·입력·상태 코드·응답을 처리하고 이 업무 결정을 중복 구현하지 않는다.

`contracts/__init__.py`는 v1의 순수 공개 타입을 모으며 `contracts/interfaces.py`는 실제 fake·archive·storage·UoW 교체 지점을 정의한다. 런타임 factory 계약은 `contracts/runtime.py`에 있다. 모든 함수에 별도 포트를 생성하지 않으며 같은 역할의 구현을 public 호환 파일로 복제하지 않는다. 아직 전환되지 않은 Worlds/Characters의 지원 계약을 사용하는 runtime 소비자는 해당 B2 source 합류 시 canonical 경로로 연결한다.

### Media의 공유 처리와 업무 소유

`integrations/media/images.py`는 제한된 이미지 해석과 WebP 변환, `files.py`는 관리 경로와 삭제 복구용 quarantine을 담당합니다. 소유자 승인이나 공개 여부, 후보 만료와 quota는 결정하지 않습니다. Character의 profile/draft/candidate/seed 저장은 `characters/service/media_storage.py`, 생성된 Post 파일 저장은 `social/service/media_storage.py`에서 찾습니다. 두 서비스는 해당 업무가 전달한 ID·용도에 맞는 파일을 만들며 기존 호출자가 인증과 DB transaction을 계속 소유합니다.

Character 업로드의 원본 크기 한도와 Post의 인코딩 결과 크기 한도는 서로 다른 기존 계약입니다. 공통 decoder를 쓴다는 이유로 이 정책을 하나로 합치지 않습니다. World Package의 lossless 재인코딩·digest/journal도 별도 계약입니다. `core/public_media.py`의 공개 mount 목록에 draft나 candidate 디렉터리를 추가하지 않습니다.

이 설명의 현재 적용 범위는 AR-B3-M1입니다. `services/profile_media.py`는 같은 객체의 임시 export와 역사 World helper만 남기며, 미전환 Character HTTP/candidate 업무와 Social job은 각 B3/B5 단계에서 소비자를 옮깁니다. quota·job·publication을 포괄하는 전역 media service는 만들지 않습니다.


### 이미지 provider 통신

`integrations/image_provider.py`가 모델별 실제 클라이언트를 선택하고, `pollinations_image.py`와 `replicate_image.py`는 provider 요청·응답·대기·실패 변환을 처리합니다. `integrations/provider_http.py`는 공개 HTTPS URL·리다이렉트·민감 헤더 제거와 제한된 오류 진단을 공유합니다. 외부 호출 횟수나 후보 quota를 결정하는 업무는 이 통신 모듈로 옮기지 않습니다.

AR-B3-M2에서 이 네 파일의 실제 구현과 모든 Python 소비자를 이전하고 옛 `services` 파일은 제거했습니다. 기존 운영 필터와 연결되는 Pollinations logger 이름은 유지합니다. Replicate 전용 검증은 `tests/media`에 있고, Post quota와 provider 실패가 연결되는 혼합 검증은 기존 Social 검증 위치에 남습니다.


### Character media 후보와 비공개 조회

`characters/service/media.py`는 소유자/후보 scope·만료·업로드·적용·폐기·비공개 파일 조회를 소유합니다. Draft 조회는 기존 Creator lifecycle의 정리 규칙을 사용하며 같은 `CreatorWorkflows`를 전달합니다. Profile 적용과 upload는 `CharacterMediaWorkflows`로 이미지 설정 무효화·활동 기록·상세 응답 조립을 같은 Session에서 실행합니다.

두 동작의 원래 저장 순서는 다릅니다. Upload는 Character 변경을 먼저 commit한 뒤 활동을 기록합니다. 후보 적용은 quota 확정과 후보 DB 삭제·활동 기록을 함께 commit한 뒤 후보 파일을 삭제합니다. 구조를 단순하게 보이게 만들기 위해 이 transaction 차이를 없애지 않습니다. 두 앱 factory는 callback factory를 `app.state`에 등록하고 HTTP dependency가 이를 제공합니다.

현재 11개 미디어 조회/업로드/적용/삭제 HTTP는 Character router에서 실제 구현하며 기존 혼합 router의 원래 위치에 같은 route 객체로 연결됩니다. 비공개 응답은 `private, no-store`와 `nosniff`를 유지합니다. 이미지 생성 두 endpoint와 provider·settings 조립은 뒤이은 media source 범위이고, 남은 runtime forwarding의 실제 소비자는 보존 지도와 tests에서 추적하여 후속 종료 단계에서 제거합니다.


### Character 이미지 생성

`characters/service/image_generation.py`는 생성 허용 판단, 일별 quota 예약, prompt/seed/size 정책, 후보 기록과 실패 예약의 상태 전이를 담당합니다. 실제 이미지 요청은 `integrations/image_provider.py`를 사용합니다. `CharacterImageGenerationWorkflows`는 여러 업무가 함께 소유하는 설정 조회·서비스 키 해석·번역 기능만 연결하며 기존 호출 시점에 같은 Session을 전달합니다.

서비스 키를 사용할 수 없으면 quota 예약 전에 종료합니다. 일별 quota가 소진되면 번역과 이미지 provider를 부르지 않습니다. Provider 오류 또는 파일 정제 실패는 기존 오류 분류를 사용해 예약을 failed로 확정하고 commit합니다. Draft의 생성 cooldown/초기 commit·마지막 commit과 Profile 생성의 응답 순서는 서로 다른 기존 흐름을 유지합니다.

이 적용으로 미디어 생성 두 HTTP도 Character router를 사용합니다. 기존 runtime에는 LLM credential/외부 번역·이전 URL-helper와 실제 잔여 호출자가 있는 forwarding이 남으며, 무기한 도메인 비즈니스 구현으로 취급하지 않습니다. 후속 shared transport/World 정리와 B4/B8의 설정·삭제 소유권 종료는 결과 문서에 별도로 기록합니다.


### Media 소유권

프로필/Draft 후보의 권한·quota·apply/discard는 Character `service/media.py`, `service/image_generation.py`, `service/image_quota.py`가 담당한다. 파일 배치는 Character·World·Social 각 소유 코드가 수행하고, 공통 이미지 정제·경로 검증·quarantine은 `integrations/media`를 사용한다. 공통 처리에서 공개 여부나 다른 업무의 quota를 결정하지 않는다. World 배너 오류와 commit 실패 보상은 World에 남는다. Post job/게시 부착과 World Package lossless codec은 각각 자신의 업무 계약을 유지한다.

실제 이미지 provider/검증된 HTTP/Azure 번역은 `integrations`에 있다. Runtime은 설정/credential·Character 후처리 callback을 제공하며 provider 호출 횟수와 기존 transaction 순서를 유지한다. 과거 media export와 생산에서 호출하지 않는 URL helper는 이전 테스트의 한시적 호환 경로로 결과 문서에 소유·종료 단계를 기록하고 새 기능의 시작점으로 사용하지 않는다.


### RoutinePost의 입력 형식과 이벤트 문맥

`routine_posts/schemas.py`는 장면 계획·게시 초안·상태 효과의 Pydantic 형식을 소유합니다. `contracts/interaction.py`는 서버가 관찰한 성공 사건 후보의 값입니다. World·consumer·시간 범위와 기존 소비 여부를 확인하고, 관련도 순서와 글자 수·JSON byte 한도를 적용하는 실제 정책은 `service/event_context.py`에 있습니다. 제한 값은 `constants.py`, 문맥 사용 불가 오류는 `exceptions.py`, 텍스트 표현은 `utils/text.py`에서 찾습니다. 공통 텍스트 정제의 실제 구현은 `core/context_text.py`를 사용합니다.

이벤트를 프롬프트에 넣었다는 사실이 성공적인 행동이나 소비 완료를 뜻하지 않습니다. 이 정책은 후보를 제한하며 실제 게시·source 소비·beat 상태의 저장은 기존 RoutinePost transaction이 담당합니다. AR-B4-B1에서 기존 입력과 정책을 먼저 이전했고, 관련 테스트는 `tests/routine_posts/test_runtime.py`로 모았습니다. 문맥의 immutable 값은 `contracts/context.py`, scope·readiness·이전 성공·claim 만료·재시도와 source 소비 판단은 `service/context.py`가 소유합니다. `runtime/routine_posts/context_references.py`는 호출자의 같은 Session으로 기존 nullable 조회와 SQL을 수행하며 새 Session·commit·명시적 flush를 만들지 않습니다. 문맥에 든 World·참여·계획·episode는 기존 attached 객체의 읽기 값이고 다른 도메인 ORM을 문맥 계약에서 import하거나 복제하지 않습니다. 옛 context 구현과 `services/routine_post_context.py` alias는 제거했습니다. 생성 결과와 provider 교체 계약은 `contracts/generation.py`, 서버 근거·응답 schema·상태 검증과 제한된 공개 문맥은 `service/evidence.py`에 있습니다. `service/generation.py`는 계획 생성→검증→게시문 생성의 실제 두 호출 순서를, `client.py`는 목적별 credential 해석과 외부 호출 식별자 변환을 소유합니다. 공유 통신은 `integrations/direct_llm.py`를 사용하며 새로운 forwarding 계층을 만들지 않습니다. 옛 provider/public/서비스 alias는 제거했습니다. 활동 설정·성공 댓글 관찰·실제 게시 transaction과 resident 조립은 B4-C에서 이어집니다.


### 활동 실행 기록과 설정

`routines/models/plans.py`는 일일 계획·episode/beat·공동 활동을, `models/resident.py`는 활동 설정·AgentRun·Slot·공개 행동 실행·FeedCue·활동 로그를 소유합니다. 두 파일은 기존 단일 Base를 사용하고 `models/__init__.py`에서 같은 클래스 객체를 제공합니다. HTTP의 일일 계획 형식은 `schemas/plans.py`, 활동 설정/로그/슬롯과 feed-cue 형식은 `schemas/resident.py`에서 찾습니다. Character 상세 화면은 이 실제 응답 형식을 그대로 사용합니다.

설정의 get/ensure/update는 `service/activity_settings.py`, 활동 로그의 숨김·90초 상태 저장 중복 제거·최신순 조회·저장은 `service/activity_logs.py`가 담당합니다. Settings의 명시적 commit/flush 선택과 log의 `unit_of_work.finish_write`를 유지하므로, 기존 caller가 여러 업무를 한 트랜잭션으로 저장할 때 새 commit을 넣지 않습니다. Social timeline도 같은 Session으로 이 로그 소유 함수를 호출합니다.

AR-B4-C1의 적용은 이 실제 모델/입력/저장 범위입니다. AgentRelationshipPoint는 Relationships, AgentDaypartMemoryEvent는 Memory의 후속 실제 소유로 분리하며 이미지 설정과 섞지 않습니다. Scheduler/lease·실행 그래프·LLM 정책·활동 HTTP와 남은 혼합 CRUD의 순차 이전은 후속 C2+ 작업입니다. 아직 남은 전역 CRUD에는 동일 함수 export를 추적된 임시 소비자로 두며, 새 Routines 서비스는 그 경로를 import하지 않습니다.


일일 계획이 필요로 하는 Character contract hash는 이미 존재하는 `PlanReferences`가 WC 소유 함수를 연결합니다. World/WC 준비 확인 뒤, repertoire 조회 직전의 원래 위치에서 같은 attached Character를 전달합니다. Character 상세 응답이 Routines의 실제 DTO를 사용해도 Routines 업무 코드가 WC 구현을 직접 역참조하지 않아 패키지 순환이 생기지 않습니다.


### 활동 시각과 resident 실행 수명

Routines의 `service/tick_schedule.py`는 active hours·다음 실행·재시도·재개 시각과 deterministic jitter를 계산합니다. World timezone과 Character image quota도 이 같은 시간 값을 사용합니다. `runtime/resident/scheduler.py`는 파일 잠금·DB lease·fencing epoch·heartbeat·취소와 종료 대기를 담당하고 앱의 기존 component worker가 한 번 연결합니다. 별도 scheduler 실행 프로세스를 만들지 않습니다.

그래프 단계가 전달하는 순수 값은 `routines/contracts/resident.py::ResidentGraphState`, 실행 중 같은 Session과 attached 객체를 묶는 context는 `runtime/resident/context.py::LangGraphResidentContext`입니다. Context는 저장소·트랜잭션을 새로 열지 않으며 원래 생성자가 전달한 객체와 callback을 유지합니다. C2는 이 역할만 이전했으며 실제 agent-run 흐름·활동 정책·provider/graph·활동 HTTP와 남은 호환은 후속 C 단계입니다.


### 실행 응답과 활동 허용 값

`routines/schemas/runs.py`는 기존 Run/Slot/Tick 입출력 다섯 형식을 소유합니다. `contracts/activity_policy.py`의 ActivityPolicy는 한 tick에서 허용/차단한 행동과 다음 시각을 담고 기존 prompt 표현을 제공합니다. `service/activity_sessions.py`는 예약 실행과 소유자 수동 실행의 기존 세션 표시를 구별합니다. 실제 허용 판단/횟수 조회/World 활성화 검증은 다음 C3b에서 각각 업무와 runtime 협력으로 이전합니다.

Resident Context는 Character/CharacterState, LlmCredential, AgentFeedCue와 ActivityPolicy의 실제 소유 타입을 그대로 참조합니다. Scheduler도 같은 Routines Tick 응답을 사용하며 별도 DTO나 ORM class를 만들지 않습니다. 이전의 공통 모델/스키마 및 legacy 정책 값 import 세 개는 제거했습니다.


### 활동 허용 판단과 횟수 조회

`routines/service/activity_policy.py`가 실제 활동 시간·허용 행동·일일 제한·cooldown·수동 세션의 예외를 판단하고, `repository/activity_counts.py`가 같은 Session에서 자기 ActivityLog의 횟수와 최근 시각을 조회합니다. `ActivityTimezoneReader`는 설정 확보 뒤 원래 위치에서 현재 World 시간을 읽는 협력입니다. 시간을 먼저 읽거나 새로운 Session을 만들지 않습니다.

기존 설정이 없으면 ensure_setting의 원래 commit/refresh가 유지되고, 이미 있는 설정을 caller가 수정한 경우에는 정책 조회가 새 commit을 만들지 않습니다. World 선택에 따른 시간대와 가져온 World의 활성화 여부는 `routines/service/activity_scope.py`가 판단합니다. `runtime/resident/activity_scope.py`는 동일 Session에서 실제 World/Character/Package 조회만 수행하며, `runtime/resident/activity_policy.py`가 두 역할을 연결합니다. Inspector도 첫 table check에 만들어 활동이 허용된 캐릭터의 조회 이전 반환을 유지합니다. 예전 `services/agent_activity_policy.py`는 직접 소비자 전환 후 제거했습니다.


### 실행 기록과 FeedCue의 저장 시점

`routines/service/runs.py`와 `service/feed_cues.py`는 기존 실행 생성·종료 및 FeedCue 소비의 commit/refresh를 소유합니다. 각 조회 SQL은 `repository/runs.py`, `repository/feed_cues.py`에 있습니다. `service/public_action_executions.py`는 공개 행동의 생성·완료를 기록하고 `repository/public_action_executions.py`는 중복 signature를 조회합니다. 공개 행동의 finish_write는 deferred UoW 안에서 flush/refresh만 수행하므로 호출자의 Social 변경과 함께 rollback할 수 있습니다. 이 차이를 동일한 저장 방식으로 합치지 않습니다.

FeedCue 입력의 identity 계약은 user/character의 id만 읽으며 호출자는 원래 attached 객체를 전달합니다. Slot 배정·lease·복구와 여러 업무를 잇는 실행 그래프는 별도 책임입니다. 저장 함수만 옮겼다는 이유로 실행 전체가 전환됐다고 보지 않습니다.
