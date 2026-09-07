# 구조 리팩터링 통합 검증

AR-X는 backend와 frontend 전환 이후 남은 역할 정리와 기능·데이터·지원 실행 경로의
통합 검증이다. 구조 설명은 각 `ARCHITECTURE.md`, 기능 대응은
[기능 보존 지도](refactor-feature-preservation.md)를 따른다.

## 출발 기준과 현재 상태

출발 commit은 PR #307의 `5b7ce1c6954eccfda7448262298051931c742df2`이다.
기능 원장의 K01~K24와 G01~G13 총 37항목, 원래 source/checkpoint/assertion을 유지한다.
선행 backend/frontend 완료와 간략한 사용자 설치 확인은 이번 최종 통합 검증과 구분한다.

AR-X0 기준 확인은 통과했다. AR-X1-A는 PR #308로 병합했고 merge
`9040ad3bb4a6f787a2c4f1d542d106b22e26f4ef`의 7개 후속 workflow까지 통과했다.
AR-X1-B는 PR #310의 7개 workflow를 통과해 merge
`779a5b2dd208b3db6ac16e221c645083ea58a63e`로 병합했고 후속 7개 workflow도 통과했다.
AR-X1-C는 PR #311의 7개 workflow를 통과해 merge
`e23380e0a289d0eb8ecd1255614e2d9e102cee0b`로 병합했고 후속 7개 workflow도 통과했다.
AR-X1-D는 PR #312의 수정 head `bfdc466965573f758a1c6a8cc129d6461a1f11f0`의
7개 workflow를 통과해 merge `6032a02cf72f509bd351e868f7f5a0998d86a7bf`로 병합했다.
그 merge의 후속 7개 workflow도 통과했다. AR-X1-E는 PR #313 head
`0ecb6f6834ef3fdc174cb48bce7bf32b20e8354b`의 7개 workflow를 통과해
merge `f07dc8d3ebb4b619159c7a9e14775d2962043e61`로 병합했다.
통합 후보는 그 실제 merge를 기준으로 한다. 최종 PR과 동일 merge의
후속 CI·설치·실행 영수증은 아래 종료 근거에서 확인한다.
최종 merge의 CI·설치 산출물·실행 파일을 확인하기 전 전체 완료로 판정하지 않는다.

출발판의 구조·디자인·frontend 보존 및 backend 계약/테스트 노드 보존 검사를 통과했다.
보호 대상과 현재 수집은 각각 2761 nodes이며 행위 테스트 실행과 구분한다.
브라우저 수집은 기본 21, 설정 2, static 68, lifecycle 2, visual 36개다.
이는 수집 결과이며 최종 후보에서 실제 실행할 대상이다.

## 역할 정리

| 단계 | 변경 | 보존할 동작 | 상태 |
| --- | --- | --- | --- |
| AR-X1-A | Identity 가입 대기를 `stores/pending-signup.ts`로 이동 | 저장 키·이메일/만료 파싱·캐시 제거·인증 이벤트와 직접 소비자 | COMPLETE · #308 병합 · post-merge 7/7 PASS |
| AR-X1-B | Characters 상태 저장 중복 통합 | 저장/이벤트 계약·첫 안내·단일/전체 조회 | COMPLETE · #310 병합 · post-merge 7/7 PASS |
| AR-X1-C | World Package 브라우저 전달 위치 | 다운로드·파일명·Blob URL 수명·native 분기 | COMPLETE · #311 병합 · post-merge 7/7 PASS |
| AR-X1-D | 공용 DOM/탐색/scroll 역할 | 선택·키보드·카드 탐색·window/container scroll | COMPLETE · #312 병합 · post-merge 7/7 PASS |
| AR-X1-E | 공용 HTTP와 기능 오류 표시 분리 | 동일 응답의 문구·파싱·401·FormData | #313 head 7/7 PASS · 병합 · 후속 결과는 해당 PR 참조 |

검증 명령, 후보와 merge SHA, 실행 경로, 실제 결과 및 제한을 단계별로 연결한다.
UI fixture·실제 API·fake provider·native·설치 검증은 각각의 범위로 기록한다.
실제 AI 품질과 P8-L-S, Release/Production은 이 구조 검증의 완료 범위에 포함하지 않는다.

## 통합 과정에서 분리한 Hotfix

PR #308의 첫 backend CI는 동시 활성화의 정원 거절 로그가 SQLite 잠금을 처리하지
못하는 기존 문제를 검출했다. 별도 PR #309가 동일 bounded writer와 retryable 오류를
적용했으며, 기존 파일의 추가 assertion 원문을 도입 commit에서 읽는 검사기 보완도
포함한다. Merge `b648587225114ae86553381556be42e017d87f62`의 7개 후속 workflow가
모두 통과했다. 원래 실패 이력과 후속 성공을 구분하며 source/checkpoint를 교체하지 않았다.

## Characters 상태 통합의 검증 위치

`frontend/scripts/test-character-state-parity.mjs`는 통합 이전 두 모듈과 현재 한 모듈을
같은 저장값으로 비교한다. 잘못된 JSON·빈 값·혼합 상태, 이벤트 순서와 payload,
Agent/Character 호출자 사이의 온보딩과 자율활동 상태 공유, 마지막 key 삭제,
브라우저가 없는 환경의 no-op을 확인한다. 기존 45개 API 요청 비교는 별도로 유지한다.
대시보드 이름의 export는 실제 같은 함수를 가리키며 별도 저장 구현이 아니다.

## World Package 브라우저 전달 위치

`utils/browser-delivery.ts`의 본문은 바꾸지 않고 `api/browser-delivery.ts`로 이동했다.
내보내기 화면이 실제 I/O 파일을 직접 사용하며 native 저장 분기는 그대로다.
고정 source `b648587225114ae86553381556be42e017d87f62`와 현재 함수를 각각 실행해
동일 Blob·한글 파일명·anchor 추가/클릭/제거·timer 0 예약·지연 URL 해제 trace를 비교한다.
기존 proxy·브라우저·static 검사를 유지하며 시각 기준을 새로 승인하지 않는다.

## 공용 DOM·카드 탐색 도구

`post-card-navigation.ts`는 `lib/navigation`, `scroll-viewport.ts`는 `lib/dom`이 소유한다.
두 파일의 본문은 그대로 유지한다. React hook과 화면/기능 소비자는 이 실제 파일을
직접 사용한다. 기존 Tauri shell 테스트의 파일 읽기 경로만 대응표대로 변경한다.
원래 hosted 출처·분류와 시각 기준을 유지하며, 현재 경로와 import 변경의 소스 해시만
디자인 보고서에 반영한다. 실제 선택·키보드·scroll owner·pagination·pull-to-refresh는
기존 static Playwright에서 계속 검증한다.

PR #312의 첫 CI는 L4 소유권 목록에서 이동한 scroll import와 source hash가 오래된
것을 검출했다. 생성 도구로 그 두 값을 갱신한 뒤 새 head의 전체 7개 workflow가
통과했다. 기준선이나 기존 단언을 바꿔 최초 실패를 지우지 않았다.

## 공용 전송과 기능별 오류 문구

공용 `lib/http/api-request.ts`는 전송·파싱·세션 처리를 맡고, Identity·Characters·
Social의 `api/request.ts`는 각 API가 기존에 수용하던 검증 문구를 해석한다.
전송 옵션에 함수를 섞어 fetch로 보내지 않으며 별도의 인자로 해석기를 전달한다.
기능 간 import나 공용 코드에서 기능으로 향하는 import는 추가하지 않는다.

기존 혼합 field 응답의 문구와 우선순위도 유지한다. 오류 소유권을 정리한다는 이유로
Identity의 기존 활동 간격 오류 응답 같은 동작을 삭제하지 않는다. 작은 호환 해석기의
수정 책임은 각 기능에 있으며 모든 새 기능에 동일 파일을 생성하는 규칙은 아니다.
`test-feature-error-parity.mjs`가 고정된 이전 소스와 세 실제 API 소비자를 같은 22개
응답으로 비교한다. 기존 endpoint·FormData·401·세션 비교와 CI도 계속 수행한다.

## 통합 후보의 구조와 검증

AR-X2는 현재 37항목의 소유 경로와 설명을 맞춘다. 이전 상태 문구는 원장의
`ar_x_precloseout_snapshot`에 보존한다. `MOVED`는 실제 역할 이동이며 최종
설치·실행 승인과 다르다. 기존 Device Home 파일럿의 `VERIFIED`는 당시 범위다.

- backend 완료 모드와 정확한 38개 bridge·20개 retained module을 유지한다.
  역사 migration과 외부 Hosted 확장 2개는 [소비 계약](backend-compatibility.md)을
  제공하며 제거 기한을 임의로 만들지 않는다. 활성 `public_main.py` 구현은 없다.
- 두 백엔드 docstring의 옛 계층 설명만 실제 service·session factory 역할에 맞춘다.
  실행 AST는 동일하며 DB schema·migration·lock·시각 기준을 변경하지 않는다.
- `src/testing`은 선택 사항이다. 실제 공통 helper가 없으면 빈 폴더를 추가하지 않는다.
  임시 소스 후보가 없으며 사용 중인 worktree·가상환경·검증 자료·설치 데이터와
  Docker volume은 삭제 대상으로 취급하지 않는다.

AR-X3의 [시나리오 지도](refactor-integration-scenarios.md)는 S01~S10과 K/G의
행위·실행 경로를 연결한다. 64자 v8 generation의 채워진 Memory 행·근거·설정을
v9로 업그레이드하고 재실행하거나 허용되지 않은 변경을 거절하는 회귀를 추가한다.
원래 테스트·assertion·skip 이유·snapshot은 그대로 유지한다.

Core CI는 backend 및 브라우저 5개 설정의 JUnit과 실제 checkout SHA/tree,
source SHA, 도구 버전·lock hash를 함께 보관한다. baseline #258의 1867개 node
(1845 PASS·22 기존 SKIP)를 현재 경로에 대응시킨 결과와 최초 도입 원장의 추가
회귀를 구분한다. 단순 수집 수나 파일 존재 여부를 행위 PASS로 취급하지 않는다.

## 종료 근거와 다음 단계

[최종 통합 PR #314](https://github.com/angmoo-tree/angmoo/pull/314)의 본문과
같은 merge의 Actions가 후보/병합/산출물 근거다.
PR head와 임시 merge checkout, 실제 main merge를 구분하고 설치 payload의
SOURCE_SHA·hash·프로세스 경로를 연결한다. 제품 코드에 자기 merge SHA를 다시
커밋하는 순환 대신 workspace의 09-07 §8.4 종료 기록에 실제 실행 영수증을 남긴다.

상태는 `CI`, `DELEGATED CHECK`, `USER CHECK`로 구분한다. 최종 판정은 필수
workflow 완료와 동일 merge의 지원 경로·설치 확인을 모두 충족해야 한다.
P8-L-S 실제 AI 품질·인과 검증과 Release/Production은 후속 별도 단계다.

### 통합 후보의 검출·보완 이력

첫 통합 후보의 Windows 전체 backend는 2742 PASS·22 기존 SKIP와 3 FAIL이었다.
2건은 Memory repository 설명 수정 후 현재 PostgreSQL 사용 목록의 source hash가
오래된 것을 검출했다. 생성기로 그 한 값을 갱신했고 기존 inventory 8개 검사를
통과했다. 나머지는 Core 보고서 업로드에 기존 CI 업로드 정책이 적용된 결과다.
같은 제한은 PR #314의 최초 Security workflow `34127752377`에서도 검출됐다.

Core 보고서는 backend의 JUnit/identity 2개와 browser의 JUnit 5개/identity 1개만
정확한 파일명으로 제한한다. 전체 디렉터리·wildcard·동적 경로·다른 job/workflow·
unpinned action·추가 upload 옵션은 허용하지 않는다. 기존 secret 참조 금지와
read-only 권한, Installer의 private-artifact 거절 정책도 유지한다. 이 범위의
허용/거절 16개 회귀와 기존 CI 정책 4개 검사가 통과했다.

이 보완 후 새 후보에서 필수 CI와 보존/전체 비교를 확인한다. 최초 실패를
후속 성공으로 덮거나 역사 source/assertion을 재생성하지 않는다.

### 실제 실행에서 발견한 migration 진단 기준 보완

PR #314 merge의 Docker와 Windows Host 화면에서 DB는 현재 SQLite v9로 정상
열렸지만 runtime 진단이 과거 revision 0083을 head로 비교해 제한 상태를 표시했다.
실제 DB revision·SQLite manifest·Alembic head는 모두 `20260904_0089`였다.
진단 상수를 현재 head에 맞추고, 새 DB를 실제로 열어 진단하는 회귀를 추가했다.
과거 및 미래 revision을 제한하는 판정은 그대로 유지한다.

기존 진단 테스트는 같은 상수를 fixture에 사용하므로 상수 자체의 노후화를
검출하지 못했다. 새 검사는 manifest와 Alembic graph를 독립적으로 대조한다.
수정 전 새 4개 검사가 실패했고, 수정 후 기존 진단 검사와 합쳐 12개가 통과했다.
K12·G06·G13 보존 원장에 연결하며 필수 Core CI의 전체 backend 실행에 포함한다.
DB 데이터·migration 본문·공개/권한 정책을 변경하는 수정은 아니다.
