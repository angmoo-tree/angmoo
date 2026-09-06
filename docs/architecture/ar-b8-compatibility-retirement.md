# AR-B8 호환 집합 종료와 원래 객체 계약의 보존

요청·응답 스키마와 서비스를 찾을 때 실제 업무가 소유한 `schemas`, `contracts`, `models`, `service`를 사용한다. 이 단계에서는 제품 소비자가 이미 전환된 import-only 집합 16개를 제거했다. 새 전달 서비스나 옛 이름을 흉내 내는 Python 모듈을 만들지 않았다. 앞서 제거된 Daily Plan 집합 1개의 역사적 구조 검사까지 포함해, 원래 소스 입력 17개를 검증한다.

| 제거 범위 | 현재 실제 소유자 |
| --- | --- |
| `app.schemas`와 agents/auth/characters/messages/media_security 6개 | 각 업무의 실제 schema와 Character·Routines constants |
| `services.messages`와 `runtime.chat.sqlalchemy_service` | Chat의 실제 서비스와 `runtime.chat.message_composition`의 원래 서비스 인스턴스 |
| `services.prompt_safety` | 기존 공통 prompt 안전성 구현 |
| `services.world_character_provider` | WorldCharacter client와 setup 계약 |
| `services.profile_media` | 실제 Media 저장·정제·경로 구현 |
| Characters·Identity·Routines·WorldCharacter·Worlds의 public 5개 | 각 원래 export가 가리킨 실제 역할 모듈 |
| 앞서 제거된 `services.daily_activity_plans`의 구조 검사 | 실제 Routines 계획·실행 서비스와 원래 순수 import 본문 증거 |

다른 업무의 ORM이나 repository를 직접 사용하는 규칙으로 변경한 것은 아니다. 기존 업무 간 협력은 typed 계약과 같은 Session을 사용하는 runtime 조립으로 연결한다. 별도 Hosted 확장이 실제 사용하는 두 registry import 계약과 Chat forwarding 종료는 다른 source 범위이며, 이 단계의 완료와 구분한다.

## 무엇을 같은 것으로 확인하는가

원래 입력은 signed source `e565834291dc901ab1826979644d81cc643f9dfd`의 Git blob이다. 이미 삭제된 Daily Plan 파일만 signed `9c14b6095b972bbbb1f02473725ea7a7983e7d6c`에서 읽는다. 현재 후보에 이 두 commit이 실제 선행하는지 확인하고, Python 본문은 AST로만 읽는다. 과거 코드를 실행하거나 과거 모듈을 import하지 않는다.

17개 원문에는 802개 명시 binding이 있다. 이 수치는 원래 `from __future__ import annotations`가 노출한 세 binding도 포함한다. public 다섯 개의 binding은 165개다. `__all__`에 없는 원래 보조 export를 임의로 버리지 않으며, 원래 `__all__`의 대입과 추가 대입 순서도 보존한다. import·단순 alias를 재귀적으로 따라가서 실제 defining owner를 찾고, 파일 지도와 전체 export 지도를 함께 기록한다.

현재 실제 class·함수·상수·service receiver의 존재와 정의를 확인한다. class는 동일 객체여야 하며, 모양만 같은 새 class는 통과하지 않는다. Chat bound method는 접근할 때마다 다른 method 객체가 생길 수 있으므로 `__self__`와 `__func__`가 모두 같은지 확인한다. 같은 이름의 임의 wrapper나 다른 receiver로 교체할 수 없다. 원래 Literal 다섯 값은 앞선 constants 이전에서 대입 본문과 값 순서를 보존했으며 여기서도 그 실제 정의를 검사한다.

## 기존 테스트의 목적을 유지하는 방법

호환 경로가 살아 있는지 확인하던 기존 22개 함수만 닫힌 목록으로 지정했다. 이 목록 밖의 테스트는 일반 원본 단언 검사를 그대로 사용한다. 목록 안에서도 signed 원래 함수 전체 AST에 정확한 import·객체 binding 변환만 적용한 결과와 현재 함수를 비교한다. 오류 조건·Session 쓰기·provider monkeypatch·응답 필드·시간 경계·기존 fixture와 호출 순서는 그대로 남는다.

옛 객체를 자신과 비교하는 단언으로 바꾸지 않는다. 원래 Git binding이 가리켰던 실제 객체와 현재 비교 대상을 확인하고, 옛 파일·package가 실제로 없어야 통과한다. Daily Plan과 L3의 순수 public 구조 검사도 원래 금지 import와 함수 부재 검사를 signed 본문에 유지하며, 현재 실제 전체 export와 파일 부재 검사를 함께 수행한다. 테스트 지원 파일은 정확한 검증 함수를 불러오는 작은 bootstrap이며 가짜 앱 namespace를 만들지 않는다.

음성 회귀는 단언 삭제·항상 참·자기 비교·잘못된 import·provider fixture 변경·다른 receiver·copied schema·조건부 import shadow·예외와 pattern binding·predicate 코드 mutation을 거절한다. 정적·상대·명시적 동적 import와 importer alias, 퇴역 package 하위 소비자 및 중첩 Python 파일 재도입도 거절한다. 임의 Python 실행을 판정하는 일반 도구를 표방하지 않으며, 이번 닫힌 source·export·22개 함수의 변환을 검증한다.

## 지도와 검사 상태

원래 source/test baseline·checkpoint·additions·동결 자료는 변경하지 않았다. `security/refactor_path_map.json`에는 실제 17개 파일 목적지, 802개 binding, 기존 split의 현재 직접 소비자와 정확한 검증 근거를 기록한다. 앞선 파일럿의 동결 증거는 유지한다. 더 이상 존재하지 않는 75개 임시 bridge를 제거했고 새 경계 예외는 추가하지 않았다.

기존 22개 보호 함수가 속한 실제 기능 파일과 음성 검사를 함께 실행한 영향 회귀는 **194 passed / 4 warnings / 43.34초**다. 이후 읽기 검토에서 class body와 decorator/default 실행에 의한 proof binding 변경 가능성을 추가로 차단했으며, 최종 엄격 회귀 **53 passed / 20.13초**에서 모든 기존 22개 함수의 정확한 AST 검증까지 다시 통과했다. 경계 검사는 **1,074 modules / 3,986 edges / 기존 exact legacy 5 / PASS**이며 현재 정적·상대·명시 동적·alias import 소비자는 0이다.

원본 전체 source·split·보호 assertion·suppression 읽기 진단은 모두 **오류 0**, PR #258/#263의 **API·JSON schema·ORM 계약 PASS**다. 최초 검사에서는 신규 테스트의 future binding 개수와 미공개 export 가정을 정정했고, 재생성이 필요한 current inventory 및 실제 Routines `__all__` 추가 대입의 원래 형태를 검증에 반영했다. 원래 기능 단언이나 제품 구현을 바꿔 이 문제를 통과시키지 않았다. 최종 source에는 새 보호 회귀 node 53개가 있다.

최초 도입 snapshot append, 선형 stock 검사, 전체 backend, Hosted CI, 설치 및 post-merge 검증은 부모 통합 단계의 별도 Gate다. 이 문서의 호환 종료 완료가 전체 8.2 완료를 뜻하지 않는다.
