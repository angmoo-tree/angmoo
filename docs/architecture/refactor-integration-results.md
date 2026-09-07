# 구조 리팩터링 통합 검증

AR-X는 backend와 frontend 전환 이후 남은 역할 정리와 기능·데이터·지원 실행 경로의
통합 검증이다. 구조 설명은 각 `ARCHITECTURE.md`, 기능 대응은
[기능 보존 지도](refactor-feature-preservation.md)를 따른다.

## 출발 기준과 현재 상태

출발 commit은 PR #307의 `5b7ce1c6954eccfda7448262298051931c742df2`이다.
기능 원장의 K01~K24와 G01~G13 총 37항목, 원래 source/checkpoint/assertion을 유지한다.
선행 backend/frontend 완료와 간략한 사용자 설치 확인은 이번 최종 통합 검증과 구분한다.

AR-X0 기준 확인은 통과했다. AR-X1-A는 PR #308로 병합했고 merge의 후속 검증을
확인 중이다. AR-X1-B는 그 merge 위에서 상태 중복을 통합해 검증 중이며,
AR-X1-C~AR-X6는 미완료다. 다음 PR은 앞선 merge의 후속 검증이 끝난 뒤 병합한다.
최종 merge의 CI·설치 산출물·실행 파일을 확인하기 전 전체 완료로 판정하지 않는다.

출발판의 구조·디자인·frontend 보존 및 backend 계약/테스트 노드 보존 검사를 통과했다.
보호 대상과 현재 수집은 각각 2761 nodes이며 행위 테스트 실행과 구분한다.
브라우저 수집은 기본 21, 설정 2, static 68, lifecycle 2, visual 36개다.
이는 수집 결과이며 최종 후보에서 실제 실행할 대상이다.

## 역할 정리

| 단계 | 변경 | 보존할 동작 | 상태 |
| --- | --- | --- | --- |
| AR-X1-A | Identity 가입 대기를 `stores/pending-signup.ts`로 이동 | 저장 키·이메일/만료 파싱·캐시 제거·인증 이벤트와 직접 소비자 | #308 병합 · post-merge 확인 중 |
| AR-X1-B | Characters 상태 저장 중복 통합 | 저장/이벤트 계약·첫 안내·단일/전체 조회 | 구현 · 검증 중 |
| AR-X1-C | World Package 브라우저 전달 위치 | 다운로드·파일명·Blob URL 수명·native 분기 | 미착수 |
| AR-X1-D | 공용 DOM/탐색/scroll 역할 | 선택·키보드·카드 탐색·window/container scroll | 미착수 |
| AR-X1-E | 공용 HTTP와 기능 오류 표시 분리 | 동일 응답의 문구·파싱·401·FormData | 미착수 |

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
