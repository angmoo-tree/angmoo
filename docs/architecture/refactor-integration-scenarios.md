# Angmoo 통합 회귀 시나리오와 실행 근거

Angmoo의 구조 전환은 기존 기능의 API·데이터·화면·실행 의미를 유지한다. 이 문서는 기능을 수정한 기여자가 어떤 회귀를 확인해야 하는지 설명한다. 코드 위치는 [기능 보존 지도](refactor-feature-preservation.md), 현재 파일·소비자·전체 관련 테스트는 [K01~K24·G01~G13 원장](../../security/refactor_feature_inventory.json), 실제 PR·병합·설치 결과는 [통합 검증 기록](refactor-integration-results.md)을 따른다.

## 세 종류의 근거를 함께 읽기

1. **원래 계약의 보존:** PR #258의 고정 source와 이후 checkpoint·최초 도입 원장이 원본 파일, API/ORM, assertion, 수집 node, UI fixture와 시각 기준을 보호한다. 경로가 바뀌면 현재 대응표로 연결한다. 삭제된 assertion을 현재 결과에 맞춰 다시 승인하지 않는다.
2. **실제 행위 검사:** API 응답만 아니라 DB 상태, 사건·provider 호출 수, 원자성, 재시도와 재시작 결과를 확인한다. 실제 SQLite/API 검사와 브라우저의 통제된 응답 fixture는 서로 다른 근거다.
3. **실행 환경의 연결:** 같은 기능 구현을 Next·정적 화면·Docker·Host Tauri·설치 앱이 올바르게 연결하는지 확인한다. native 저장 대화상자와 다중 창, 실제 설치·종료는 해당 환경에서 확인한다.

PR #258의 별도 checkout에서 실행한 전체 backend는 1845 PASS·22 SKIP / 1867 collected였다. 이 숫자만으로 현재 기능 보존을 판단하지 않는다. 같은 원래 node를 현재 경로에 연결한 실제 결과와 원래 assertion의 유지, 이후 도입 테스트를 함께 확인한다. 원본 checkout의 source나 기대값을 현재 코드에 맞춰 고치지 않는다.

## 제품 흐름별 검사 위치

표의 파일은 시작 위치이며 해당 K 항목의 전체 `test_paths`를 대신하지 않는다. 각 시나리오는 성공뿐 아니라 권한 거절·실패·삭제·scope 격리와 재실행을 포함한다.

| 시나리오 | 보호하는 흐름과 결과 | 주요 K | 대표 검사 시작 위치 |
| --- | --- | --- | --- |
| S01 초기 실행·owner·생성·설정 | 미소유 설치에서 owner 한 명을 확정하고 세션 hash만 저장한다. 재진입·CSRF/Origin·프로필/설정 저장과 scope를 유지한다. | K01~K03·K13 | [owner/session](../../backend/tests/identity/test_l1_local_owner_session.py), [Home](../../backend/tests/device_home/test_world_surface.py), [설정 화면](../../browser-tests/ui-e-local-settings/local-settings.spec.ts) |
| S02 활동 준비·일일 계획·재시작 | WorldCharacter의 승인·활성화, 4개 시간대 계획, episode/beat/cursor와 이미 소비한 사건의 상태를 유지한다. | K04·K05·K08 | [활동 runtime](../../backend/tests/routines/test_daily_activity_runtime.py), [claim 복구](../../backend/tests/routines/test_guarded_claim_recovery.py), [WorldCharacter](../../backend/tests/world_characters) |
| S03 SNS·Inbox·관계·검색 | 수동 쓰기의 추가 AI 호출이 없고 성공 사건·관찰·관계 방향과 World 범위를 구분한다. FTS/graph 결과는 canonical 상태를 다시 확인한다. | K06~K09·K20 | [수동 SNS/Inbox](../../backend/tests/social/test_l3_owner_manual_social_inbox.py), [Social 검색](../../backend/tests/social/test_world_feed_search.py), [관계 화면](../../browser-tests/relationship-graph/product-shell.spec.ts) |
| S04 패키지·미디어·새 설치 | 두 합성 data root 사이 export/import에서 private runtime·secret을 제외하고 ID/binding·asset/license를 유지한다. import는 원자적이며 명시적으로 활성화하기 전 자율 실행하지 않는다. | K03·K04·K10·K11 | [두 root 왕복](../../backend/tests/world_packages/test_closeout.py), [import/실패 복원](../../backend/tests/world_packages/test_import_commit.py), [proxy](../../frontend/scripts/test-world-package-proxy.mjs) |
| S05 World Chat·Router·stream | World/양쪽 Character·thread·model snapshot을 고정하고 Router route·호출 상한·NDJSON 순서·취소/재시도·중복 방지를 유지한다. | K14·K17·K18 | [Router](../../backend/tests/chat/test_p8_l_k_retrieval_router.py), [BOTH 조립](../../backend/tests/chat/test_p8_l_n_both_workflow_coordinator.py), [근거 stream](../../backend/tests/chat/test_p8_l_p_evidence_response_streaming.py) |
| S06 기억 관리·근거 회상 | ON/OFF·pin·정정·삭제·retention은 scope와 version을 확인한다. 정정은 원래 근거를 다시 검증하고 삭제는 회상에서 즉시 차단한다. | K15·K16·K19 | [owner 관리](../../backend/tests/memory/test_p8_l_r_memory_owner_control.py), [Memory 회상](../../backend/tests/memory), [정적 UI](../../browser-tests/static-product-shell.spec.ts) |
| S07 source→배치→기억→후속 입력 | 성공 source의 delivery, 별도 opt-in, retain/skip·원자 저장·근거 연결·Hot Brief와 재시작 이후 입력의 인과를 fake provider로 확인한다. | K18·K20~K22 | [배치 인과/안전성](../../backend/tests/memory/test_p8_l_r_memory_batch_safety.py), [배치 runtime](../../backend/tests/memory/test_p8_l_r_memory_batch_runtime.py) |
| S08 종료·재기동 | child 닫기·트레이 숨김과 전체 종료를 구분한다. 전체 종료 예산, deadline/cancel, sidecar/listener 정리와 durable 복구를 확인한다. | K12·K22·K23 | [종료·늦은 provider](../../backend/tests/memory/test_p8_l_r_memory_batch_safety.py), [화면/native 연결](../../browser-tests/refactor-lifecycle.spec.ts), [설치 CI](../../.github/workflows/windows-installer.yml) |
| S09 실패·OFF·삭제·경쟁 | source/설정/lease가 바뀐 늦은 결과를 저장하지 않는다. retry는 유한하며 다른 owner/Character를 보존하고 projection 장애가 canonical 권한을 우회하지 않는다. | K01·K09·K11·K12·K15~K18·K21~K23 | [batch fence/scrub/retry](../../backend/tests/memory/test_p8_l_r_memory_batch_safety.py), [graph replay](../../backend/tests/relationships/test_projection_replay.py), [업그레이드 데이터](../../backend/tests/migrations/test_populated_memory_upgrade.py) |
| S10 화면·탐색·지원 기능 | Phone/Studio/Graph·Memory·Settings·Tree·지원 route의 직접 진입과 뒤로 가기, focus/keyboard·scroll·선택 상태를 유지한다. | K02·K13·K19·K24 | [웹 화면](../../browser-tests/product-shell.spec.ts), [정적 화면](../../browser-tests/static-product-shell.spec.ts), [고정 visual](../../browser-tests/product-surfaces.visual.spec.ts) |

S07의 fake provider는 선택 결과·실패·stale 응답과 물리 호출 수를 통제한다. 실제 모델이 좋은 기억을 선택하고 대화 품질을 높이는지는 P8-L-S의 별도 검증이다. UI fixture를 사용한 S06/S10의 결과도 실제 DB 저장이나 네이티브 창 검증을 대신하지 않는다.

## 공통 기반과 데이터

| 범위 | 확인하는 계약 |
| --- | --- |
| G01·G09·G10·G11 | 설정 우선순위, frozen lock, 지원 runtime 의존성과 환경 예시, 개발 `.env` 없는 설치, 비밀/개인 데이터의 Git·패키징 제외 |
| G02·G05·G13 | 단일 Base/metadata, 명시적인 engine/session, SQLite transaction·PRAGMA, Alembic 역사와 지원 v1~v8→v9 migration |
| G03·G04 | HTTP·업무 오류와 retry 의미, scope별 cursor·정렬·limit·잘못된 cursor·누락/중복 방지 |
| G06·G12 | `app/main.py`의 단일 앱 생성과 지원 profile, 모델 등록·startup/shutdown·로그 handler 및 redaction, 제거된 실행용 `public_main` 참조 부재 |
| G07·G08 | 테스트 수집·fixture/conftest·동적 경로·CI와 필수 지원 자원. 사용하지 않는 templates/testing 폴더를 형식만 맞추려고 생성하지 않음 |

[데이터가 채워진 Memory 업그레이드 검사](../../backend/tests/migrations/test_populated_memory_upgrade.py)는 64자 이전 generation의 v8 DB에 owner·World·WorldCharacter, ON/OFF·retention·version, 활성/pinned·superseded·deleted 기억과 evidence를 넣는다. v9 전환과 반복 실행에서 관련 행의 모든 열 값, ID 연결과 FK를 비교한다. 새 batch 테이블이 비어 있어 자동 유료 동의가 생기지 않는지도 확인한다.

같은 검사의 거절 경우는 migration이 소유하지 않은 기억 내용을 의도적으로 바꾼다. 실제 coordinator가 변경을 검출해야 하며, 이전 source 파일 hash·행·현재 marker가 그대로 남고 임시 generation이 정리돼야 한다. 단순 테이블 개수 비교만 통과하는 회귀를 방지하기 위한 검사다. 사용자 설치 DB를 fixture로 복사하지 않는다.

기존 migration 원문과 고정 predecessor 자료는 수정하지 않는다. [역사적 import 호환](backend-compatibility.md)을 유지하며, 새 검사도 현재 실제 모델과 migration coordinator를 사용한다.

## CI 결과 파일 읽기

[Core CI](../../.github/workflows/ci.yml)는 원래 전체 suite를 실행하면서 backend JUnit과 웹·설정·정적·lifecycle·고정 Linux visual의 JUnit을 각각 보관한다. 검사 대상·재시도 정책·기대값·snapshot은 보고서 추가 때문에 바뀌지 않는다.

- `source_sha`는 검증하려는 PR head 또는 push SHA다. `checkout_sha`·tree는 runner가 실제로 실행한 checkout이다. PR에서는 GitHub가 만든 임시 merge와 PR head가 다를 수 있으므로 둘을 모두 기록한다.
- identity 파일의 event·run ID/attempt·Python/uv 또는 Node/pnpm·lock hash를 결과와 함께 읽는다. 과거 head의 XML을 새 head의 PASS로 옮기지 않는다.
- 업로드는 Core의 정확한 JUnit 6개와 identity 2개로 한정한다. 일반 파일·DB·환경 파일·디렉터리 wildcard는 CI 정책에서 거절하며, 통제된 합성 fixture 결과를 보관한다.
- 테스트가 실행되기 전에 job이 실패했거나 XML이 없으면 PASS가 아니다. 실패 보고서도 보관하며, backend 전체와 브라우저의 필수 다섯 suite를 구분한다.
- 원장의 `test_paths`에는 fixture/helper도 포함된다. 수집 node가 없는 지원 파일은 실제 테스트 소비자와 연결하고, 실행했다고 임의의 PASS 숫자를 부여하지 않는다.

기존 PostgreSQL URL 전용 skip 및 public profile 밖 Hosted lifespan skip은 정확한 이유와 node를 유지한다. SQLite 제품 경로가 통과했다는 사실을 PostgreSQL 전용 분기의 검증으로 확대하지 않는다.

## 최종 실행 환경의 확인

Next 웹·정적 preview의 자동 회귀, 실제 API를 사용하는 Docker, 공식 Host Tauri, 최종 설치 산출물은 각각의 근거가 필요하다. 같은 backend 업무 시나리오를 모든 창에서 중복 실행할 필요는 없지만 각 경로의 인증/요청·저장·탐색·종료 연결은 확인한다.

Host는 Docker의 합성 contributor data와 native 창을 사용하며 설치 앱 sidecar를 만들지 않는다. 설치형은 CI artifact의 SOURCE_SHA·checksum·payload manifest와 실제 host/sidecar 파일·프로세스·listener를 연결한다. headless CI의 강제 종료 fallback을 실제 UI 전체 종료 확인으로 기록하지 않는다.

실제 확인 결과는 `CI`, 위임받은 실행은 `DELEGATED CHECK`, 사용자가 직접 수행한 결과는 `USER CHECK`로 구분한다. 최종 source/merge·각 환경·성공/실패·제한은 통합 검증 기록에서 확인한다. Release/Production과 P8-L-S의 실제 AI 품질 완료는 이 구조 회귀의 결과로 앞당기지 않는다.
