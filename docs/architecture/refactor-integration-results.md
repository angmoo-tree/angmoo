# 구조 리팩터링 통합 검증

AR-X는 backend와 frontend 전환 이후 남은 역할 정리와 기능·데이터·지원 실행 경로의
통합 검증이다. 구조 설명은 각 `ARCHITECTURE.md`, 기능 대응은
[기능 보존 지도](refactor-feature-preservation.md)를 따른다.

## 출발 기준과 현재 상태

출발 commit은 PR #307의 `5b7ce1c6954eccfda7448262298051931c742df2`이다.
기능 원장의 K01~K24와 G01~G13 총 37항목, 원래 source/checkpoint/assertion을 유지한다.
선행 backend/frontend 완료와 간략한 사용자 설치 확인은 이번 최종 통합 검증과 구분한다.

AR-X0 기준 확인은 통과했고 AR-X1-A 검증 진행 중이다. AR-X1-B~AR-X6는 미완료다.
최종 merge의 CI·설치 산출물·실행 파일을 확인하기 전 전체 완료로 판정하지 않는다.

출발판의 구조·디자인·frontend 보존 및 backend 계약/테스트 노드 보존 검사를 통과했다.
보호 대상과 현재 수집은 각각 2761 nodes이며 행위 테스트 실행과 구분한다.
브라우저 수집은 기본 21, 설정 2, static 68, lifecycle 2, visual 36개다.
이는 수집 결과이며 최종 후보에서 실제 실행할 대상이다.

## 역할 정리

| 단계 | 변경 | 보존할 동작 | 상태 |
| --- | --- | --- | --- |
| AR-X1-A | Identity 가입 대기를 `stores/pending-signup.ts`로 이동 | 저장 키·이메일/만료 파싱·캐시 제거·인증 이벤트와 직접 소비자 | 검증 중 |
| AR-X1-B | Characters 상태 저장 중복 통합 | 저장/이벤트 계약·첫 안내·단일/전체 조회 | 미착수 |
| AR-X1-C | World Package 브라우저 전달 위치 | 다운로드·파일명·Blob URL 수명·native 분기 | 미착수 |
| AR-X1-D | 공용 DOM/탐색/scroll 역할 | 선택·키보드·카드 탐색·window/container scroll | 미착수 |
| AR-X1-E | 공용 HTTP와 기능 오류 표시 분리 | 동일 응답의 문구·파싱·401·FormData | 미착수 |

검증 명령, 후보와 merge SHA, 실행 경로, 실제 결과 및 제한을 단계별로 연결한다.
UI fixture·실제 API·fake provider·native·설치 검증은 각각의 범위로 기록한다.
실제 AI 품질과 P8-L-S, Release/Production은 이 구조 검증의 완료 범위에 포함하지 않는다.
