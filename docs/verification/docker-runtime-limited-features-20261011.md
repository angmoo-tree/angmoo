# Docker 일부 기능 제한: 연결 경합 복구와 Media 실행 경계 수정 결과

- 날짜: 2026-10-11, 로컬 검증
- 저장소: `D:/project_code/angmoo-workspace/angmoo-tree-angmoo`
- 브랜치: `feat/0.1.0-release-readiness`
- 작업 시작 HEAD: `f4a640771e970daabfd49b2060939d38e0624011`
- 범위: 현재 Docker의 `일부 기능 제한` 원인 수정. 출처·권한 검증과 기존 데이터 보존.
- Git 정책: 현재 로컬 브랜치와 로컬 커밋만 사용. PR, push, CI 워크플로, main 병합 없음.

## 확인한 문제와 원인

작업 시작 시 `angmoo-backend-1`은 실행 중이지만 unhealthy였고, 컨테이너
내부 `/health`는 HTTP 503 / `embedded_runtime_not_ready`를 반환했다.
로그에는 SQLAlchemy `QueuePool` 연결 부족과 관계망 작업자의 종료,
기억 검색 색인의 페이지 재구성 실패가 있었다.

1. 저장하지 못한 경험을 조회할 때 같은 출처와 이전 기억 계보를 개별 기록마다
   반복 검증하면서 SQL 처리량이 증가했다. 공유 풀의 크기는 5, overflow는 10,
   연결 대기 제한은 30초였다.
2. 이미지 생성 작업과 정기 유지보수가 비동기 루프에서 동기 SQL을 실행했다.
   연결을 기다리는 동안 루프가 멈추면 다른 요청·비동기 작업의 진행과 연결 반환,
   스케줄러 heartbeat까지 지연될 수 있었다.
3. 관계망 작업자는 원본 SQLite 연결 대기 TimeoutError를 처리하지 못해 종료됐다.
   기억 FTS 작업자는 페이지 실패 후 degraded가 되고 다음 커밋 알림을 기다려,
   연결이 복구되어도 새 커밋이 없으면 재구성이 계속되지 않았다.

화면의 상태 배지는 runtime 상태를 표시한다. 실제 작업자의 복구와 준비 상태가
돌아오도록 수정했으며 상태 판정 조건은 유지했다.

## 구현과 유지한 계약

| 변경 | 구현 | 유지한 조건 |
| --- | --- | --- |
| Media의 동기 실행 경계 | 기존 Memory 실행 큐의 취소·소유·drain 계약을 `SqliteAsyncTaskQueue`로 공통화. Media는 작업자 1개, 수용량 4개인 큐를 소유한다. | 각 SQL 단계가 작업자 안에서 Session을 열고 닫는다. 요청 Session이나 ORM 객체를 스레드 사이로 전달하지 않는다. |
| 이미지 처리 단계 | 작업 탐색, 준비, 제출 직전 확인, 영수증·진단 저장, 결과 저장과 유지보수를 큐에서 수행한다. 제공사 I/O는 기존 비동기 실행을 유지한다. | 소유권·설정 재검사, 한도, attempt 전이, lease token, 늦은 결과 차단, spool 복구, 결과 불명 작업의 재제출 금지는 유지한다. |
| 종료 | 유지보수와 생성 작업을 멈춘 뒤 실행 중인 로컬 작업을 drain하고 Media를 해제한다. | 취소 시 실행 중인 SQL을 소유 없이 방치하지 않는다. |
| 관계망 작업자 | 원본 연결 checkout timeout 때 degraded를 알리고 같은 루프에서 재시도한다. 기본 폴링 간격부터 최대 30초까지 backoff한다. | 기존 작업 lease·최종 반영 조건은 그대로 사용한다. 실제 성공한 batch/probe 이후에만 ready가 된다. |
| 기억 FTS | 실패한 페이지는 새 커밋 없이도 1초부터 최대 30초 간격으로 재시도한다. | 32개 페이지와 build/validate/orphan/promotion 검사를 유지하며 준비 중 검색 제한을 해제하지 않는다. |
| 저장하지 못한 경험 목록 | 한 요청·Session·시각 안에서만 `MemoryAccessValidation`을 공유한다. | 다음 요청은 현재 권한·출처를 다시 확인한다. 캐시를 runtime이나 reader에 보관하지 않는다. |

관계망의 일반 RuntimeError 등을 일괄 무시하지 않는다. 저장소의 지속적인 실패는
degraded로 남으며, 성공하지 않았는데 ready로 표시하지 않는다. SQLite 풀의 용량,
대기 제한, 권한·출처 정책, health 기준과 DB 스키마는 변경하지 않았다.

## 트레이드오프

Media의 짧은 로컬 단계는 작업자 하나에서 직렬 처리한다. 한 단계가 오래 걸리면
다른 Media 로컬 단계도 기다리지만, 서버의 비동기 루프와 제공사 I/O를 멈추지 않고
작업자·대기 작업 수를 제한한다. 기존 Memory 큐와 같은 수명 관리 코드를 사용해
취소·종료 규칙을 두 곳에서 따로 유지하는 비용을 줄였다.

재시도는 파생 자료와 작업자에만 적용하며 기존 lease와 반영 검사를 유지한다.
일시적인 연결 부족 이후 자동 복구가 가능하고, 지속 실패의 재시도 빈도는 제한된다.
목록 최적화는 한 요청 안의 같은 사실만 재사용하므로 다음 조회의 권한 변경을 놓치지 않는다.

## 회귀 검증

모든 pytest 실행은 `ANGMOO_DENY_EXTERNAL_NETWORK=1`과 외부 네트워크 차단 fixture를
사용했다. pytest가 생성한 임시 DB·자료에서 검사했으며 실제 AI API 시험 호출은 없다.

| 묶음 | 결과 | 주요 확인 |
| --- | --- | --- |
| Windows 집중 회귀 | **70 passed**, 3 warnings, 125.73초 | 이미지 생성/복구, Chat 첨부, 원본 연결 대기, 기억 목록의 권한, 실행 큐 취소·종료, FTS 복구, 관계망 재시도 |
| Windows 추가 회귀 | **92 passed**, 196.73초 | 구조 검사기 회귀, 이미지 작업·첨부 소유권, SNS 전달 증명과 부모 출처 복구 |
| Docker Linux 집중 회귀 | **19 passed**, 3 warnings, 63.06초 | 아래 명령의 다섯 파일. 같은 연결 부족·재시도·권한 시험을 Linux에서도 확인 |

위 묶음에는 겹치는 시험이 있으므로 개수를 합쳐 고유 시험 수로 해석하지 않는다.
warnings는 Starlette/httpx/anyio 및 HTTP 422 명칭 관련 지원 중단 예고다.

```powershell
docker exec -u 10001:10001 -e ANGMOO_DENY_EXTERNAL_NETWORK=1 angmoo-backend-1 .venv/bin/python -m pytest -q tests/image_integration/test_media_worker_responsiveness.py tests/relationships/test_graph_projection_worker.py tests/memory/test_recall_projection_responsiveness.py tests/memory/test_situation_recovery_http.py tests/memory/test_canonical_worker_lifecycle.py
```

추가한 시험은 실제 SQLite 풀 크기를 1로 제한하고 연결을 점유한 뒤 비동기 timer로
반환하여, 이미지 작업의 SQL 대기가 timer를 막지 않는 것을 확인한다. 관계망도
실제 연결 부족 후 같은 루프에서 한 번만 반영되는 것을 확인한다. 반복 실패는
ready가 되지 않고 backoff한다. FTS는 새 커밋 없이 복구하고 준비 중 검색 검사를
유지한다. 목록은 같은 요청에서 출처 조회를 줄이고, 다음 요청에서 글이 숨겨지면
설명 노출을 막으면서 허용된 저장 포기 조작은 제공한다.

기존 이미지 시험 fixture 두 곳도 현재 제품 계약과 맞췄다. ComfyUI에는 서버 API 키를
보내지 않도록 했고, Chat 이름 캡처는 현재 실제 계약 구현을 사용하게 했다.
새 시험의 `Base` fixture 참조와 진단 callback 주입 오류는 검증 중 수정했다.
제품의 ComfyUI·Chat 동작이나 검증 정책을 완화하지 않았다.

### 실제 소스 구조 검사에서 남아 있는 기존 문제

구조 검사기의 pytest 통과와 저장소 전체 정책 통과는 별개다. 작업 시작 HEAD를
`git archive`로 격리해 실제 AST inventory/policy를 비교했으며,
**HEAD 6건 / 현재 6건 / 추가 0건 / 제거 0건**이었다.

- Chat `contracts.evidence_reads`와 `relationship_evidence_policy`의 cross-domain deep import: 두 import가 일반 검사와 refactor role 검사에서 각각 보고된다(4건).
- Identity의 `service.world_credentials` / `service.world_image_credentials` module cycle(1건).
- Memory의 `contracts.activity_situation` / `contracts.situation_source_binding` module cycle(1건).

기존 6건은 이번 연결 경합 수정과 별도로 남아 있다. 정책이나 baseline을 바꾸지 않았으며
저장소 전체 구조 정책을 PASS로 판정하지 않는다. `git diff --check`는 통과했다.

## 실제 Docker 상태와 확인 범위

사용자가 이미 실행한 Compose Watch가 수정된 Python 소스를 자동 동기화하고
StatReload로 앱 프로세스를 다시 시작했다. 수동 restart/rebuild 명령은 수행하지 않았다.
변경된 제품 소스 8개의 SHA256을 로컬 파일과 컨테이너 파일에서 비교해 모두 일치했다.

| 확인 | 수정 후 결과 |
| --- | --- |
| `angmoo-backend-1` | running / **healthy**, 컨테이너 RestartCount 0 |
| `angmoo-frontend-1` | running / **healthy** |
| 컨테이너 내부 `/health` | HTTP 200, status=ok, scheduler/projector=ready |
| 정상 로컬 세션으로 호출한 `/api/backend/runtime/status` | HTTP 200, `local-runtime-status-v1`, **installation_state=ready**, 마지막 표본 약 116ms |
| 세부 구성요소 | backend, sqlite, ladybugdb, scheduler, projector 모두 **ready**, reason_code 없음 |
| 프론트엔드 기존 표시 계약 | ready → healthy → **준비됨** |

최종 자동 재로딩 이후 확인 시점까지의 컨테이너 로그에서 `QueuePool limit`,
`in-process projector component failed`, `memory_recall_projection_page_failed`,
`image_worker_local_failure:TimeoutError`는 각각 0회였다.

실제 브라우저 화면은 컴퓨터 사용 도구의 초기화 실패
(`failed to write kernel assets`, OS error 3)로 직접 확인하지 못했다.
화면이 사용하는 정상 인증 상태 API와 표시 매핑은 확인했으며 직접 UI PASS와 구분한다.
이 기록은 Docker 진단 결과이고 Windows 설치본 상태를 판정한 것이 아니다.

원본 데이터 볼륨, 저장된 API 키, 사용자 설정을 삭제·초기화·변경하지 않았다.
서비스의 정상 자동 활동을 중단하지 않았으므로 원본 DB 바이트가 작업 전후 동일하다고
주장하지 않는다. 장시간 자연 활동·실제 AI 품질 시험은 이번 회귀 범위에 포함하지 않았다.
