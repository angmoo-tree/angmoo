# Angmoo Backend Architecture

Angmoo 백엔드는 **업무별 도메인 안에 HTTP 처리, 업무 흐름, 데이터 모델을 함께 두는 구조**를 사용합니다. 게시물 동작은 `social`, 대화는 `chat`, 기억은 `memory`에서 찾고, 그 안에서 `router.py`, `service.py`, `models.py`처럼 역할을 드러내는 파일을 따라갑니다.

이 문서는 기능을 추가하거나 버그를 수정하는 기여자가 코드의 위치와 연결 방식을 이해하기 위한 설명서입니다. [FastAPI Best Practices](https://github.com/zhanymkanov/fastapi-best-practices#project-structure)의 도메인별 구성을 바탕으로, Angmoo의 로컬 실행·AI 호출·기억·World 경계를 설명합니다.

> **적용 상태 — 2026-09-05:** AR-0 기준선과 AR-1 검사 지원은 PR #259에서 병합됐습니다. `device_home` 첫 backend 파일럿은 PR #260, merge commit `a55c521b9adad624ae1342b2a7b270abc2237f79`로 병합됐고 역할별 파일과 새 경계 검사를 사용합니다. §8.2의 AR-G0 후속 보존·부분 전환 검사를 바탕으로 공통 설정을 `app/config.py`로, identity 실제 구현을 역할 파일로 옮겼습니다. identity의 옛 `public.py`는 미전환 소비자의 동일 객체 호환만 남아 부분 scope로 관리합니다. 다른 업무와 공통 기반의 상태, 검증·PR·병합 결과는 [보존 지도](../docs/architecture/refactor-feature-preservation.md)와 [백엔드 전환 결과](../docs/architecture/refactor-backend-results.md)에 기록합니다.

> **AR-G2 적용 범위:** 공통 오류 4개는 `app/exceptions.py`, Device Home·Social profile이 함께 사용하는 cursor bytes 변환은 `app/pagination.py`가 소유합니다. 기존 core 모듈은 동시성·middleware 구현과 동일 오류 객체의 export를 유지합니다. 다른 업무 오류·cursor payload·query·실행 계약은 기존 소유 모듈에서 계속 관리합니다. 병합 및 통합 검증 상태는 위 실행 결과 문서에서 구분합니다.

> **AR-B2 Worlds 적용 범위:** World 정의·readiness·생성·배너와 10개 HTTP 경로는 `worlds/models.py`, `schemas.py`, `contracts.py`, `exceptions.py`, `storage.py`, `service/`, `router.py`가 소유합니다. WorldCharacter의 입장·퇴장 HTTP는 WC router가 소유하고, 입장에 필요한 World/membership 조회·seed·정의 version 변경은 Worlds service가 같은 Session으로 협력합니다. Worlds 전체를 완료 scope로 올리지 않고 실제 이전된 역할 module만 검사합니다. `worlds.public` 및 frozen SQLite v2→v3가 사용하는 옛 경로 4개는 같은 객체를 제공하는 추적된 호환 경로입니다.

> **AR-B2 WorldCharacter 기반 적용 범위:** 6개 ORM은 `world_characters/models.py`, 입출력은 `schemas/identity.py`·`schemas/setup.py`, 순수 업무 계약은 `contracts/`, 오류는 `exceptions.py`가 소유합니다. 생성기 통신은 `client.py`, 응답 검증은 `service/setup_validation.py`, Package용 seed는 `service/seed.py`에 있습니다. 소유자·입장·승인·Studio·퇴장·runtime mode·readiness의 실제 업무 흐름은 `service/`, HTTP는 `router/profile.py`·`entry.py`·`setup.py`가 소유합니다. 여러 업무 join과 삭제·runtime busy 검사 및 시작 조립은 `runtime/world_characters/`에 있습니다. 미전환 외부 소비자는 정확한 bridge만 허용합니다. immutable SQLite migration이 사용하는 옛 ORM 경로 두 개는 같은 class 객체의 alias로 유지합니다.


> **AR-B5-A Social 기반 적용 범위:** 게시물·반응·미디어 작업은 `social/models/posts.py`, Feed cursor·관찰·block은 `models/feed.py`, owner 수동 작성·inbox 후보는 `models/manual_writes.py`, 성공 행동의 당시 자기 설명은 `models/subjective_context.py`가 실제 ORM을 소유합니다. 수동 쓰기·관찰·프로필·Today·subjective context의 값과 오류는 `contracts/`, 수동 HTTP 요청·응답은 `schemas/manual.py`에 있습니다. 원본 글·반응·프로필 업무 흐름은 아래 B5-B2~B6 적용 범위로 이어지며 agent 도구와 Relationship/projection 전환은 아직 남아 있습니다. immutable SQLite v7→v8와 Alembic 0088의 subjective-context import는 같은 클래스와 schema helper의 호환만 남습니다. 기존 공통 model export도 같은 클래스를 사용하고 G5에서 최종 조립 위치를 정리합니다.

> **AR-B5-B1/B2 Social 읽기 적용 범위:** `repository/{posts,profiles,media,inbox}.py`는 Social 테이블의 실제 SQL을 소유하고, `service/notifications.py`는 수신자·자기 알림 판단을 수행합니다. `service/posts.py`는 게시물·스레드 읽기, `service/visibility.py`는 삭제·신고·인용·조상 게시물 공개 판단, `service/presentation.py`는 응답 조립을 담당합니다. User와 Character 조회는 각 소유 도메인의 service를 같은 Session으로 호출합니다. 멘션 조회의 한 번의 SQL, 입력 순서·삭제/정지 필터와 nullable 조회를 유지하며, 조회 협력은 flush/commit을 추가하지 않습니다. 원본 글·반응은 `service/timeline.py`, 프로필·팔로우는 `service/profiles.py`가 현재 실제 업무 구현을 소유합니다. Feed 목록·following은 `service/feed.py`, Inbox 목록·읽음 판단은 `service/inbox.py`에 있습니다. 기본 검색·Today 순위는 `service/discovery.py`가 담당합니다. 기본 HTTP 31개는 `social/router.py`, 요청 의존성은 `dependencies.py`가 소유합니다. 앱 생성은 `runtime/social/composition.py`에서 네 서비스를 연결하고, 공통 API 조립은 원래 Character 상태 경로 순서를 보존합니다. World Feed 검색·agent 도구는 이어지는 B5에서 이전합니다.

> **Social 저장과 협력:** `service/source_posts.py`는 원본 글·타임라인 글 생성, `repository/reactions.py`는 반응·신고 저장, `repository/profiles.py`는 팔로우 저장을 소유합니다. 이미 검증된 actor의 id/name/display_name을 읽는 협력은 외부 ORM 조회를 대신하는 우회 저장소가 아닙니다. `service/joint_posts.py`의 각 필드 대입과 `notifications.ensure_joint_started_notification`의 query/add는 기존 공동 활동 caller의 Session과 저장 순서를 유지합니다.

> **Social timeline 업무 흐름:** `service/timeline.py::SocialTimelineService`가 원본 글·대꾸·인용·반응·신고·삭제의 실제 권한/흐름/저장 순서를 소유합니다. `runtime/social/timeline.py`는 이미 존재하던 활동 로그·quota·관계 이벤트 처리만 같은 Session으로 연결합니다. WorldCharacter의 현재 World와 멤버십 판단은 `world_characters/service/social_scope.py`에서 수행하며 캐릭터 값을 복사하거나 먼저 읽지 않고 원래 읽기 순서를 보존합니다. 순수 문맥 정제는 `core/context_text.py`, 제한된 topic/게시 결과 표현은 `social/service/activity_results.py`에 있습니다. Identity quota 모델의 역사적 공개 별칭은 G5/B8에서 종료 조건을 검토합니다.

Social의 SQL은 `repository/posts.py`, `profiles.py`, `inbox.py`, `media.py`에서 읽습니다. 다른 업무 ORM을 사용하는 복합 조회는 아직 남은 runtime 전환 범위입니다. `service/notifications.py`는 수신자 없음·자기 자신 알림 제외와 실제 저장 순서를 함께 소유하고, `utils/text.py`·`cursors.py`는 IO 없는 변환만 담당합니다. 기존 SQL helper가 호출하는 `finish_write`는 caller의 지연 commit 구간에서 flush만 하므로, 새 위치를 이유로 commit을 추가하거나 제거하지 않습니다. Community/World Feed의 HTTP DTO는 `schemas/community.py`·`feed.py`에 있습니다. `cruds/community.py` 집합은 제거했으며, 현재 소비자는 실제 소유 서비스·repository를 사용합니다. 이미 별도 branch에서 이전된 Resident·Tree·Lore의 최종 소비자 연결은 부모 통합에서 같은 기능을 이어받습니다.

> **AR-B5-C1 Relationships 기반과 후보 처리:** 관계 event/evidence/state/change/proposal/outbox는 `relationships/models/social.py`, replay는 `models/projection.py`, 관계 응답 후보는 `models/points.py`가 실제 ORM을 소유합니다. 후보 입력 판단·생성·선택/소비/실패는 `service/points.py`, 해당 SQL은 `repository/points.py`, 결정적 식별자는 `utils/points.py`에 있습니다. 후보의 기존 명시적 commit과 중복 충돌 rollback→winner 조회를 유지합니다. Graph 읽기·회상·계획 실행은 `service/graph_read.py`·`graph_recall.py`·`graph_planning.py`, 응답은 `schemas.py`, 값·실행/조회 callback 계약은 `contracts/`가 소유합니다. `policies/`는 strict plan 파싱, 방향·근거·범위의 IO 없는 규칙을 소유합니다. 성공 source의 값은 `contracts/events.py`, 변화량/시간대/snapshot은 `policies/events.py`, 방향별 상태와 상한은 `service/state.py`, outbox 선택·원본 제외는 `service/projection_events.py`·`events.py`가 소유합니다. 이 흐름의 SQL은 `repository/events.py`·`state.py`에 있으며 caller Session의 flush/commit 순서를 보존합니다. 최종 Event 생성·다른 업무 검증·proposal·projection 실행의 나머지 실제 업무 분리는 다음 B5 단계입니다.

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

현재 `public_main.py`는 G06 전환 중의 호환 export만 소유합니다. Local의 명시적 `RuntimeConfig`, 복구, Memory 시작·종료와 각 지원 profile의 계약은 `main.py`의 단일 앱 생성 구현에 통합됐으며, 실제 sidecar·contributor·일반 테스트·CI 계약 검사와 현재 runtime inventory는 main을 참조합니다. 검증 후 호환 파일을 제거하고 그 파일이 없는 후보에서 다시 실행을 확인합니다. 이 목표를 현재 구현 완료로 읽지 않으며, scheduler·DB·Memory의 세부 처리는 소유 runtime과 도메인에 둡니다.

### G06 앱 생성의 현재 구현과 호환 경로

앱과 lifespan의 실제 구현은 `app/main.py`의 `create_app`과 `create_lifespan` 한곳에 있습니다. `create_app(profile="full")`은 기존 기본 `/health` 응답과 구성 요소 기본값을 유지하고, `create_public_app`은 같은 함수에 `profile="public"`을 지정한 adapter입니다. 후자는 Local의 readiness 응답과 명시적 `RuntimeConfig` 연결을 보존합니다. `create_public_lifespan`도 같은 lifecycle 함수에 기존 public의 미구성 component 기본값을 전달합니다. 두 경로가 서로 다른 DB를 가져야 하는 경우 각 명시적 runtime 구성은 계속 별도로 만듭니다.

`public_main.py`에는 별도 factory·오류 class·초기화 본문이 없고, 같은 구현과 public profile을 가리키는 임시 export만 있습니다. 모듈의 앱 객체는 미디어 디렉터리를 만들지 않으며, 명시적인 factory 호출의 `prepare_media_directories=True` 기본값은 유지합니다. 설정 복원, Memory 종료, World Package 복구와 같은 실행 연결은 이 단일 factory가 기존 runtime 소유 구현을 호출합니다.

이 단계는 G06의 첫 실제 통합입니다. 개발 ASGI는 `app.main:public_app`, 공식 sidecar/contributor는 명시적 RuntimeConfig를 주는 `create_public_app`을 사용합니다. 임시 호환 파일과 삭제 전 비교 검사는 유지하며, 새 bundle/installer 검증과 호환 파일 제거는 아직 남아 있습니다. B4/B5/B7의 후속 서비스 callback 및 G5의 단일 Base/database 합류도 별도 통합 검증 대상입니다. `public_main.py`가 없는 최종 후보의 검증 전에는 G06 완료로 보지 않습니다.

## 2. 도메인 안에서 코드 찾기

### Character lore의 기반 소유

업로드한 캐릭터 참고 문서는 `character_lore/models.py`의 source/chunk/parser lease 모델과 JSON 임베딩 타입을 사용합니다. Memory의 사건 기억과 별도 업무입니다. HTTP 입출력은 `schemas.py`, chunk·검색 결과·embedding credential 값은 `contracts.py`, 제한과 오류는 `constants.py`·`exceptions.py`가 실제 정의를 소유합니다.

`service/parser_quota.py`는 실제 parser 수용량 판단과 SQL·lock·lease 저장/해제를 담당합니다. SQLite 프로세스 lock, PostgreSQL advisory transaction lock, 전역/사용자 한도, HMAC subject hash와 commit/rollback 순서가 원래와 같습니다. `parser.py`는 업로드 바이트·확장자·MIME·ZIP 검증, 제한된 자식 프로세스의 PDF/DOCX 추출과 종료를 실제 소유합니다. `policies/chunking.py`는 문장·섹션 경계를 보존하는 청크 분할, `service/presentation.py`는 검색 결과와 임베딩 입력의 텍스트 표현, `utils.py`는 정규화와 해시를 담당합니다.

`service/documents.py`는 소유자 확인, 업로드·교체·재생성·삭제와 검색 실패/fallback 판단을 실제 소유합니다. 조회·집계·재사용 embedding 조회는 `repository.py`, 코사인 거리와 사용 이력·섹션 다양성을 고려한 순위는 `policies/ranking.py`로 구분합니다. 정책은 ORM 대신 읽기 계약을 받아 같은 값을 판단합니다. 문서 transaction의 commit/flush/refresh와 호출자의 같은 Session은 유지합니다.

`LoreWorkflows`는 캐릭터 조회·자격 증명·최근 글 문맥·임베딩/추적 호출만 전달합니다. `runtime/character_lore.py`가 기존 실제 구현과 provider transport를 조립하며 도메인 서비스가 runtime을 import하지 않습니다. `router.py`는 원래 다섯 HTTP 경로·인증·오류를 연결하고, 두 앱 factory가 등록한 의존성을 `dependencies.py`에서 받습니다. 기존 lore service와 HTTP 파일은 제거했습니다. 남은 전역 모델/schema 집합 등록은 G5, 주민 실행 소비자는 B4, runtime의 기존 자격 증명 query와 최근 글 helper 연결은 각각 B8 Identity 및 B5 전환 범위입니다.

### Tree 게시판의 소유

Tree 글·댓글은 `tree/models.py`, 공개 HTTP 형식은 `schemas.py`, 조회/저장은 `repository.py`, 공지·연결 캐릭터 권한 및 응답 조립은 `service.py`에 있습니다. `router.py`는 기존 공개 읽기와 인증 쓰기의 URL·오류를 유지하고 같은 인증/Session dependency를 사용합니다.

작성자 이름 검색의 correlated SQL 조건과 캐릭터 nullable 조회는 `TreeReferences`로 연결합니다. `runtime/tree.py`가 원래 Identity SQL predicate와 Character의 실제 조회 함수를 조립하며 Session을 새로 만들거나 미리 조회하지 않습니다. 업무 순서와 권한은 Tree service에 있고 runtime으로 옮기지 않습니다. create post/comment의 commit→refresh, created_at DESC/id ASC 및 동일 시각 다음 페이지의 id > cursor 규칙은 그대로입니다.

전역 모델·schema 집합은 G5 전환까지 같은 클래스 객체를 노출합니다. 기존 Tree의 services/cruds/model/schema/HTTP 파일은 실제 소비자 전환 후 제거했고 새 구현은 그 경로를 사용하지 않습니다. 다른 B8 업무와 G5·최종 배포 검증의 상태는 별도로 남습니다.


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

### Daypart 활동 기억의 소유

Daypart는 resident가 실제로 제공받은 관찰과 완료한 행동을 시간대별로 기록하는 기억입니다. `memory/models/daypart.py`가 기존 `agent_daypart_memory_events` 테이블을 소유하고, `service/daypart.py`가 저장·보존 기간 정리·history·이전 요약 조회를 담당합니다. 복잡한 조회 조건은 `repository/daypart.py`, 시간대 시작과 요약·prompt 필드 형식은 `policies/daypart.py`에 있습니다. 장기 기억의 candidate/item admission과 서로 다른 기존 기록 형식을 합치지 않습니다.

`service/daypart_observations.py`는 이미 제공한 feed/inbox 입력의 중복 판단, compact note와 제공 기록 저장을 수행합니다. 작성자 이름이 필요하면 실행 소유자가 전달한 `DaypartObservationReferences`를 원래 조회 위치에서 호출합니다. 같은 Session을 사용하며, 첫 inbox 관찰을 commit한 뒤 feed 작성자를 조회하는 순서를 유지합니다. Memory가 Social이나 Character ORM을 직접 import하지 않습니다.

LangGraph 실행·관계 행동 선택·provider 호출은 resident의 책임입니다. 관계 포인트 만료 후 Daypart 요약을 저장하는 조립도 실행 위치에 남습니다. Memory의 각 기존 저장은 원래처럼 개별 commit을 하고, 요약 한 그룹의 commit이 실패하면 rollback 후 다음 그룹을 계속 처리합니다. 이 경계를 임의로 하나의 transaction으로 합치면 실패·재시도 동작이 달라집니다. `contracts/daypart.py`는 실행 객체 전체를 import하는 대신 Memory가 읽는 필드와 Session 타입만 설명합니다.

Daypart의 실행 연결은 `runtime/memory/daypart_observations.py`가 소유합니다. Resident는 기존 프로필 조회 factory를 전달하며, Memory 조립은 실제 Post가 있을 때만 같은 Session으로 이를 생성합니다. `runtime.memory`가 Resident 실행기를 역으로 import하지 않습니다. 실행의 중복 관찰 필터·보존 기간 정리와 Writer의 행동 기억 저장은 실제 Memory 서비스를 직접 사용합니다. 계정·캐릭터 삭제의 다중 업무 UoW는 동일 ORM 객체를 유지합니다. 전체 source 통합·CI·설치 검증은 별도 완료 조건입니다.

업무 동작의 중심은 서비스입니다. HTTP와 예약 작업은 서로 다른 진입점이지만 같은 업무 규칙을 사용합니다.

```text
HTTP 요청 → router → service → DB 접근 / 필요하면 repository
                          └─→ 외부 client

runtime의 예약·작업 실행 → 같은 service
```

Router는 요청을 해석하고 응답으로 바꿉니다. Service는 인증된 actor와 대상 scope를 받아 무엇을 허용하고 어떤 변경을 함께 저장할지 결정합니다. DB 접근이 간단하면 service가 SQLAlchemy session을 직접 사용할 수 있습니다. Repository를 분리했다면 SQL 조회·저장은 repository가 맡고 업무 결정은 service에 남습니다.

### 예: 기억 후보를 만들 때

현재 [Memory write lifecycle](app/domains/memory/service/items.py)은 source의 유효성과 Memory 설정을 확인한 뒤 후보를 저장합니다. scope 검사는 `service/scope.py`, 실제 저장은 `repository/items.py`가 맡습니다.

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

### Memory에서 역할을 찾는 방법

Memory의 HTTP는 `router.py`, 요청과 응답은 `schemas/`, 요청별 실행 연결은 `dependencies.py`에 있습니다. 다음 표는 실제 구현 위치입니다.

| 변경할 동작 | 실제 소유 위치 |
| --- | --- |
| 기억 설정·후보·항목·보존·수정 | `service/scope.py`, `items.py`, `management.py`와 `repository/items.py` |
| 원본의 성공·공개·관찰·차단·digest 판단 | `service/source_evidence.py` |
| 회상 요청·허용 연산·계획 실행 | `service/recall.py`, `retrieval_plan.py` |
| 회상 결과의 현재 원본 재검증·문서 구성 | `repository/recall.py`, `recall_records.py` |
| AI 배치 선택·예약·종료 허가 | `service/batch_selection.py`, `batch_preparation.py`, `batch_scheduling.py` |
| 동의 기간 안의 누락 원본 복구 | `service/reconciliation.py`와 `repository/reconciliation.py` |
| 실제로 제공한 Daypart 관찰·행동·요약 | `service/daypart.py`, `daypart_observations.py` |

SQLite의 원본과 scope가 최종 판단 기준입니다. FTS5와 graph 같은 검색 결과만으로 공개 여부·삭제·사용 가능성을 판단하지 않습니다. `runtime/memory/`의 source/recall queries는 외부 도메인 조회를 같은 Session으로 연결하고, projection은 검색 색인과 파일을 관리합니다. `batch_runtime.py`는 worker 시작·중지·실행을 조립하며 위 Memory 서비스를 호출합니다.

서비스에 전달하는 repository·원본 읽기·외부 예약 정보는 `contracts/`의 실제 협력 타입에 명시합니다. 서비스마다 별도 추상 클래스나 중간 전달 서비스를 추가할 필요는 없습니다. commit·rollback은 기존 업무 흐름의 소유자가 결정하므로, 함수 위치를 옮길 때 조회마다 새 Session을 만들거나 저장 시점을 앞당기지 않습니다.

기여 코드는 `memory.public` 같은 집합 공개 모듈을 경유하지 않고 실제 역할 파일을 import합니다. 이전 `domain/`·`api/` 집합 모듈과 `public.py`는 소비자 전환 후 제거했습니다. `infrastructure/sqlalchemy_models.py`와 `batch_models.py`만 불변 SQLite/Alembic revision이 사용하는 정확한 schema helper 5개를 같은 객체로 제공합니다. 새 제품 코드가 이 역사적 경로에 의존하지 않습니다. 현재 작업의 순차 PR·설치·통합 Gate 상태는 실행 결과 문서에서 별도로 확인합니다.

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

공통 `models.py`에 업무 table을 모두 다시 모으거나 engine를 생성하지 않습니다. [`runtime/persistence/model_registration.py`](app/runtime/persistence/model_registration.py)의 `register_models()`는 각 도메인의 실제 ORM 모듈을 명시적으로 import하고 하나의 `Base.metadata`를 반환합니다. 앱 구성, `alembic/env.py`, 독립적인 `SqliteCanonicalDatabase.open()`이 필요한 시점에 호출하며 반복 호출해도 같은 class·metadata를 사용합니다. 등록 자체는 engine나 앱을 생성하지 않습니다. 공통 Base는 도메인이나 등록 함수를 역으로 import하지 않습니다.

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

현재 [DB 기반](app/database.py)은 동기 SQLAlchemy `Session`·`create_engine`을 사용합니다. 폴더를 바꾸는 작업에 `AsyncSession` 전환을 포함하지 않습니다. 비동기 I/O는 `await`로 호출하고, 동기 DB·파일·SDK 호출이 event loop를 막지 않도록 기존 실행 경계를 확인합니다. `async def` 안에서 보통의 동기 helper를 호출한다고 FastAPI가 자동으로 thread pool에 옮겨 주지는 않습니다. [FastAPI 동시성 설명](https://fastapi.tiangolo.com/async/)

Session은 변경 가능한 transaction 상태입니다. 같은 Session을 동시에 실행되는 thread·task·worker가 공유하지 않습니다. 작업을 다른 실행 문맥으로 옮길 때도 session의 생성·사용·종료와 transaction 범위가 맞아야 합니다. 요청 session을 종료 후 background 작업에 재사용하지 않습니다. [SQLAlchemy Session 동시성](https://docs.sqlalchemy.org/en/20/orm/session_basics.html#is-the-session-thread-safe-is-asyncsession-safe-to-share-in-concurrent-tasks)

## 7. 실행 환경과 외부 서비스

Angmoo는 Docker의 브라우저 실행과 Windows 설치 앱에서 같은 백엔드 업무 코드를 사용합니다. 설치 앱은 Tauri host와 bundled sidecar를 사용합니다. Host Tauri 개발은 기존 wrapper가 Docker backend를 재사용하며 설치용 sidecar를 별도로 띄우지 않습니다. 별도 Next.js 서버를 설치 앱의 새 필수 조건으로 넣지 않습니다. Docker·Host Tauri 개발·설치 앱은 데이터 경로와 lifecycle이 다르므로 한 실행이 다른 실행의 DB나 프로세스를 종료하지 않도록 기존 조립을 유지합니다. [공개 runtime 구조](../docs/public/architecture.md)

| 영역 | 담당하는 일 |
| --- | --- |
| `main.py` | 단일 앱 생성과 지원 profile의 router·오류·startup/shutdown 연결. Local 구현은 통합됐으며 `public_main.py`는 참조 전환·검증 후 제거할 임시 export |
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
| `app/core/db.py` | Base 정의는 `app/models.py`, DB 구현은 `app/database.py`; 역사 migration용 동일 Base alias만 유지 |
| 기존 `app/models/`의 업무 ORM | 소유 도메인 모델, 등록은 실행 조립 |

`core`의 나머지 유틸리티와 기존 runtime·provider 코드는 각각의 실제 역할에 따라 유지하거나 옮깁니다. 모든 파일을 여섯 전역 파일에 합치지 않습니다. 사용 중인 구현과 위임만 남은 alias를 구분하고 import·동적 등록·migration·패키징 소비자가 없어진 뒤 옛 파일을 제거합니다.

### `app/models/`와 `app/models.py`는 한 번에 공존시키지 않습니다

G5 준비 구현은 옛 업무 모델 export 패키지를 제거하고 [`app/models.py`](app/models.py)에 공통 Base만 둡니다. 업무 코드는 실제 소유 도메인의 모델을 사용하고, 여러 도메인 조회는 runtime에서 조립합니다. 기존 테스트에서 함께 쓰는 ORM fixture는 `tests/model_fixture_support.py`에만 있으며 제품 코드는 이를 import하지 않습니다. 현재 branch의 준비 결과와 병합·설치 Gate는 전환 결과 문서에서 구분합니다.

102개 실제 도메인 class는 같은 Base와 metadata에 한 번 등록됩니다. `app/core/db.py`는 내용이 동결된 역사 migration이 사용하는 동일 Base 객체의 import만 유지합니다. 새 코드의 Base는 `app.models`, 연결·Session은 `app.database`에서 가져옵니다. `models/` Python 패키지와 `models.py`를 동시에 남기거나 같은 table을 두 class로 등록하지 않습니다.

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


### Social 프로필과 팔로우

프로필의 팔로우 권한·중복 알림·팔로우 해제, 글/답글/좋아요 수와 목록, 팔로워 응답 구성은 `social/service/profiles.py`에서 찾는다. SQL은 Social의 `repository/profiles.py`가 담당하고 User·Character의 nullable 조회는 각 소유 서비스에 같은 Session을 전달한다. 다른 도메인의 ORM을 가져와 조회를 복제하지 않는다.

프로필 표시와 팔로우 가능 여부는 서로 다른 기존 판단이다. 삭제된 Character의 기존 프로필은 이름과 미디어를 가린 응답을 유지하지만 해당 Character를 새로운 팔로우 대상으로 선택하는 것은 거절한다. 각 서비스의 flush·commit 규칙을 그대로 사용하므로 호출자의 deferred transaction에 참여하며 프로필 구성 과정에서 새로운 commit을 만들지 않는다. `utils/limits.py`는 기존 페이지 크기 제한 계산만 공유한다.

현재 AR-B5-B6에서 이 실제 구현을 이전했다. 남은 HTTP·agent 호출자의 옛 Community import는 정확한 임시 소비자로 추적하며 전체 Social·Relationships 전환 완료로 취급하지 않는다.


### Social Feed와 Inbox 조회

Feed 목록과 following 권한은 `social/service/feed.py`가 소유한다. 현재 공개 상태와 참조 게시물의 판단은 기존 visibility service를 사용하고, 선택·정렬·cursor와 응답 조립 순서를 유지한다.

Inbox의 없는 알림 오류와 응답·읽음 흐름은 `social/service/inbox.py`에서 찾는다. `runtime/social/inbox.py`의 조회는 Character 소유권 subquery와 Notification을 기존 한 번의 SQL로 연결한다. 소유 Character를 먼저 별도 조회해 ID 목록으로 바꾸지 않으므로 쿼리 수와 읽기 시점이 같다. 이 조회는 `UserInboxReads` 계약으로 전달하며 runtime에서 알림 상태를 변경하지 않는다.

읽음 대입·commit·refresh는 Social `service/notifications.py`가 실제로 수행한다. 이 경로는 원래 deferred write 문맥에서도 명시적으로 commit하던 동작을 유지한다. 새 소스 작성의 flush/finish_write 계약과 임의로 같게 바꾸지 않는다. Character Inbox의 명시적 User 또는 Character recipient 범위와 상위 caller의 기존 인증 조건도 유지한다.


### Social 검색과 Today 순위

기본 검색 입력·현재 공개 판단·응답과 Today 활동 점수·동점 정렬은 `social/service/discovery.py`의 실제 정책이다. Character 텍스트 검색은 `characters/service/search.py`가 소유하고, Post와 Character 이름을 함께 찾는 SQL 및 Character와 활동 로그의 집계는 `runtime/social/discovery.py`에서 한 번의 기존 쿼리로 연결한다. 공통 LIKE token/escape는 `core/search_text.py`에 한 번만 정의한다. `%`·`_`·역슬래시를 새 wildcard 문법으로 해석하지 않는다.

Today 인기 root Post의 SQL은 Social repository에 있고 공개 응답·반응 점수는 Feed service가 결정한다. 활동 순위의 KST 자정·포스트/대꾸/좋아요 가중치·이름에 따른 동점 순서를 유지한다. 이 전역 Today 순위는 Chat 근거용의 World 범위 Today SNS snapshot과 서로 다른 기존 기능이므로 합치지 않는다.

현재 AgentActivityLog와 hidden-action 상수는 AR-B4-C 이전 대상이다. 그 두 원래 조회 의존은 runtime의 정확한 임시 소비자로 기록하고 Social 도메인이 옛 model/CRUD를 다시 import하지 않는다. 이 조회는 provider 호출이나 commit을 만들지 않는다.


### 공개 캐릭터 활동 응답

공개 캐릭터 활동의 대상 존재/삭제 판단과 응답 구성은 `social/service/profile_activity.py`가 소유한다. `schemas/activity.py`는 공개되는 Character·state·event 필드를 명시한다. 활동의 원문 reason/result나 Character private 설정, state memory_note를 그대로 직렬화하지 않고 기존 action alias와 고정 요약을 사용한다.

댓글 조회는 Social repository, 활동 로그 조회/기존 visible filter는 `runtime/social/profile_activity.py`의 같은 Session 협력이다. 원래 댓글 20개 조회 → 공개 Character/state 구성 → 활동 로그 80개 조회와 visible/dedupe 20개 적용 순서를 유지한다. 이미 로드한 state의 ORM identity-map 사용이나 필요한 lazy read도 보존한다.

기존 schema aggregate는 같은 class를 내보내는 임시 호환 경로이며 구현이 중복되지 않는다. ActivityLog와 visible filter의 실제 owner 이동은 AR-B4-C가 이 정확한 runtime 소비자까지 연결한다.


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


Operations는 `domains/operations/models.py`의 설정·공지·감사 모델, `service/settings.py`의 DB/환경/기본값 선택, `service/maintenance.py`의 실행 허용·공지 우선순위, `repository.py`의 실제 조회·개인정보 정리를 소유한다. 계정 삭제 조립은 호출자의 같은 Session으로 감사 정보 정리를 요청하고 기존 외부 트랜잭션이 완료를 결정한다. 설정 읽기나 repository가 임의로 commit하지 않는다.


### Character 이미지 설정의 책임

`characters/service/image_settings_owner.py`는 소유자 검증, 공유/개인/비활성 키 모드, 외형 설명의 수동·자동 상태, 기준 이미지 교체·삭제 및 quota 응답을 결정합니다. 실제 저장은 `repository/image_settings.py`, 키 암호화·설정 갱신은 `service/image_settings.py`가 소유합니다. 다섯 이미지 설정 HTTP 경로는 Character router를 사용합니다.

Runtime은 기존 서비스 키 가용성과 Social quota 조회를 같은 Session으로 연결합니다. 공통 텍스트 검증 `core/image_prompt_safety.py`는 외부 통신 없이 Character와 Social에서 같은 정의를 사용합니다. 기준 이미지 저장→기존 파일 삭제→setting 변경→commit/refresh 순서와 사용자가 직접 작성한 외형 설명의 보존 조건은 그대로입니다. 남은 management caller의 짧은 runtime 연결은 해당 업무 이동과 함께 종료합니다.

WorldCharacter의 소유자 identity는 `service/owner_identity.py`의 실제 조회·생성·수정 서비스가 담당합니다. 설치 소유자 확인은 Identity의 `service/owner_context.py`, 특수 Character seed·프로필 쓰기는 Character의 `service/owner_controlled.py`에 요청합니다. 일반 create/update의 commit/rollback/refresh는 WC 서비스가 유지하고 Package seed는 같은 Session에서 flush만 합니다. 이전 application forwarding 함수와 repository Protocol은 실제 호출 전환 후 제거했습니다.


WorldCharacter의 공개 프로필·Studio·후보 조회와 퇴장 정책은 `service/public_profile.py`, `service/studio.py`, `service/lifecycle.py`에 있습니다. World 권한 확인·프로필 표현·퇴장 버전 및 상태 판단은 이 서비스가 소유합니다. Character/WorldMembership을 함께 읽는 기존 SQL은 `runtime/world_characters/queries.py`가 같은 Session에서 실행하며 `contracts/queries.py` 계약으로 주입됩니다. API와 다른 runtime 소비자는 `runtime/world_characters/composition.py` 또는 공통 HTTP 연결 `app/api/world_character_dependencies.py`에서 조립합니다. 서비스가 runtime을 역으로 import하지 않으며 row 개수·DB 정렬·조회 횟수를 바꾸지 않습니다.

기존 프로필·Studio·소유자 HTTP 7개 경로는 `router/profile.py`에 있습니다. 단순 application forwarding 함수와 repository Protocol은 실제 호출을 옮긴 뒤 제거했으며, 퇴장 runtime guard는 `contracts/lifecycle.py`에 실제 협력 계약으로 남습니다. 선택된 World에서 퇴장할 때 Character의 비활성화도 Character 서비스의 같은 attached 객체 쓰기로 연결하고 commit/rollback은 원래 WC 트랜잭션이 수행합니다.


WorldCharacter의 생성·재시도·승인·거절·입장 정책은 `service/autonomous_setup.py`에 있습니다. Character 조회, nullable World/membership 조회·입장 membership seed·World contract version 쓰기, agent-purpose credential 조회는 각 소유 서비스와 같은 Session으로 협력합니다. `infrastructure/autonomous_setup_models.py`의 외부 ORM 집합은 제거했습니다. Provider budget·쿼터·실패 상태 기록과 commit 경계는 WC 서비스에 유지합니다. Runtime mode의 실제 repair 정책은 `service/runtime_modes.py`, 시작 시 Session factory·SQLite immediate 실행은 `runtime/world_characters/recovery.py`가 소유합니다. Runtime의 capacity query는 원래 WC/Character join을 그대로 유지합니다.

#### Chat 모델 정책과 요청 계약

채팅의 HTTP 입출력은 `domains/chat/schemas.py`, 공통 업무 오류는 `exceptions.py`, 모델 선택·reasoning·토큰 및 generation lease 규칙은 `policies.py`에 있습니다. `contracts/model_binding.py`는 thread 모델 연결 방식과 값의 계약을 소유합니다. 소비자는 이 실제 파일을 import하며 옛 `api/schemas.py`와 `domain/` 계약 파일의 재수출 경로는 두지 않습니다.

Thread SQL, generation 시작·재연결·취소·최종 저장과 provider 실행은 아래의 실제 service/repository 및 runtime 협력으로 연결됩니다. B5/B7의 미합류 계약과 B8의 호환 종료는 부분 scope의 정확한 소비자로 기록합니다.


#### Chat 데이터와 thread 조회

Chat의 ORM은 `chat/models.py`, 요청·응답/값·generation fence·retrieval plan·evidence 규칙은 `schemas.py`와 `contracts/`에 있다. `repository/threads.py`는 실제 Chat table 조회와 transaction-scoped advisory lock을 소유하며 commit/rollback을 수행하지 않는다. owner/scope 확인과 상태/오류·commit 순서는 서비스가 유지한다. 다른 업무 ORM을 repository에 가져와 Chat 소유처럼 확장하지 않는다. 실제 실행 service와 교차 업무 조립은 아래 역할을 따르며 옛 runtime 이름은 기록된 호환 소비자만 지원한다.

### Chat 실제 서비스와 교차 업무 조회

Chat 요청은 이제 역할이 있는 실제 서비스로 들어갑니다. `service/threads.py`의 `ThreadService`는 World 참여자 확인, 대화 목록·생성·변경, 기본/개별 모델 선택과 저장 직전 재검증을 담당합니다. `service/settings.py`의 `MessageSettingsService`는 사용자·캐릭터의 쪽지 설정과 credential 선택·오류 판단을 맡습니다. `service/messages.py`의 `MessageService`는 기존 쪽지의 lease, 단일 provider 호출, 답변 저장과 같은 실패 메시지 재시도를 실행합니다. HTTP는 각각의 서비스 인스턴스를 직접 사용합니다.

`repository/threads.py`는 Chat 소유 SQL 조회·advisory lock을, `runtime/chat/scope_queries.py`는 World·WorldCharacter·Character·설치 정체성을 함께 읽어야 하는 기존 join을 소유합니다. `contracts/context.py`는 그 조회 결과와 같은 Session을 사용하는 협력 계약입니다. nullable 결과의 의미와 거부 오류는 Chat 서비스가 결정하며, 조회 협력 코드는 commit·rollback·권한 거부를 수행하지 않습니다. `MessageSettingsService`의 credential 행 저장과 암호화 envelope는 Identity의 `service/message_credentials.py`에 요청하며 flush-only 계약을 유지합니다.

World 대화 생성의 tuple/quota lock, preference 생성의 flush-only 경로, 저장 직전 scope 재검증, 충돌 시 한 번의 재시도는 그대로입니다. 기존 쪽지는 user message commit 뒤 provider를 부르고, 재시도에서는 기존 실패 assistant 행 하나를 수정합니다. 새로운 공통 transaction 규칙으로 이 차이를 합치지 않습니다.

과거 `ChatService → ChatRuntimePort → SqlAlchemyChatRuntime` 전달 체인은 HTTP 호출 경로에서 제거했습니다. 과거 구조 자체를 검증하는 승인 테스트 하나 때문에 이전 forwarder와 Protocol만 `app/compatibility/chat_service.py`·`chat_runtime_contract.py`에 임시 보존합니다. 이들은 신규 기능의 진입점이 아니며 B8에서 원래 node/assertion과 실제 서비스 회귀의 대응을 확인하고 퇴역합니다. `runtime/chat/sqlalchemy_service.py`에는 Memory 선택과 이전 테스트가 쓰는 동일 인스턴스 메서드 alias만 남습니다. 실제 generation/retrieval은 아래 서비스와 runtime 협력이 소유합니다.

### Chat 검색·응답 생성과 저장 책임

검색 경로 선택, canonical/graph/both 계획 실행, 근거 조립과 응답 생성은 `chat/service/`의 역할별 모듈에 있습니다. `contracts/`는 요청·값·불변 Today SNS snapshot과 실제 provider/저장/Memory 협력의 형식을 설명합니다. 모든 서비스에 새로운 전달 계층을 추가하지 않습니다.

`repository/response_lifecycle.py`는 응답 요청의 lease·상태 전이·sequence·최종 답변의 원자적 저장을 담당합니다. `accept`와 `finalize`는 원래 `create_request`와 `finalize_response`의 동일 함수 이름이며 추가 저장 정책이 아닙니다. 실행 경로는 이 저장소를 직접 사용하므로 단순 전달만 하던 `GenerationLifecycleService` 인스턴스를 생성하지 않습니다. 오래된 fence의 거부, 완료 응답 재실행 시 중복 방지, 부분 delta 비저장, 성공 이후 Memory 후보 생성 순서는 유지합니다.

이전 생성 클래스는 기존 공개 계약과 승인 테스트를 보존하기 위해 `compatibility/chat_generation_lifecycle.py` 한 곳에 남습니다. 새 기능의 진입점으로 사용하지 않으며 B8에서 원래 테스트와 실제 저장소 회귀의 대응을 확인한 뒤 제거합니다. 실제 생성 입장 판단은 GenerationService, 여러 업무를 읽는 조립은 아래 runtime 협력이 소유합니다. `runtime/chat/world_generation.py`는 기존 검사 alias이며 전체 B6 통합 검증과 호환 종료는 별도입니다.

### World Chat 요청의 실제 서비스

`service/generation.py`의 `GenerationService`가 접수·같은 요청 재실행·실패 응답 재시도·상태 읽기·기한 만료 복구·시작 전 실패 기록을 구현합니다. HTTP의 접수·재시도·요청 조회 네 동작은 이 실제 인스턴스를 호출합니다. ThreadService의 소유권·잠금·World 재검증과 모델 snapshot을 같은 Session으로 사용하고, 사용자 메시지 flush 이후 요청 생성·commit·refresh 순서를 유지합니다. 요청이 이미 존재하면 원래 내용과 키를 확인해 기존 요청을 반환하며 새 메시지를 만들지 않습니다.

`repository/response_requests.py`는 같은 thread의 진행 중·최신 요청을 원래 조건과 순서로 조회합니다. 조회는 commit하지 않습니다. 기한 만료 복구의 commit, 실패 stream의 accepted/failed 이벤트 sequence와 fence 확인은 GenerationService가 소유합니다. Stream/provider·근거 inspector의 실제 구현은 아래 service와 외부 협력 조립에 있으며, 옛 runtime 이름은 같은 메서드만 연결합니다.

### 근거 inspector의 공개 상태 재확인

`service/evidence.py`의 `EvidenceService`는 저장된 근거 snapshot을 현재 원본과 대조합니다. World·원본 revision·성공 여부·공개 여부·주체의 관찰·참여·차단 상태가 맞아야 과거 본문을 최대 500자로 보여줍니다. Today SNS는 원본과 조상 내용을 포함한 revision을, 저장된 Memory는 활성 상태와 현재 evidence를, 관계 근거는 방향·version·참여자 및 차단 상태를 다시 확인합니다. 삭제·변경된 근거의 옛 본문을 그대로 반환하지 않습니다.

`contracts/evidence_reads.py`는 이 판단에 필요한 같은 Session의 읽기 형식을 명시합니다. `runtime/chat/evidence_reads.py`는 기존 Memory/Today reader를 조립하고 nullable Relationship 조회와 World 범위의 이름 join을 수행합니다. 공개 가능 여부나 오류 정책을 다시 구현하지 않으며 commit을 추가하지 않습니다. HTTP의 근거 조회는 실제 EvidenceService에 연결됩니다.

### Streaming과 provider 실행 조립

`GenerationService.stream_world_response`는 현재 요청의 thread·기한·상태, 사용자 메시지와 응답 Character, 로컬 Memory 실행 가능 여부, credential 오류를 확인합니다. 허용된 요청의 모델 snapshot을 credential에 적용한 뒤 실행 조립에 전달하며 실패 종류·재시도 가능 여부·이벤트와 저장 순서는 이 서비스에 있습니다. Character와 World는 소유 서비스의 nullable 조회를 같은 Session으로 사용합니다.

`contracts/execution.py`는 실제 실행 조립 결과와 입력을 명시합니다. `runtime/chat/generation_workflows.py`는 기존 canonical provider/executor, graph gateway/provider/executor, World 이름 목록, router·응답·UoW·성공 Memory 후보·Today validator를 그 순서로 연결합니다. 조립은 새로운 provider 호출이나 권한 판단을 추가하지 않습니다. 서비스는 이어서 기존 20개/8,000자 recent-context 규칙과 optional Today snapshot 실패 처리를 적용하고 실제 response workflow를 실행합니다. recent-context SQL은 repository, 선택·본문 한도와 요청 구성은 서비스에 있습니다.

`runtime/chat/world_generation.py`는 이제 기존 테스트·계약을 위한 동일 인스턴스 이름만 남았습니다. 새 HTTP 동작은 실제 generation/evidence 서비스에 연결됩니다. A2 구조 확인 테스트가 보는 module attribute는 B8의 명시적 퇴역 대상이며 제품 동작의 호출 체인에 포함되지 않습니다. Canonical preflight/entity resolution·Today snapshot 검증과 Request 기반 HTTP 의존성은 아래 역할로 연결됩니다.


### 검색 사전 검사와 Today snapshot 판단

`service/retrieval_policy.py`는 설치 소유자 → World → thread → 활성 참여자 → 소유자 제어 requester → 차단 → Memory 설정 순서로 canonical scope를 판단합니다. Entity 이름은 SQL 결과에 다시 Unicode casefold를 적용해 같은 이름인지 확인하고, 같은 World의 활성 상태·공개·차단 여부를 결정합니다. `contracts/retrieval_reads.py`로 받는 교차 업무 조회는 같은 Session의 기존 SQL이며, Chat thread 조회는 자신의 repository에 있습니다.

`service/today_sns_activity.py`의 snapshot validator는 응답 생성 중 Today 원본의 complete-through와 snapshot hash가 유지되는지 판단합니다. Runtime의 retrieval/Today factory는 실제 SQL reader와 차단 조회를 조립합니다. 이 factory는 정책이나 commit을 추가하지 않으며, 기존 constructor 이름은 같은 factory의 임시 alias입니다. Memory와 Social의 미합류 경로는 해당 단계의 canonical 계약으로 순차 연결합니다.


### Chat HTTP와 앱 연결

쪽지·설정 HTTP는 `router/messages.py`, World thread/진입은 `router/world_chat.py`, 생성 접수·재시도·상태·근거·NDJSON은 `router/world_chat_response.py`에 있습니다. Router는 자기 schemas와 exceptions를 사용하고 HTTP 오류·응답 형식만 처리합니다. 실제 thread/settings/message/generation/evidence 업무는 `dependencies.py`가 Request의 앱 상태에서 제공하는 typed 서비스로 호출합니다.

두 앱 factory는 `runtime/chat/message_composition.configure_chat_services`로 기존의 같은 인스턴스를 등록합니다. 요청마다 provider나 Session을 다시 만들지 않습니다. DB와 인증 dependency는 원래 동일 함수이므로 기존 override 및 사용자 검증 경계가 유지됩니다. Standalone router 실행도 같은 명시적 구성을 사용합니다. 서비스 미등록 상태에서는 숨은 기본 인스턴스를 생성하지 않습니다.

이전 HTTP 모듈 3개는 A2 구조 검사 한 곳을 위한 동일 함수/router alias로만 남습니다. 실제 API 조립과 동작 테스트는 canonical router를 사용하고, 이 alias는 B8에서 원래 구조 node를 실제 서비스·전송 회귀와 대응해 제거합니다. Generation의 NDJSON 이벤트 필드·UTF-8 직렬화·no-store/nosniff, route 등록 순서와 operation ID는 변경하지 않습니다.

### Runtime 진단과 실행 잠금의 소유권

`domains/runtime/router.py`는 소유자용 `/runtime/status` HTTP와 응답 형식을 담당합니다. InstallationIdentity의 같은 Session 조회와 claimed-owner 판단은 `identity/repository/runtime_access.py` 및 `identity/service/runtime_access.py`에 있습니다. 상태의 privacy-safe 분류와 component overlay는 Runtime `service/status.py`, `service/components.py`에서 읽을 수 있습니다. 다른 업무의 실제 상태 조회와 reader 생성은 `runtime/diagnostics`가 연결하며, 두 앱 생성 profile은 이 reader factory를 한 번 등록합니다.

`RuntimeSchedulerLease` ORM은 Runtime의 `models.py`에 있습니다. 잠금 획득·heartbeat·tick·해제·오래된 실행자 거부 규칙은 `service/scheduler_lease.py`와 `service/sqlite_lease.py`, 실제 SQL과 compare-and-set 조건은 같은 이름의 `repository` 파일이 담당합니다. `runtime/persistence/scheduler_lease.py`는 SQLAlchemy Session factory와 Identity 조회를 연결하고, `sqlite_scheduler_lease.py`는 SQLite engine·읽기 connection·BEGIN IMMEDIATE 재시도·시계를 연결합니다. `scheduler_fence.py`는 실행 context와 단일 before-commit hook의 수명을 담당합니다.

도메인 밖에서 필요한 Runtime 값과 callback 계약은 `contracts/status.py`, `lease.py`, `lease_store.py`, `search.py`, `transaction.py` 등 실제 정의 파일에서 import합니다. 기존 `public.py`와 `api/application/domain/infrastructure/ports` 집합 export는 제거했습니다. 옛 assertion을 보존하는 두 테스트의 local namespace는 동일한 실제 타입과 함수만 묶으며 제품 코드가 사용하지 않습니다. 공통 Base·DB·모델 등록의 G5 통합과 G06 진입점 최종 정리는 이 역할 배치와 구분하여 검증합니다.

관계 이벤트가 활동 실행을 연결할 때 Routines의 `service/public_action_executions.py`는 같은 Session의 nullable 조회와 같은 객체의 `social_event_id` 대입만 소유한다. 이벤트 오류 판정·최종 flush와 commit 책임은 호출 workflow에 남으므로 이 helper는 자체 commit이나 flush를 하지 않는다.


성공한 Social source가 관계 이벤트를 만들 때 `relationships/service/events.py`가 재실행 확인·근거 적격성·변화량·상태·outbox의 순서를 소유한다. 근거 조회는 각 실제 소유자의 조회 함수에 요청하고 runtime의 `event_references.py`가 원래 Session을 연결한다. Actor의 잠금과 WorldCharacter/member 상태 판단은 WorldCharacter 서비스에 남고, evidence의 공개 여부 판단은 Relationships가 원래 시점에 수행한다. 이 흐름은 commit하지 않으므로 게시/실행/event/evidence/outbox는 caller의 하나의 transaction으로 함께 저장하거나 되돌린다.


활동 제안의 한도·발행·수락·거절·역제안은 Relationships `service/proposals.py`를 수정한다. 공동 활동 슬롯과 두 참가자의 예약/계획 변경은 Routines 소유이며 `runtime/activity_proposals`가 같은 Session의 두 서비스를 조립한다. 이 상위 조립은 각 도메인과 기존 event/joint runtime을 단방향으로 참조하며 제안 상태 판단을 복제하지 않는다. 예약 도중 실패해도 caller가 근거 event와 모든 상태를 함께 rollback할 수 있도록 제안 서비스는 자체 commit을 하지 않는다.


Projection outbox의 업무 상태 전이와 재시도 기준은 Relationships가 소유한다. Session 기반 경로의 `service/projection_state.py`는 원래 claim/finalize 순서를 수행하고 commit은 실행 경로가 맡는다. 후보 선택·World별 readiness 집계는 같은 도메인의 repository가 소유하며, 이 조회 결과를 그래프의 권한 판단을 대신하는 근거로 사용하지 않는다.


Canonical SQLite 경로의 `service/sqlite_projection_state.py`는 lease 검증·retry/dead/cancel 판단을, 같은 이름의 repository는 기존 SQL과 CAS를 소유한다. Runtime의 기존 `_write`가 `run_sqlite_immediate`에 같은 connection callback을 전달하여 BEGIN IMMEDIATE·commit·busy retry를 수행한다. 서비스는 engine이나 별도 Session을 만들지 않고, 늦은 worker가 다른 lease의 성공/실패 상태를 덮어쓰지 못하도록 원래 owner·만료·attempt 조건을 그대로 사용한다.


Projection 명령의 버전·서명·payload 형식은 `relationships/policies/projection_commands.py`, 현재 canonical source의 적격성과 삭제/숨김·관계 방향·replay snapshot 판단은 `service/projection_commands.py`가 소유한다. Repository는 원래 nullable 조회와 evidence 순서를 유지한다. WorldCharacter의 `service/projection_scope.py`는 기존 World와 membership 연결만 확인하며 active 작성 권한 검사와 구별한다. Runtime은 같은 Session과 attached 객체를 연결하고 기존 ProjectionCommandError로 오류를 변환한다. 그래프 복구가 새로운 사건을 승인하거나 삭제된 source를 다시 공개하는 경로가 되지 않는다.


Replay의 요청 검증·동시 실행 차단·lease·high-water 고정·완료 감사 기록은 `relationships/service/replay.py`가 소유하며 SQL은 `repository/replay.py`에 있다. 생성은 기존처럼 flush만 하고, start/renew/finalize는 기존 실행 경로의 commit 시점을 유지한다. `runtime/graph_projection/replay.py`는 Session 열기·clock·sidecar clear/apply/digest와 지표 기록을 조립한다. 복구 중 새로 들어온 outbox가 고정된 high-water 범위에 섞이지 않으며, 원래 오류와 재개·실패 상태를 유지한다. World의 전체 식별자는 World 소유 조회로 가져온다.


Owner의 Social-memory 진단 응답은 Relationships `schemas.py`가 소유한다. 이 응답의 Joint 스냅샷은 진단 화면에서 보여 주는 형식이며 Routines의 실행 상태 쓰기를 소유하지 않는다. Event·evidence·방향별 관계·열린 제안·outbox 개수는 Relationships `repository/diagnostics.py`, Joint/participant 조회는 Routines `repository/joint_diagnostics.py`에 있다. 같은 Session에서 원래 join/filter/order와 활동별 참가자 조회를 유지하고 중간 commit을 만들지 않는다.


Social-memory 진단의 소유권·현재 근거 상태·응답 구성은 `relationships/service/diagnostics.py`를 수정한다. WC의 현재 active membership 상태는 `world_characters/service/projection_scope.py`의 별도 진단 판단이며 과거 projection 복구 허용과 합치지 않는다. Runtime의 `diagnostic_references.py`는 Character·WC·Social·Routines의 같은 Session 조회와 graph gateway를 연결한다. 진단/관계 그래프 HTTP 두 개는 Relationships router가 소유하고 기존 URL prefix·tags 조립은 공통 API가 맡는다. 두 앱 factory는 `configure_relationships_runtime`을 한 번 호출하며 요청마다 실제 설정과 같은 DB Session으로 reader를 만든다.


실제 관찰의 원본 적격성·방향별 친숙도·중복 receipt·그래프 outbox는 `relationships/service/observations.py`, 해당 evidence SQL은 `repository/observations.py`가 소유한다. Social의 관찰 입력/결과 계약은 그대로 사용하며 `runtime/relationships/observation_references.py`가 caller의 같은 Session에서 WC active membership과 Social Post/양방향 block 조회를 연결한다. 성공 source 자체를 복제하거나 감정을 추론하지 않으며 기존 flush 위치와 caller rollback/commit 책임을 유지한다. Source 작성 runtime UoW의 나머지 전환은 별도로 이어진다.


수동·검증된 자율 작성의 성공 source와 evidence는 `relationships/service/source_posts.py`가 원래 `audit_only` 상태로 저장한다. 실제 관찰에 의한 관계 receipt와는 다른 책임이다. source 작성의 중복 digest·이미 작성한 결과 확인·공개 root 검사와 ledger/candidate 조회는 각각 `social/utils/source_writes.py`, `service/manual_writes.py`, `repository/manual_writes.py`에 있다. fault injection 위치와 두 번의 원래 flush를 보존하고 caller의 원자적 쓰기 경계 안에서 실행한다.


수동·검증된 자율 작성의 actor/target 허용·중복 결과·게시물·inbox candidate·응답 판단은 `social/service/source_writes.py::SocialSourceWriteService`가 구현한다. 같은 도메인의 Timeline 서비스를 받아 기존 정책을 그대로 사용한다. `runtime/social/sqlalchemy_unit_of_work.py`는 SQLite BEGIN IMMEDIATE·재시도·최종 commit을 소유하고 `source_references.py`에서 Character/Identity/WC/membership 및 성공 사건 쓰기를 같은 Session으로 연결한다. WC nullable actor query는 해당 repository의 실제 조회이며 외부 ORM을 서비스 이름으로 재export하지 않는다. 협력 객체 생성은 조회를 수행하지 않고 actor/target 정책은 원래 잠금 이후 순서로 실행한다.


Social 임시 `_SocialPersistenceModels`/`social_persistence_models` export는 종료했다. Runtime의 프로필·Today·자기 설명·Memory 근거 복합 조회는 Social/Character/WC/World/Routines의 실제 ORM 클래스를 import한다. 이 변경은 query 조립을 runtime에서 도메인으로 우회 수출하는 변경이 아니며 원래 SQL과 cursor·bounded batch·검증 순서는 유지한다. 각 남은 실제 Social 조회 정책/SQL의 소유 분리는 다음 단계에서 이어진다.


수동 World 피드·스레드는 `social/service/manual_feed.py`에서 읽기 권한, 공개 범위, 작성자 profile capability와 응답을 판단한다. `social/repository/manual_feed.py`는 원래 게시물·댓글·좋아요 query를 소유한다. 여러 도메인을 함께 조회하는 active-profile join과 nullable owner 사실은 `runtime/social/manual_feed_references.py`가 같은 Session으로 제공한다. 읽기와 쓰기의 검증 순서·오류가 다르므로 이름이 비슷하다는 이유로 owner 검증 함수를 통합하지 않는다. 읽기는 commit하지 않고 호출자가 가진 변경을 원래 autoflush 시점에 관찰한다.


게시물 이미지의 시각 정체성·scene 프롬프트 규칙은 `social/service/image_prompts.py`, 구조화 출력 검증은 `social/schemas/image_generation.py`, prepared 결과는 `social/contracts/image_generation.py`에 있다. Character 사실은 readonly `ImageCharacter`로 사용한다. 날짜별 사용량·무료 quota 예약/종료 정책은 `social/service/image_quota.py`가 실제 Social media repository를 호출하며 기존 lock→사용량→예약→commit/refresh 순서와 KST 날짜 계산을 유지한다. 오류는 Social exceptions, 실패/건너뜀 결과 작성은 image_attempts가 소유한다.


이미지 작업의 queued→processing claim, stale 실패, 완료·quota 종료 및 Character/Post 존재 확인 순서는 `social/service/image_jobs.py`가 소유한다. `social/repository/image_jobs.py`는 기존 대기 작업 선택과 stale 목록 query만 수행한다. 워커는 Session·설정 시각·루프와 구체 callback을 연결한다. Claim commit/refresh가 완료된 후 같은 Session에서 Character를 조회하고, 삭제된 Character나 Post이면 provider를 호출하지 않고 기존 실패를 저장한다. Provider·attachment는 명시적인 typed callback이며 service가 실행 runtime을 import하지 않는다.


생성 결과 첨부·quota 종료는 `social/service/image_attachment.py`에 있다. 미준비 결과는 그대로 반환하고, 준비된 결과는 기존 크기·품질 값으로 저장한 뒤 PostMedia commit/refresh와 quota 종료 commit을 수행한다. 저장 실패의 quota 실패 처리도 같은 순서다. 모델별 reference 필요·fallback 판단은 `image_reference_policy.py`, provider 진단값을 안정적인 업무 실패 결과로 만드는 정책은 `image_attempts.py`가 소유한다.


이미지 요청 수락과 resident/local 생성 준비의 실제 판단은 `social/service/image_generation.py`가 담당한다. 키 mode·지원 모델·사용량·reference·시각 정체성·생성 실패와 quota 종료 순서를 여기서 읽는다. Character 설정/LLM/운영 설정/비밀 해석/활동 로그는 하나의 `ImageGenerationWorkflows` 협력으로 구체 구현을 연결하며 같은 Session과 tracker 객체를 유지한다. `BotImageRequestRead`는 기존 Social schema의 동일 class이다. 수동 이미지 요청은 job만 기록하고 즉시 LLM/이미지 provider를 호출하지 않는다.


시각 정체성의 수동 값·이미지 hash 캐시, 생성 응답 검증, fallback과 seed→avatar→banner 참조 선택은 `social/service/image_identity.py`가 담당한다. `ImageGenerationWorkflows`는 원시 LLM 응답과 파일 참조 로딩 및 Character의 실제 저장 협력을 제공한다. 정상 검증을 통과한 값만 같은 attached 설정 객체에 저장하며, 캐시 적중·잘못된 응답에 저장을 추가하지 않는다. HTTP DTO와 LLM 출력 schema의 기존 검증 규칙도 유지한다.


이미지 작업의 실제 실행 조립은 `runtime/social/image_generation.py`, 워커의 Session·시각·반복·취소·로그는 `runtime/social/image_job_worker.py`에 있다. 앞의 파일은 Social 서비스에 Character 설정·비밀 해석·LLM·파일 로딩 협력을 연결한다. 프롬프트/참조 정책이나 quota/첨부를 찾아볼 때는 해당 `social/service/image_*.py`를 사용한다. 옛 이미지 services 두 파일 및 사용하지 않는 private wrapper4·단순 정책 재수출을 제거하고 caller와 테스트를 실제 소유 모듈에 연결했다.


World 캐릭터 소셜 프로필의 불투명 커서는 `social/service/profile_cursor.py`가 소유한다. `app/pagination.py`의 공통 bytes 인코딩과 달리 이 파일은 기존 version·AESGCM AAD/nonce·secret 유도 key·payload shape·World/캐릭터/탭 범위를 정한다. 암호화 성공만으로 게시물 공개 판단을 대신하지 않으며 실제 조회는 현재 공개·차단 조건을 적용한다.


World 캐릭터의 게시물·대꾸·좋아요 프로필은 `social/service/world_profile.py`가 입력 검증, 소유 프로필 오류, 차단, 탭/페이지 선택과 응답 조립을 소유한다. 같은 업무 테이블의 count·posts·likes·media SQL은 `repository/world_profile.py`, 여러 업무의 Character·World 멤버십 join은 `runtime/social/profile_references.py`에 있다. `profile_composition.py`가 같은 Session을 연결하며 구성만으로 DB를 읽지 않는다. 전체 reader 인터페이스와 별도 profile application은 실제 서비스에 통합했고 옛 runtime reader 파일을 제거했다.


수동 World 피드·스레드·게시·답글·캐릭터 Social 프로필의 HTTP 5개는 `social/router.py::manual_router`가 소유한다. 공통 API는 원래 위치에서 그 router를 포함한다. `dependencies.py`는 요청의 같은 Session을 사용하여 프로필 서비스, 수동 피드 조회 협력, source 쓰기 실행기를 얻고, `runtime/social/composition.py`가 실제 factory를 연결한다. 구성은 DB·provider IO를 하지 않으며 프런트엔드 요청 검증 뒤에 업무가 실행된다. SQLite 즉시 트랜잭션·재시도·commit은 기존 실행기에 남고 service의 판단을 복제하지 않는다. 트랜잭션 실행 계약은 `contracts/write_execution.py`에 있다.


성공한 행동에서 명시한 동기·감정의 저장은 `social/service/subjective_context.py`가 소유한다. 실행/event/scope/evidence/source 일치, digest·중복 충돌과 검증된 row 저장 순서를 이곳에서 판단한다. `repository/subjective_context.py`는 Social source·기존 declaration을 조회하고 `runtime/social/subjective_references.py`는 같은 Session의 World/WC/Relationship 사실을 제공한다. 상위 행동 트랜잭션은 `subjective_composition.py`를 통해 연결하며 서비스는 원래 flush만 수행한다. 명시하지 않은 감정을 추론하거나 실패한 행동에 활성 declaration을 남기지 않는다.


Today SNS의 활동 종류, 실행 성공 일치, source/chain 변경 감지값, watermark와 UTC 값 변환은 `social/service/today_activity_values.py`가 실제 구현한다. 최대 기록96·scan2048·batch512·분기 깊이8과 기존 공개 범위/event 종류 집합은 Social constants에 둔다. 조회 조립·scope·SQL은 아래 `TodaySocialActivityService`와 같은 Session 조회 협력이 소유한다.


Today SNS의 범위·권한·차단·조상 게시물·성공 근거·명시적 자기 설명 검증과 category/count/coverage/watermark 조립은 `social/service/today_activity.py::TodaySocialActivityService`가 소유한다. `repository/today_activity.py`는 기존 bound/batch 실행과 Social post/block/declaration SQL, `runtime/social/today_activity_queries.py`는 같은 Session의 World/WC/membership/Relationship/Routines 사실을 조회한다. 구체 fact 조회는 Social의 동일 bounded query 실행을 사용해 populate_existing·정렬·상한·batch 순서를 유지한다. `runtime/social/today_activity.py::today_social_activity_reader`는 실제 서비스를 구성만 하고, 옛 SqlAlchemyTodaySocialActivityReader 파일은 제거했다.


성공한 자율 행동을 기록할 때 `social/service/action_sources.py`가 원본 글·반응 확인과 World 연결을, `action_notifications.py`가 생성/입력 알림 연결과 명시적 NO_ACTION 처리 판단을 소유한다. `world_characters/service/action_scope.py`는 원래 활성 WorldCharacter 조회·확인, `relationships/service/action_response.py`는 제안 응답의 허용 판단을 수행한다. 실행 레코드 필드는 `routines/service/public_action_executions.py`가 실제 대입하며 flush/commit을 추가하지 않는다. `runtime/social/{langgraph_actions,world_feed_actions}.py`는 같은 Session에서 소유 서비스를 호출하고 성공 event/evidence·proposal 저장을 원래 순서로 연결한다. 오류 생성자는 이 협력에서 원래 오류 클래스를 전달하여 scope 오류의 class와 reason을 유지하고, 이를 위해 다른 업무를 역참조하지 않는다. 옛 services의 두 social_apply 파일은 제거했다.

### LocalBot 인증과 공개 응답

`local_bot/service/authentication.py`는 토큰 형식과 활성 키, 캐릭터의 삭제·실행 모드, 소유자의 삭제·demo 제한을 순서대로 확인한 뒤 기존 키 사용 기록을 저장합니다. Character와 Identity 조회는 `contracts/authentication.py`에 필요한 nullable 조회로 표현하며 runtime은 실제 소유 서비스를 같은 Session으로 연결합니다. 인증에서 캐릭터나 소유자의 상태를 복제하거나 새 Session을 만들지 않습니다.

`local_bot/service/presentation.py`는 Social 응답을 Bot의 공개 필드로 변환합니다. Bot의 입력·공개 응답 형식은 `local_bot/schemas.py`가 소유하고, Social 이미지 작업 결과인 `BotImageRequestRead`와 공유 글 미디어·댓글은 원래 Social 형식을 사용합니다. 비공개 Character 상태·개인 credential을 공개 projection에 추가하지 않습니다. `policies/rate_limit_clock.py`는 원래의 지역 날짜 경계와 양수 Retry-After 계산을 유지합니다.

Bot의 실제 읽기·행동은 `local_bot/service/actions.py`, 18개 HTTP 경로는 `router/bot.py`에서 찾습니다. `dependencies.py`는 요청의 같은 DB Session, Bot 인증과 app.state에 등록된 협력 구성을 연결합니다. `runtime/local_bot/composition.py`는 Social 업무, 활동 로그, 이미지 요청과 필요한 복합 조회를 구성하며 서비스는 runtime을 직접 import하지 않습니다. 옛 `services/local_bot.py`와 Bot의 옛 HTTP 파일은 제거했습니다. 다른 업무의 최종 소비자 연결과 모델 등록은 B5/G5 통합에서 검증합니다.

LocalBot의 Social 게시물·반응·follow, Routines 활동 이력, Character 상태 읽기는 `runtime/local_bot/queries.py`가 현재 Session에서 연결합니다. 각 조회의 다른 작성자·삭제·시간·개수·정렬 조건과 non-Session fallback을 유지하며 해당 조회에서 commit/flush를 추가하지 않습니다. 할당량·행동 판단은 이 SQL 조립과 구분합니다.

`local_bot/service/rate_limits.py`는 게시·답글·반응·상태·읽기의 실제 제한을 판단하고 사용량 응답과 Retry-After를 만듭니다. `contracts/rate_limits.py`의 필요한 조회·활동기록만 runtime에서 연결합니다. 실제 Session의 quota lock과 원래 synthetic fallback을 구분하며, 읽기 횟수는 원래 자체 commit, 행동은 원래 완료 후 commit·실패 rollback을 유지합니다. rate-limit 로그의 중복 방지 조회와 저장도 같은 Session 및 원래 호출 순서입니다.

공통 HTTP Authorization 문법은 `app/api/authorization.py`에서 해석합니다. Identity와 LocalBot의 권한 정책은 각자의 서비스에 남아 있습니다. 다른 업무의 실제 오류 클래스를 처리할 때는 검사 정책에 정확한 `exceptions` 모듈을 공개 entry로 등록할 수 있습니다. 이것은 하위 모듈·router·models·repository 접근을 허용하지 않으며, 오류 모듈의 DB·프레임워크 의존도 계속 금지합니다.

Bot 쓰기에서 할당량 잠금, 지연 commit 구간, 성공 기록과 실패 rollback의 순서는 업무 계약입니다. 이미지 생성 요청은 원래 게시 성공 후 위치를 유지합니다. 상태 저장은 일일 사용량을 늘리지 않고 마지막 성공 시각으로 재호출 간격을 제한합니다. 반환 DTO는 소유자 id·토큰·private persona를 포함하지 않습니다.


Resident가 Feed·Inbox에서 시도할 수 있는 Social 행동과 차단 이유는 `social/service/resident_affordances.py`에서 판단한다. 원래 좋아요·리포스트 존재와 visible reply 탐색 SQL은 `repository/resident_affordances.py`, agent 문맥용 응답 복사·텍스트 정제는 `service/agent_presentation.py`가 소유한다. 다른 캐릭터 조회는 기존 Character profile service의 같은 nullable 조회를 사용한다. 활성 정책이 이미 정한 allowed_actions를 받아 Social의 self/기존 반응/target/visibility 규칙만 적용하며 Routines의 정책을 중복 구현하지 않는다. Community의 다른 기능은 전환 중이고, 이 23개 함수에 대해서만 동일 함수 import로 협력한다.


활동 계획에 제공할 Feed 이력의 정제·서버 확정 메타데이터 병합·경고·길이/개수 제한과 prompt 문자열은 `routines/service/feed_history_values.py`가 소유한다. 입력 형식 2개는 `routines/schemas/feed_history.py`의 실제 Pydantic class이고, Social의 이전 schema 표면은 전환 중 같은 class를 import한다. 두 업무에서 쓰는 단순 bounded neutral text 변환은 `core/bounded_text.py`에 한 번만 정의한다. Routines 값 정책이 Social service에 역의존하거나 AI 결과가 원본 메타데이터를 바꿀 수 있도록 처리하지 않는다. DB/활동 로그/HTTP 연결의 남은 Community 업무는 별도로 전환한다.

World Feed 검색의 준비 상태, 공개·차단 조건, 순위, 관찰 claim과 다음 키워드 결정은 `social/service/world_feed.py`에 있다. `repository/world_feed.py`는 Social cursor/observation/reaction/block 조회를 맡는다. 다른 업무의 활성 WorldCharacter·membership·World·프로필과 결합 조회는 `runtime/social/world_feed_queries.py`가 호출자의 같은 Session으로 제공한다. `contracts/world_feed.py`의 읽기 계약은 실제 연결된 객체를 그대로 받으며 복사된 ORM이나 다른 Session을 만들지 않는다. `policies/world_feed.py`는 DB 조회 없이 행동 허용 여부와 시간 표시를 계산한다. FTS 후보 조회는 `service/keyword_feed.py`, 프로세스의 실제 검색 인덱스 등록과 단일 lock/state는 `runtime/search/binding.py`가 맡는다. 커서 및 관찰 변경의 commit/rollback은 원래 호출자의 트랜잭션에 남는다.


World Feed의 실행 판단은 `social/service/feed_cycle.py`가 소유한다. 관찰을 LLM 계획 전에 저장하는 순서, NO_ACTION·중복 실행·대상 재검증·재시도와 공개 성공 트랜잭션은 이곳에서 결정한다. 주기 ID/결과 값은 `feed_cycle_values.py`, 단일 Social 행동 선택/반환은 `feed_cycle_publishing.py`, 서버 후보·작성 근거 검증은 `feed_reaction_validation.py`의 실제 정책이다. `runtime/social/feed_cycle.py`는 같은 resident context/Session/attached 결과를 보존하면서 다른 업무와 provider를 연결한다. 구성 객체를 만들 때 SQL·provider·commit을 미리 실행하지 않는다. 원래 max3 LLM 제한과 관찰/공개 성공의 서로 다른 저장 시점을 유지한다.


World Feed의 bounded prompt와 서버 후보/의도/공개 근거 지침은 `social/service/feed_reaction_prompts.py`의 실제 정책이다. `runtime/social/feed_reaction_provider.py`는 기존 credential resolver·Gemini 응답 schema·DirectLlm transport·trace context를 연결한다. prompt를 이동하면서 문자열·후보 목록·중립화/길이 제한·응답 계약을 바꾸지 않으며, 실제 네트워크나 자격 증명 해석을 service의 import/구성 단계에서 실행하지 않는다.


활동 계획에 사용할 소비 이력/최근 관심/자기 주제 이력은 `routines/service/feed_history.py`와 `routines/repository/feed_history.py`가 소유한다. Post/root 이력 SQL·숨김/공개 문맥·현재 컬럼 우선 주제 메타데이터는 `social/repository/topic_history.py`, `social/service/topic_metadata.py`가 담당한다. 실행 조립은 원래 Session의 붙어 있는 객체를 그대로 읽어 제공한다. Routines가 Social ORM이나 저장소를 직접 가져오거나, Post 컬럼이 이미 채워졌는데 활동 로그를 미리 조회하지 않는다. 중립 JSON-object fallback은 `core/json_objects.py`의 동일 함수 하나를 공유한다.


Social Agent Tool의 Run·캐릭터·사용자 범위와 거절 메시지는 `social/service/agent_tool_authorization.py`가 소유한다. Routines의 Run 조회·활동 허용 검사와 Identity 사용자 조회는 `runtime/social/agent_tool_authorization.py`가 원래 Session으로 연결한다. Run auth key 성공을 먼저 반환하고 daypart 세션 거절 뒤에만 기존 fallback을 수행한다. 협력은 객체 복사·선조회·commit을 추가하지 않으며, 지정된 활동 거절 외의 예외는 그대로 전달한다.


실제 Social 도구 게시/답글/반응/팔로우는 `social/service/agent_tool_actions.py`의 `AgentToolActionService`가 소유한다. 원래 권한/자기 글/중복/공개 검증 후 같은 Social timeline을 호출하고, 주제 메타데이터·성공 활동 로그·선택적 feed cue 소비를 원래 순서로 처리한다. `runtime/social/agent_tools.py`는 기존 Session의 타 업무 협력만 연결하며, provider를 호출하거나 새 commit 경계를 만들지 않는다. 기존 호출자는 구성된 `agent_tool_actions`의 원래 이름/인자를 사용한다.


도구의 피드/Inbox/관찰 읽기는 `social/service/agent_tool_reads.py`가 공개·행동 가능 조건, 원래 커서/스캔 상한과 중립 응답을 소유한다. 이미 전달한 알림의 session fingerprint·읽음 처리 판단도 Social에서 수행한다. Routines 활동로그 SQL은 `routines/repository/feed_history.py`가 소유하며 runtime은 같은 Session의 원래 attached 행을 제공한다. malformed 기록을 건너뛰는 경우와 일치한 잘못된 payload에서 종료하는 경우를 바꾸지 않고, 조회를 앞당기거나 별도 commit을 만들지 않는다.


활동 계획용 feed 관심/이력 정제 note의 실제 정책과 로그는 `routines/service/feed_history_notes.py`가 소유한다. 입력/메모 응답 DTO는 `routines/schemas/feed_history.py`에 두며 Social 응답·기존 HTTP도 같은 class를 사용한다. 숨겨진 Post 판단과 도구 권한은 `runtime/social/feed_history_notes.py`의 지연 협력으로 연결하고, 서버 skeleton metadata를 클라이언트 요약이 덮어쓰지 못하게 하는 기존 판단과 로그 privacy를 유지한다.

### 활동 허용 판단과 횟수 조회

`routines/service/activity_policy.py`가 실제 활동 시간·허용 행동·일일 제한·cooldown·수동 세션의 예외를 판단하고, `repository/activity_counts.py`가 같은 Session에서 자기 ActivityLog의 횟수와 최근 시각을 조회합니다. `ActivityTimezoneReader`는 설정 확보 뒤 원래 위치에서 현재 World 시간을 읽는 협력입니다. 시간을 먼저 읽거나 새로운 Session을 만들지 않습니다.

기존 설정이 없으면 ensure_setting의 원래 commit/refresh가 유지되고, 이미 있는 설정을 caller가 수정한 경우에는 정책 조회가 새 commit을 만들지 않습니다. World 선택에 따른 시간대와 가져온 World의 활성화 여부는 `routines/service/activity_scope.py`가 판단합니다. `runtime/resident/activity_scope.py`는 동일 Session에서 실제 World/Character/Package 조회만 수행하며, `runtime/resident/activity_policy.py`가 두 역할을 연결합니다. Inspector도 첫 table check에 만들어 활동이 허용된 캐릭터의 조회 이전 반환을 유지합니다. 예전 `services/agent_activity_policy.py`는 직접 소비자 전환 후 제거했습니다.


### 실행 기록과 FeedCue의 저장 시점

`routines/service/runs.py`와 `service/feed_cues.py`는 기존 실행 생성·종료 및 FeedCue 소비의 commit/refresh를 소유합니다. 각 조회 SQL은 `repository/runs.py`, `repository/feed_cues.py`에 있습니다. `service/public_action_executions.py`는 공개 행동의 생성·완료를 기록하고 `repository/public_action_executions.py`는 중복 signature를 조회합니다. 공개 행동의 finish_write는 deferred UoW 안에서 flush/refresh만 수행하므로 호출자의 Social 변경과 함께 rollback할 수 있습니다. 이 차이를 동일한 저장 방식으로 합치지 않습니다.

FeedCue 입력의 identity 계약은 user/character의 id만 읽으며 호출자는 원래 attached 객체를 전달합니다. Slot 배정·lease·복구와 여러 업무를 잇는 실행 그래프는 별도 책임입니다. 저장 함수만 옮겼다는 이유로 실행 전체가 전환됐다고 보지 않습니다.


### 슬롯 pool·복구·lease의 구분

`routines/service/slot_pool.py`는 빈 슬롯 확보, `slot_recovery.py`는 만료된 실행 복구, `slot_assignments.py`는 임시·상시 배정 반납, `slot_leases.py`는 실행 연결·연장·완료를 소유합니다. `slot_state.py`의 한정된 clear는 같은 attached Slot의 배정 필드만 지웁니다. 조회는 `repository/slots.py`에서 찾습니다. 임시 수동 실행의 종료를 상시 자율활동 배정으로 바꾸거나, 자율활동이 받아들인 배정을 임시 슬롯처럼 지우지 않습니다.

Character row lock과 owner-controlled WorldCharacter 제외를 사용하는 배정/선점 판단도 `slot_assignments.py`와 `slot_claims.py`가 소유합니다. `contracts/slots.py`의 협력은 caller와 같은 Session에서 원래 Character 잠금·조회와 WC correlated predicate만 제공합니다. `runtime/resident/slot_references.py`가 실제 조회를, `runtime/resident/slots.py`가 원래 호출 signature와 조립을 담당합니다. Predicate를 미리 조회한 ID 목록으로 바꾸거나, commit/rollback을 adapter로 옮기지 않습니다. 현재 테스트의 혼합 `agent_crud.get_assigned_slot` 이름은 실제 repository 함수의 동일 객체 export만 사용하며, 기존 assertion을 그대로 보존하는 정확한 임시 소비자입니다. 이를 전체 전환 완료로 간주하지 않으며 B8-A 이전에 정리합니다.


### 실행 실패 후 대기 정책

`routines/service/run_backoff.py`는 사용량 제한·과부하·응답 시간 초과를 구분해 원래 재시도 시각과 표시 메시지를 결정합니다. 최근 실행 이력은 자기 `repository/run_backoff.py`에서 같은 Session으로 읽고, 결과 값은 immutable `contracts/backoff.py`에 둡니다. Provider 요청이나 sleep은 이 정책의 책임이 아닙니다. Character 또는 credential의 최근 실패를 읽는 OR 조건, 시각 범위와 30행 제한을 유지하며, 정책을 조회하기 위해 별도 Session이나 commit을 만들지 않습니다.


### 읽기 전용 실행 단계의 재시도

`runtime/resident/read_only_lanes.py`는 읽기 전용 provider 호출의 한정된 재시도와 대기, 오류 분류·진단 payload를 수행합니다. 실제 공개 행동을 실행하거나 재실행하는 역할은 맡지 않습니다. 취소와 재시도 대상이 아닌 오류는 원래 객체로 전파하고, 진단 정보의 합성 순서와 비밀 가림을 유지합니다. Run/slot/retry의 오류 클래스는 `routines/exceptions.py`가 실제로 소유합니다. 현재 runtime contract의 두 Run 오류 export는 기존 Character 오류 동일성 테스트가 소비하는 같은 객체이며, 복제 클래스가 아닙니다. 이 정확한 임시 계약의 종료는 B8 전환에 포함됩니다.

교차 도메인의 HTTP 오류 처리는 `routines/contracts/execution_errors.py`의 명시적 두 오류 계약을 사용한다. 실제 정의는 `routines/exceptions.py`의 한 객체이며, Character router와 현재 runtime 계약만 이 지원 표면을 통해 사용한다. 기존 service/schema/contract 경계 검사에 예외를 추가하지 않는다.


### 실행 결과의 저장과 진단

`routines/service/run_results.py`는 Run 결과에 남길 필드, 비밀 가림, 단계별 오류와 사용량 집계, snapshot 저장을 소유합니다. 원래의 redaction 뒤 허용 필드 선택과 오류 길이 제한을 유지하며 원본 요청 payload를 변경하지 않습니다. 자기 Run은 `repository/runs.py::get_run`으로 caller Session에서 읽습니다. Snapshot 갱신은 원래의 commit을 수행하고, 쓰기 단계 조회나 없는 Run을 처리할 때 별도 commit을 추가하지 않습니다. Provider 호출이나 Daypart 기억 저장은 이 서비스의 책임이 아닙니다.


### 활동 로그를 통한 실행 근거 확인

`routines/service/activity_evidence.py`는 실제 ActivityLog에서 상태 저장·tick 완료·스레드 조회를 확인하고, 관찰 결과와 공개 행동 근거를 표현합니다. 원래 JSON의 실패 기본값과 조회 전 expire_all 호출을 보존합니다. `repository/activity_evidence.py`는 이벤트 종류·시각 범위·정렬·제한이 다른 아홉 조회를 각각 소유하며 같은 Session을 사용합니다. 관찰 문장에서 공개 행동을 했다고 잘못 주장하면 그 문장을 근거로 사용하지 않습니다. `utils/context_text.py`는 원래의 공백 압축만 담당하며, 의미가 다른 Memory 문맥의 정제 함수를 대신하지 않습니다.


### Resident 프롬프트와 쓰기 지시

Routines 서비스의 `prompt_context.py`는 전달받은 값의 공통 문맥을 표현하고, `perception_prompts.py`·`action_prompts.py`·`state_prompts.py`·`execution_prompts.py`는 각각 읽기·행동 선택·상태 저장·실행 지시를 구성합니다. 이 함수들은 DB나 provider를 호출하지 않습니다. Character와 saved state는 이미 사용하던 속성만 읽는 `contracts/prompt_context.py`의 입력 계약이며, 새 객체를 복제하거나 다른 도메인의 ORM을 조회하지 않습니다. Post와 Comment도 기존 객체의 값만 읽는 입력 계약을 사용하여 Social과 역방향 의존을 만들지 않습니다. 원래 글감 선별과 owner cue/자기 근황 지시의 실제 판단은 `service/action_briefs.py`가 소유합니다. 문구·분기·컨텍스트의 신뢰 경계·시각 읽기 순서는 위치 변경과 함께 바꾸지 않습니다.


### Resident 응답 판단과 실제 호출

`routines/service/decision_results.py`는 받은 JSON의 범위와 fallback을, `execution_results.py`는 성공 상태와 실제 공개 행동의 근거 선택을 소유합니다. `perception_diagnostics.py`는 같은 Session의 원래 ActivityLog 저장을 호출하여 caller의 deferred commit을 존중합니다. `runtime/resident/decision_lanes.py`는 기존 client의 읽기 전용 요청 두 개와 프롬프트·응답 규칙을 연결하며, `gateway_results.py`는 외부 응답의 텍스트와 추적 문맥을 다룹니다. provider 호출 순서·키·건너뜀 조건·오류 전달을 유지하며, 외부 응답을 해석하는 것만으로 공개 행동의 성공을 만들어내지 않습니다.


### Resident 후보·도구·세션 정책

`routines/service/action_candidates.py`는 읽은 후보값을 식별하고 설명하며, `tool_policy.py`는 허용 행동을 실제 도구명으로 연결합니다. `session_keys.py`는 실행/시간대 세션의 식별 및 flag·character allowlist의 원래 조건을 다룹니다. 새 SQL·provider 호출 없이 기존 전달값을 사용합니다. 원래 실행 오류8개는 `routines/exceptions.py`의 실제 클래스이며 기존 HTTP와 runtime에서 같은 객체로 처리됩니다. SDK 요청 형식은 `runtime/resident/request_options.py`에 있습니다.


### Resident가 사용하는 Social 조회

`social/repository/resident_context.py`는 좋아요·리포스트·팔로우 여부와 보이는 스레드 답글의 실제 조회를 소유합니다. 조회는 caller의 Session을 그대로 사용하며 visibility 조건·후속 조회 순서·미커밋 변경의 자동 반영·rollback 의미를 유지합니다. Routines는 이 결과를 활동 후보와 도구 허용 판단에 사용하며 Social ORM의 조회를 별도의 Routines repository에 복제하지 않습니다. 현재 남은 AgentRun 소비자는 C6b의 실행 협력 전환 대상으로 명시합니다.


### Resident 행동 후보의 허용과 표현

`routines/service/action_admission.py`는 자기 글·기존 반응·답글·팔로우 상태에 따라 허용 도구와 차단 이유를 정합니다. `action_menu.py`는 실제 후보 표를, `action_candidates.py`는 읽은 작성자 이름을 표현합니다. `contracts/action_context.py`의 제한된 읽기 협력을 `runtime/resident/context_references.py`가 같은 Session으로 연결합니다. 조건을 판단하기 전 모든 자료를 미리 읽지 않고, 원래 분기에서 필요한 조회만 수행하며 받은 ORM 객체를 복제하지 않습니다. Social SQL과 숨김 판단은 Social 소유 함수를 사용합니다.


Resident 문맥에 쓰이는 알림·최근 게시물·상호 답글 후보의 SQL은 같은 `social/repository/resident_context.py`가 소유합니다. 읽지 않은 알림의30/20개 제한, 최근 자기 글8개·대상 글5개·답글200개와 원래 정렬을 각각 호출 목적에 맞게 유지합니다. Routines 자기 활동 로그의 최근 관계 검토 시각만 `routines/repository/resident_context.py`에서 읽습니다. 스레드 루트 추적은 원래 cycle·없는 부모의 처리만 수행하며, 별도의 공개 여부 검사와 합치지 않습니다.


### Resident의 피드·알림·관계 문맥

`routines/service/feed_context.py`는 읽을 피드와 알림 후보를 선택하고 설명하며, `social_context.py`는 팔로우·상호 답글·관계 검토 후보를 판단합니다. 이 코드에서 다른 도메인의 ORM을 조회하지 않습니다. `contracts/context_reads.py`는 실제로 읽는 값과 조회 협력을 정의하고 `runtime/resident/feed_context_references.py`가 기존 Session에 연결합니다. 원래 Post class 확인은 runtime이 같은 class로 수행하여 정책의 strict assertion을 유지합니다. Feed/행동 가능 알림/결과 문장의 기존 Social workflow는 caller가 명시 전달하며, 같은 코드를 runtime 안에 다시 구현하지 않습니다.


### 슬롯 상태와 실행 준비 확인

`routines/service/slot_status.py`는 슬롯 목록의 공개 응답·소유자 필터와 UTC 실행시각 비교를 담당합니다. AgentRun의 기존 성향 helper는 제품 호출 없이 원래 테스트만 소비하므로 B8-A 검토 대상으로 보존하며, 실제 관리 흐름의 readiness 업무는 C7에서 별도로 이전합니다. `retry_schedule.py`는 수동 실행 시각과 재시도 시각의 우선순위를 정하고, 필요한 경우에만 기존 ActivityTimezoneReader로 World 시간을 읽습니다. 설정이 이미 주어졌을 때의 no-commit과 설정을 처음 만드는 ensure 경로의 원래 commit을 구분합니다. 슬롯 목록 HTTP도 이 실제 서비스와 같은 기존 응답 모델을 사용합니다.


### Resident 실행 권한과 슬롯 인증 연결

`routines/service/run_identity.py`는 캐릭터 삭제·소유자와 자격 증명 소유자·배정·활성 상태를 원래 순서로 판단합니다. `runtime/resident/identity_references.py`는 동일 Session의 소유 도메인 조회를 연결하며, 캐릭터 오류가 나면 자격 증명을 미리 읽지 않습니다. `runtime/resident/credential_profiles.py`는 등록된 인증 어댑터를 통해 검사·키 해석·연결·새로고침을 수행합니다. 이미 일치하면 키를 해석하지 않으며, 실패는 기존 오류 유형과 비밀 정제를 유지합니다. 이 런타임 연결에 SDK나 다른 업무의 권한 판단을 다시 작성하지 않습니다.


### 실행 대상 선택과 상태 조회

`routines/service/post_selection.py`는 명시된 대상 우선, 자기 글 제외 조회, 마지막 공개 루트 글 fallback 순서를 담당합니다. Scoped routine이 연결된 경우에는 전역 피드 대상을 만들지 않습니다. 실제 두 SQL은 Social의 `repository/resident_context.py`에 있고 runtime이 같은 Session을 연결합니다. 캐릭터 상태는 `characters/service/state.py::get_character_state`, 슬롯은 `routines/repository/slots.py::get_agent_slot`, 활동 설정은 기존 `activity_settings.get_setting`에서 읽습니다. 이 nullable 조회는 원래 attached 객체를 반환하며 별도 flush/commit을 추가하지 않습니다.


### 실행 요청의 진입 판단

`routines/service/execution_admission.py`는 사용 가능한 캐릭터, 요청 소유자, 명시 또는 기본 자격 증명을 판단합니다. 명시 자격 증명과 기본 선택은 기존 검증 조건이 다르므로 두 흐름을 그대로 구분합니다. 런타임은 게시물 조회 뒤 소유자를 정하는 원래 순서를 유지합니다. `identity/service/credential_cooldown.py`는 이미 붙어 있는 credential의 대기 시각만 변경하며, 대기 여부와 저장 시점은 해당 실행 흐름이 결정합니다. 설정 변경을 이유로 먼저 commit하거나 자격 증명을 다시 읽지 않습니다.


### Resident 실행과 슬롯 요청

`routines/service/slot_requests.py`는 슬롯 요청의 실제 유지보수 제한, 캐릭터·자격 증명 판단, 활동 설정, 최초 시각과 배정 순서를 소유합니다. 같은 Session의 조회 협력은 `runtime/resident/slots.py`에서 연결하며, 필요한 시점에 평가합니다.

`runtime/resident/execution.py`는 수동 실행, 슬롯별 실행, 전체 tick의 실제 비동기 실행을 조립합니다. provider 호출, lease 수명, 실행 기록 생성 시점과 실패 보상이 이곳에서 연결됩니다. 오류 처리에서 사용하는 `run_created` 같은 상태는 원래 저장 성공 직후에 바뀌어야 하므로 별도 전달 계층으로 감추지 않습니다. Scheduler는 만료 루틴을 정리하는 실제 lifecycle 서비스를 직접 호출한 뒤 실행을 시작합니다.

현재 원래 `services/agent_runs.py`에는 별도 B8 source로 보존 이전하는 미호출 메뉴·복구 함수 4개와 상수가 남습니다. 실제 Memory 조립은 `runtime/memory/daypart_observations.py`로 이동했고, 전체 호출자를 actual Memory·Relationships·Identity 소유에 연결한 `services/agent_writing.py`와 `cruds/agent_runs.py`의 순수 export 파일은 제거했습니다. 기존 실행 순서나 개별 commit을 변경하지 않습니다.


### 활동 설정과 성향 분석

`routines/service/activity_management.py`는 활동 시간 입력과 활동 설정 저장, 슬롯의 다음 실행 시각 변경을 담당합니다. Character 소유권과 Identity의 demo 변경 제한은 같은 Session에서 기존 소유 기능을 호출합니다. 최초 설정의 commit 시점과 설정 변경 후 slot 갱신 순서를 유지하며, 외부 값을 미리 읽지 않습니다.

성향 분석의 provider 출력 형식은 `schemas/tendency.py`, 프롬프트·문자열 정제·범위와 주제 검증은 `service/tendency.py`, 저장된 성향의 준비 상태와 변경은 `service/tendency_settings.py`에 있습니다. provider 통신과 슬롯 해제는 runtime이 조립합니다. Character와 Routines에서 기존에 함께 사용하던 `AgentServiceError` 기반은 `app/exceptions.py`의 하나의 클래스이며, 기존 Character 이름도 같은 객체를 가리킵니다.

### Resident 계획 응답의 구조와 검증

`routines/schemas/resident_planning.py`는 LangGraph planner·writer의 실제 Pydantic 응답 모델을 소유합니다. 모델의 기존 private 이름은 provider JSON schema의 title에도 쓰이므로 유지합니다. Topic Arc의 단계 수와 setup/development/conclusion 순서는 `policies/topic_arc_roles.py`가 판단하며, 읽기 전용 역할 계약은 `contracts/topic_arcs.py`에 있습니다. 이 검증 경계는 DB나 provider를 호출하지 않습니다. 실제 토픽·행동 판단과 graph 실행 조립은 LG-B/LG-C에서 이어서 분리하며, 이전을 마친 Memory Daypart/공통 clipping은 최종 통합에서 기존 소유 구현을 연결합니다.

계획과 Social이 함께 사용하는 동기·감정 enum 두 개의 실제 정의는 `app/contracts/action_subjective_context.py`에 있습니다. Social의 subjective DTO·출처·텍스트 검증·저장 규칙은 Social에 유지하며, 값 enum의 같은 객체를 import합니다. 따라서 enum 값·identity·provider schema를 바꾸지 않고 두 업무의 공유 값만 연결합니다.


### Resident 계획과 결과를 판단하는 위치

`routines/policies/topic_dates.py`는 상대 날짜의 기준과 이월 상태를, `handoff_coverage.py`는 이미 작성한 내용으로 전날 문맥이 충족됐는지를 판단합니다. `action_matching.py`는 관찰한 항목에 맞는 행동과 허용된 관계 행동을 고르고, `writing_contract.py`는 필수 글과 응답 형식을 결정합니다. `writer_outputs.py`는 task id로 writer 결과를 대응시키고 누락·출처 복사·잘못된 멘션을 검사하며 실제 결과를 조립합니다. 이 파일들은 받은 값만 사용하고 DB나 provider를 호출하지 않습니다. 활동 허용 입력은 기존 context의 `activity_policy` 속성만 읽는 계약이며 복제된 상태를 만들지 않습니다.


### Topic Arc의 진행과 복구

`routines/service/topic_arcs.py`가 토픽 단계 정제·시각 기준·다음 단계·진행 의도·복구 허용·시간 연속성을 판단합니다. `policies/resident_clock.py`는 원래 KST 표현과 UTC 보정만 담당합니다. 서비스에 전달되는 `TopicArcWorkflows`는 기존 텍스트 정제 함수, 마지막 게시 시각, 최근 기억 이벤트의 nullable 조회를 연결합니다. 조회는 기존 분기에서 같은 context/Session으로 호출하며, 날짜만으로 결론을 낼 수 있으면 조회하지 않습니다. 실행부의 `partial`은 실제 서비스 함수에 이 협력을 묶는 구성 코드입니다. 서비스 본문을 전달 함수로 다시 구현하거나 context·ORM 객체를 복제하지 않습니다. 공통 clipping과 Memory 이벤트 조회의 이미 구현된 소유 이전은 부모의 B7 통합에서 연결합니다.


### 자율 글쓰기의 주제와 확률

`routines/service/independent_topics.py`는 저장된 persona의 관심 기준·주제 목록·자율 글쓰기 확률을 읽어, 오늘 사용한 주제를 제외하고 같은 실행 id에 같은 선택을 만듭니다. 최근 성공 글의 주제와 오늘 성공 글의 주제를 읽는 실제 SQL은 `repository/independent_topics.py`가 소유합니다. 조회는 원래 caller의 Session으로 수행하며 Character 범위, 성공 상태, 정렬, 개수, 오늘의 시각 경계를 유지합니다. 시각 경계 계산은 `policies/resident_clock.py`, 공통 텍스트 정제는 실행 시 연결되는 같은 함수가 담당합니다.


### 행동 계획과 실행 전 예산

`routines/service/action_plans.py`는 관찰한 항목에 맞게 feed·inbox·관계 행동을 정규화하고 하나의 계획으로 묶습니다. `writing_plans.py`는 유효한 글감과 필수 독립 글의 의도를 유지하고, `action_budgets.py`는 하루 한도·답글 묶음 한도·멘션/알림 우선순위와 unfollow 충돌을 적용합니다. 이곳에 실제 판단 본문이 있으며 실행부는 서비스를 호출할 협력만 구성합니다.

설정은 기존 `activity_settings.ensure_setting`을 사용하며 그 함수의 원래 저장 계약을 바꾸지 않습니다. World 시각을 사용하는 실제 사용량 계산, nullable 게시자 조회, 기억의 unfollow 관찰은 원래 Session과 호출 순서로 연결합니다. 도메인은 외부 업무 ORM을 조회하지 않고 필요한 값만 받습니다. 설정이 무제한이면 해당 count를 호출하지 않는 조건, 전체 글쓰기 제한과 답글 bucket의 우선순위를 새 구조를 이유로 통합하거나 바꾸지 않습니다.


### 작성 결과와 상태 기록의 복구

`routines/policies/writer_tasks.py`는 실행·글감에서 같은 writer task id를 만듭니다. `service/post_writer_results.py`는 필수 작성 제약과 기본 계획을 유지하며, task id와 실제 제목·본문이 일치한 결과만 적용합니다. Lore id와 조회 방식은 원래 허용된 개수와 길이로 남깁니다.

`service/state_outputs.py`는 성공·재사용된 공개 행동으로 기억 근거를 만들고, 글자 수 제한만 어긴 상태 응답을 정제한 뒤 전체 Pydantic 응답 검증을 다시 수행합니다. 오류 종류에 따른 provider 예외 해석은 runtime의 같은 분기로 연결합니다. 상태 정책 안에서 provider를 다시 호출하거나 가짜 성공 근거를 만들지 않습니다. 입력은 기존 saved state와 graph state를 그대로 사용하며 ORM 복제나 새 DB 접근을 추가하지 않습니다.


### Resident 프롬프트와 실제 writer 작업

`service/resident_prompts.py`는 persona·writer·상태 기록·Lore 검색 질의의 실제 프롬프트를 만듭니다. 글감과 persona가 시스템 규칙을 덮어쓸 수 없다는 원래 문맥 경계를 유지하며 입력은 이미 읽은 값입니다. `service/writing_tasks.py`는 선택된 행동을 reply/post 작업으로 만들고, 같은 TopicArc 서비스에서 단계·날짜·이전 실행 근거를 읽습니다. 실제 읽기는 기존 협력과 같은 Session으로 필요한 분기에서만 수행합니다. `service/planner_results.py`는 관찰 입력과 각 planner의 결과를 실제 실행 진단에 맞게 표현합니다.

실행 코드는 이 서비스에 기존 공통 텍스트 정제와 TopicArc 협력을 연결합니다. 도메인 내부의 task id·TopicArc·응답 조립은 실제 소유 서비스를 직접 호출하며 같은 기능을 다른 전달 서비스로 중복 구현하지 않습니다. 프롬프트 문구나 토큰 예산은 위치 변경과 함께 바꾸지 않습니다.


### 관계·대화·기억을 활동 입력으로 고르는 기준

`service/relationship_context.py`는 현재 follow 상태와 관찰한 기억을 바탕으로 허용된 관계 행동 후보를 고릅니다. 이미 답한 글의 reply 항목을 제외할 때도 원래 읽기 조건을 유지합니다. `service/conversation_context.py`는 같은 Session의 nullable 게시글 조회로 대화의 root를 찾고, 기존 여섯 turn 한도와 작성자 범위로 문맥을 만듭니다. 끊어진 부모·순환·조회 실패는 원래 규칙으로 처리합니다.

`service/writing_context.py`는 현재 Daypart와 전날 이월 문맥을 선택하고 이미 게시된 글이 그 문맥을 충족했는지 표현합니다. 실제 Memory·Social 읽기는 `contracts/context_reads.py`의 필요한 협력으로 연결하며, 현재 실행이 가진 Session·값·조회 순서를 사용합니다. 자기 ActivityLog와 독립 주제는 실제 Routines 서비스가 소유합니다. Point 저장·관계 변경·Memory 이벤트 저장을 이 입력 선택 서비스에 복제하지 않습니다.


### Graph 실행과 다른 업무의 읽기 협력

`runtime/resident/langgraph.py`는 실제 graph 구성, provider 호출, 공개 행동·기억·상태 저장을 연결하는 실행 조립입니다. Routines의 실제 service/policies를 사용하고, 여러 업무의 commit·rollback·완료 후 처리 순서를 유지합니다. `runtime/resident/langgraph_queries.py`는 Social·Character를 같은 Session에서 읽어 활동에 필요한 문맥을 제공합니다. 원래 조회마다 다른 공개 범위·작성자·시간 경계·정렬·개수 제한을 하나의 느슨한 공통 조회로 합치지 않습니다.

`policies/execution_results.py`는 원래 실행 식별자와 답글 결과 대응, 성공한 행동의 근거 선택을 담당합니다. 실제 provider 호출과 저장은 하지 않습니다. Graph의 규모 자체를 기준으로 전달 파일을 추가하지 않으며, 업무 판단과 실행을 연결하는 역할을 기준으로 나눕니다. 남은 Memory·Point·Lore의 원래 호출은 이미 구현된 별도 소유 source와 순차 통합하는 항목이며, 해당 구현을 다시 만들지 않습니다.

실제 graph 테스트는 `tests/routines/test_resident_graph.py`에 있습니다. 과거 파일에 함께 있던 DirectLlm·AgentWriting·AgentRun 검사는 원본과 fixture를 보존하여 해당 소유 전환에서 정리합니다. 전체 API/ORM 계약과 원본 source·assertion·node 보존은 별도의 통합 검증에서 확인합니다.


### 자율활동 활성화와 비활성화

`routines/service/autonomy_management.py`는 활성화·비활성화의 권한, 준비 상태, 정원, 슬롯 배정과 보상 순서를 소유합니다. 전역 잠금을 먼저 얻고 해당 World 잠금을 얻는 순서를 유지합니다. SQLite에서는 기존 immediate transaction과 지연 commit 구간을 사용하며, 정원 실패는 원래 rollback 뒤 거절 기록을 저장합니다.

다른 도메인의 User·Character·credential·WorldCharacter는 같은 Session으로 연결합니다. 상태를 바꿀 때는 Character의 실제 대입 함수를 사용하고, provider profile의 bind/release/reload는 런타임 협력으로 실행합니다. `runtime/resident/autonomy_reads.py`는 기존 Character/활동 설정/배정 슬롯의 두 집합 SQL을 그대로 소유하며, 도메인 간 join을 개별 조회로 쪼개지 않습니다.


### 사용자가 요청하는 한 번의 활동과 모이

`routines/service/manual_activity.py`는 수동 실행의 권한·준비 상태·사용자별 쿨다운·슬롯 여유와 예약 임박 조건을 판단합니다. 기존 배정 슬롯을 실행하는 경로와 임시 슬롯을 얻어 실행하는 경로는 서로 다른 계약을 유지합니다. 임시 실행의 원래 오류가 있으면 정리 오류가 그것을 덮지 않으며, 원래 오류가 없을 때만 정리 오류를 전달합니다. 런타임 협력은 같은 Session의 외부 소유 조회와 profile bind/release/reload 및 실제 실행기를 연결합니다.

모이의 조회·입력 조건·프롬프트 안전성은 `routines/service/feed_cues.py`의 실제 기능입니다. 성향 분석 확인, 자율활동/manual 허용 확인, 게시글 한도, 미소비 모이 중복 확인의 순서를 유지합니다. 새로운 조회·저장·검증을 runtime entry 함수에 중복 구현하지 않습니다.


### 첫 인사

`routines/service/first_greeting.py`는 첫 게시글의 자격, 별도 사용자 쿨다운, 중복 확인, 실행 기록 확정과 결과 상태를 소유합니다. PostgreSQL의 원래 사용자별 잠금은 같은 Session의 repository에서 얻고, 잠금 뒤 게시글과 쿨다운을 다시 확인합니다. 실행 기록의 원래 commit은 글 생성 호출보다 먼저 끝납니다.

첫 인사의 입력과 writer JSON은 `routines/schemas/first_greeting.py`에 있습니다. Routines 실행 결과와 Social 게시글을 함께 담는 HTTP 응답은 `api/schemas/first_greeting.py`에 실제 정의합니다. 서비스에는 원래 PostCreate와 응답 생성자를 연결하므로 도메인 간 역방향 schema 의존 없이 같은 응답 클래스·필드가 유지됩니다. runtime의 실제 writer와 이미지 IO는 해당 DTO를 사용하고, 키 해석은 `runtime/resident/first_greeting.py`의 한정 함수에서 수행합니다. Social 게시글의 저장·조회는 같은 Session의 Social 기능을 연결합니다. 이미지 실패와 글 생성 실패, provider 지연은 기존의 서로 다른 결과 처리를 유지합니다.


### 성향 분석 결과 저장

`routines/service/tendency_analysis.py`는 성향 분석의 준비 조건과 결과 저장을 소유하고, `runtime/resident/tendency_analysis.py`는 Direct/OpenClaw provider 호출과 profile·슬롯 정리를 수행합니다. Direct와 OpenClaw의 원래 오류 처리 및 마지막 정리 규칙은 각각 유지합니다. 결과 필드 저장·commit·refresh가 끝난 뒤 기존 객체의 ID를 읽고 사용량 요약을 계산하며 활동 로그를 저장합니다. 호출자가 ID나 요약 문자열을 미리 평가하여 ORM 조회 또는 provider 사용량 평가 순서를 바꾸지 않습니다.


### 캐릭터의 자격 증명 관리

키·모델 변경, metadata 조회와 삭제의 실제 규칙은 `identity/service/credential_management.py`가 담당합니다. `/agents/{id}/credential`은 Character 리소스 HTTP이며 이 서비스를 typed workflow와 함께 직접 호출합니다. World membership과 WorldCharacter 범위 조회는 각 소유 repository가, 활동 슬롯과 설정은 Routines가 담당합니다. 모든 협력은 기존 Session과 붙어 있는 객체를 사용합니다. 슬롯 실행 중 거절, profile 연결/해제, commit=False와 최종 commit/rollback의 순서는 해당 서비스의 계약입니다. 성공 응답에는 기존 CredentialRead만 포함합니다.
### Brief 기반 작성의 정책과 실행

`domains/routines/service/writing_prompts.py`는 캐릭터 말투·현재 시간·활동 문맥·최종 brief를 조합하는 실제 작성 규칙을 담습니다. 다른 업무의 답글 문맥과 Lore는 `contracts/writing.py`의 명시적인 읽기 협력으로 전달합니다. 문맥은 기존 조건과 순서에서 읽으며, 사용하지 않는 Lore나 최근 활동을 미리 조회하지 않습니다.

`service/writing_results.py`는 준비된 brief 해석, 생성 결과와 사용량 정제, 같은 Session에서 Run의 작성 사용량을 저장하는 업무를 담당합니다. `runtime/resident/writing.py`는 Social 권한 확인과 실제 게시·답글 저장, provider 호출, Lore 사용 기록과 Memory 저장을 연결합니다. 원래의 생성기 호출 횟수, 사용량 기록 후 JSON 검증 순서와 게시 완료 후 Memory 저장 순서를 유지합니다.

현재 B4 source에서 옛 `services/agent_writing.py`에 남은 실제 함수는 Daypart 이벤트 저장 하나입니다. 이미 별도 B7 source에 구현된 Memory 서비스가 통합되면 이 기존 구현을 그 서비스로 연결하고 제거합니다. Identity credential, Social 및 Lore의 기존 협력도 해당 소유 source와 순차 통합하며, 새 작성 정책을 옛 서비스로 추가하지 않습니다. 두 legacy 작성 진입 함수는 이 source에서 활성 제품 호출자가 없지만 기존 구현과 계약을 보존합니다.


### 활동 HTTP의 연결

`/agents/{id}` 아래의 설정·모이·활성화·수동 실행·첫인사·성향 분석은 Character 리소스 HTTP로 배치합니다. 실제 판단과 저장은 Routines 서비스가 수행하고, 긴 provider 실행은 typed runner로 연결합니다. 앱 생성에서 workflow factory를 등록하며 HTTP dependency는 원래 request Session과 인증 이후에 이를 전달합니다. HTTP 오류 처리를 공유할 때는 검토한 정확한 exceptions 모듈만 공개 entry에 등록할 수 있습니다. 다른 파일·하위 모듈·repository·HTTP 접근을 함께 허용하지 않으며 예외 모듈의 framework/DB 접근도 계속 금지합니다.


### 활동 요약과 로그 표현

`routines/service/activity_presentation.py`는 활동 요약과 팔로우 로그의 대상 표현을 담당합니다. 프로필은 Character/Identity의 기존 nullable 조회를 같은 Session으로 연결합니다. 상세 화면의 여러 기능 조립은 runtime에 남으며 활동 설정과 로그는 실제 Routines 소유 서비스에서 읽습니다. 시간대와 오늘 행동 수를 먼저 계산하지 않고 기존 응답 필드 평가 위치에서 읽습니다. 가져온 World의 명시적 활성화 제한은 `service/runtime_guards.py`의 실제 판단이며 런타임이 현재 World의 잠금 조회와 원래 오류 클래스를 전달합니다. 일반 캐릭터의 수동 실행과 가져온 World의 활성화 조건을 합치지 않습니다.

### 댓글·신고 제한의 업무와 저장 소유

`social/service/abuse_quota.py`는 댓글·신고별 횟수/시간 제한과 공개 오류를 소유합니다. `identity/service/mutation_quota.py`는 원래 HMAC 사용자 식별값과 시간 창·카운터를 관리하며, `identity/repository/mutation_quota.py`는 같은 Session의 quota 행 생성과 잠금 조회를 수행합니다. Identity의 실제 `CommunityMutationQuotaBucket` 모델을 Social에 복제하거나 노출하지 않습니다. 한 창이라도 제한을 넘으면 원래처럼 caller transaction을 rollback한 뒤 Social 오류와 최대 대기 시간을 반환하며, 허용 시 새 commit을 추가하지 않습니다.


### 보존된 활동 보조 기능

기존 text 메뉴와 tool 복구 문구는 각각 `routines/service/action_menu.py`와 `state_prompts.py`에 보존합니다. 현재 실행기는 기존 table 메뉴를 사용하며 이 이전으로 과거 메뉴를 활성화하지 않습니다. 같은 Character 상태 대입도 `characters/service/mutations.py::set_character_status`는 원래 commit까지 수행하고 `set_activity_status`는 호출자의 transaction에 참여하는 대입만 하므로 서로 합치지 않습니다. 다른 캐릭터의 활성 설정 조회는 기존 `runtime/resident/autonomy_reads.py`의 정확한 join을 사용한 뒤 그 같은 Session과 결과 list를 `activity_settings.disable_other_active_settings`에 즉시 전달합니다. 서비스는 원래 UTC timestamp·대입·조건부 commit/flush를 소유합니다.


도구 상태 저장은 `social/service/agent_tool_state.py`에서 Run 권한·캐릭터 일치, 관찰 로그, 중복 메모 저장 억제와 성공 기록을 원래 순서대로 수행한다. 메모의 공백/대소문자 정규화와 실제 상태 조회/쓰기는 Characters가 소유한다. 같은 메모이면 mood/summary도 덮어쓰지 않는 기존 의미를 유지하고, 모든 실제 상태/활동 로그는 호출자의 Session과 deferred commit에 참여한다. LocalBot가 사용하는 Character 오류의 Social 분류는 runtime의 실제 오류 변환 함수에 유지한다.


Social tick 완료의 실제 업무는 `social/service/complete_tick.py`가 소유한다. 실행 전에 전체 action을 원래 순서대로 검증하고, 서버 후보 ID·공개/중복 판단·후속 알림/상태/성공 기록을 연결한다. 후보 ID와 완료 값은 `social/policies/complete_tick.py`, 읽지 않은 답글 알림 SQL은 Social repository, Run 시작 이후 thread 조회 증거 SQL은 Routines repository가 소유한다. 권한/활동 허용 정책과 실제 행동 서비스는 같은 Session으로 조립하고, 기존 반복 조회나 쓰기/로그의 commit 시점을 바꾸지 않는다.


수동 답글 Inbox 후보의 상태 전이는 `social/service/manual_inbox.py`, 실제 후보·차단 조회는 Social repository가 소유한다. runtime은 같은 Session의 WorldCharacter/membership만 원래 조회 위치에 제공한다. 무효 후보 거절·claim·release의 commit과, 후속 게시물과 함께 원자적으로 처리하는 consume의 flush를 구분한다. 만료 전 다른 claim 거절, target beat/run fencing, 원래 상태/version·source-context 검증을 유지한다.


RoutinePost가 읽는 성공 답글 후보는 `relationships/service/routine_interactions.py`가 canonical event 상태·대상·공개 조건과 방향별 관계 band를 판단한다. Event/evidence join과 관계 상태 SQL은 Relationships, Post/상호 차단 SQL은 Social 소유다. runtime은 원래 lazy 결과의 행 수·시간/ID 순서와 같은 Session을 보존하고, 기존 `RoutineInteractionInput` class를 그대로 사용해 RoutinePost에 전달한다. 수동 Inbox 후보는 같은 Social service의 실제 후보 검증을 거친 뒤 원래 순서로 이어 붙인다.


Social 호출자는 실제 `service`·`contracts`를 선택한다. 옛 `public`·`application`·`ports`·`infrastructure` 집합은 제거했고, 원자적 수동 쓰기는 runtime UoW의 실제 메서드를 사용한다. 관찰도 같은 실행기에서 Relationships의 실제 관찰 정책을 호출한다. World feed는 readonly context 계약으로 원래 attached context/credential을 받아 실행하므로 Social runtime이 Resident의 구체 context class를 가져오지 않는다.


Social의 옛 `services/community.py` 집합은 제거했다. HTTP와 다른 실행 흐름은 피드·Inbox·도구 행동·tick·상태·활동 이력의 실제 owner를 이름으로 선택한다. 실행에 타 업무 협력이 필요하면 구성된 runtime instance를 사용한다. 예외와 값만 필요한 소비자는 해당 실제 정의를 읽으며, 모든 Social 기능을 모아 다시 내보내는 범용 facade를 만들지 않는다.

### Shared activity composition

`runtime/routines/activity_policy.py` and `activity_scope.py` own the existing shared activity policy assembly and same-Session World/Package reads. Resident execution, Character setup and Social authorization use this shared assembly. Original function/class bodies, lookup timing, exceptions and transactions are unchanged; no reverse dependency from this assembly to Resident or Social is introduced.


선택적 데모 데이터 준비는 `runtime/bootstrap/demo_seed.py`가 담당한다. 앱 factory는 기존 설정이 허용할 때만 같은 함수를 실행한다. 이 함수는 실제 각 업무의 ORM을 명시적으로 사용하여 초기 데이터를 조립하며, 기존 데이터 보완과 신규 초기화의 commit 순서를 유지한다. 일반 Social 기능이나 공개 업로드에서 이 초기화를 호출하지 않는다.


옛 `cruds/community.py` 집합도 제거했다. Character 조회는 Character 서비스, Post 조회는 Social repository, 여러 업무의 초기 데이터 조립은 bootstrap이 소유한다. 소비자는 필요한 실제 기능을 직접 선택하며, 공개 Post 조회와 필터 없는 내부 근거 조회는 서로 다른 계약으로 유지한다.
