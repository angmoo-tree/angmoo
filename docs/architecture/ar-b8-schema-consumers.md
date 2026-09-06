# AR-B8 스키마 소비자 전환과 남은 호환 검사

기준 source는 `9c14b6095b972bbbb1f02473725ea7a7983e7d6c`이다. 이 전환은 실제 스키마 정의와 응답 계약을 바꾸지 않고, 소비자가 업무 소유 파일을 직접 참조하도록 연결한다. 전체 `app/schemas` 삭제는 아직 완료하지 않았다.

## 실제 소비자와 export 근거

- 기존 스키마 모듈 10개의 명시 import 390개가 실제 소유 위치의 동일 객체임을 전환 전에 확인했다. 여기에는 업무 export와 함께 원래 모듈에 노출된 보조 import가 포함된다. `world_character_setup`은 기존부터 실제 setup 모듈 자체를 가리키는 alias였으며 별도로 동일 모듈임을 확인했다.
- 제품 코드 8개 파일의 활성 참조 73개와 미사용 import 2개를 정리했다. 호환 파일 내부 참조도 실제 소유자로 연결했다. 전체 소비자 수정은 테스트 및 호환 파일을 포함해 46개 파일, 명시 참조 471개다.
- 제품의 최상위 함수·클래스 147개는 각 import를 실제 이름으로 해석했을 때 원문 전체 AST가 같다. 조건·호출 순서·Session·provider·반환 표현을 수정하지 않았다.
- 원래 export별 실제 목적지, 각 소비자의 원본 위치, 남은 검사와 Literal 관찰은 `security/refactor_path_map.json`의 `AR-B8-SCHEMA-CONSUMERS`에 기록한다. 원본 source·test baseline, checkpoint, additions는 수정하지 않는다.

| 제거한 호환 파일 | 실제 소유 위치 |
| --- | --- |
| `app/schemas/worlds.py` | `app/domains/worlds/schemas.py` |
| `app/schemas/social_memory.py` | `app/domains/relationships/schemas.py` |
| `app/schemas/world_activity_runtime.py` | `app/domains/routines/schemas/plans.py` |
| `app/schemas/world_character_setup.py` | `app/domains/world_characters/schemas/setup.py` |

## 원문 그대로 남긴 검사

다음 일곱 파일의 호환성 검사는 실제 옛 import 경로를 비교 대상으로 사용한다. 이 전환에서는 해당 파일을 수정하지 않았다. 남은 여섯 호환 파일의 최종 제거는 이 검사들의 목적과 실제 지원 계약을 별도로 검토한 뒤 진행한다.

| 테스트 파일 | 남은 검사 대상 |
| --- | --- |
| `tests/characters/test_character_foundation.py` | 원래 aggregate·agents·characters·media export의 class/function identity |
| `tests/characters/test_character_http_workflows.py` | 두 앱 factory의 workflow 연결과 원래 aggregate 응답 identity |
| `tests/identity/test_l1_identity_domain_foundation.py` | 원래 aggregate·auth와 Identity class identity |
| `tests/identity/test_l1_identity_architecture.py` | 원래 schema 모듈의 존재와 안쪽으로 향하는 정확 import 집합 |
| `tests/test_p8_l_b_chat_domain.py` | importlib로 읽은 원래 messages export identity |
| `tests/test_p8_l_b_chat_domain_inventory.py` | 원래 messages의 전체 승인 export와 실제 Chat class identity |
| `tests/world_characters/test_readiness_contract.py` | 원래 agents readiness 응답과 Character 응답 identity |

옛 경로 import를 canonical import로 바꾸면서 동일한 표현만 남기면 일부 검사는 자기 자신을 비교하게 된다. 이 작업에서는 그렇게 바꾸지 않았고, 해당 호환 export와 정확한 inward bridge만 유지했다. 제품과 일반 테스트의 신규 호출은 이 경로를 사용하지 않는다.

## 원래 Literal 별칭 다섯 개

`app/schemas/agents.py`의 `AgentGoogleModel`, `GoogleGeminiModel`, `ImageKeyMode`, `WritingRepetitionLevel`, `AgentExecutionMode` 대입 본문을 그대로 유지했다. 현재 제품·테스트에 이 원래 다섯 이름의 직접 소비자는 없다. Character 또는 Routines의 실제 스키마에는 이미 같은 값을 표현하는 별칭이 있으나, 이 사실만으로 원래 export가 같은 객체라고 판단하지 않는다.

전환 전 같은 Python 프로세스에서 비교한 다섯 값은 모두 동등했다. `WritingRepetitionLevel`은 그 실행에서 실제 Routines 값과 `is` 비교가 거짓이었다. 나머지 네 비교는 그 실행에서 참이었지만 import 순서와 typing 내부 캐시를 일반적인 동일성 보장으로 취급하지 않는다. 최종 정리에서는 원문 별칭의 보존 위치를 정하거나, 지원 중인 소비자가 없다는 근거로 export를 종료하는 결정을 별도로 남겨야 한다. 응답 JSON schema나 enum 순서를 바꾸는 근거로 사용하지 않는다.

## 기존 source 검사의 연결 보완

첫 집중 실행에서 `test_public_runtime_source_has_no_hosted_saved_count_quota_contract`가 이미 C32에서 삭제한 `app/cruds/community.py`를 읽어 실패했다. 기준 source에도 같은 삭제 경로가 남아 있었고, 스키마 전환 자체는 이 테스트의 import 한 줄만 바꾼 상태였다.

이 검사는 단순히 옛 파일이 존재하는지를 검사하는 대신, 원래 Community의 함수·상수·class가 실제 이동한 전체 24개 source 파일을 읽도록 연결했다. 목적지 집합은 기존 모든 `split_symbols`와 transitive file map에 근거하며 그 근거를 이번 단계 지도에 함께 남겼다. 원래 저장 개수 제한 금지 문자열과 assertion은 전부 유지했다. Character 생성·상태와 Social 저장 등의 전체 실제 본문이 검사 대상이며, 비어 있는 façade로 통과시키지 않는다.

## 검증 상태

최종 집중 결과는 **498 passed / 19 skipped / 56.22초**다. 공개 테스트 기준 **604개 전체 보존**, 현재 public profile **2,509개 수집**을 확인했다. 신규 node는 없다. 최초 집중 결과는 **497 passed / 19 skipped / 1 failed**였고, 위 삭제 경로를 실제 전체 source로 연결한 뒤 해당 파일의 **3개 테스트가 통과**했다. Skip 19개는 기존 조건이며 이 작업에서 추가하지 않았다. 첫 보존 검사에서 PR258/263의 API·JSON schema·ORM 계약, 변경된 보호 테스트 37개 파일의 assertion, 기존 전체 split 증거가 모두 통과했다.

기준 source에는 `app.cruds.agents`와 `app.services.agent_runs`의 미등록 legacy 소비자 진단 13개가 이미 있었다. 이번 변경 뒤의 진단도 동일한 13개이며 새 진단은 없다. 이 두 잔여 모듈은 부모의 별도 B8 실제 소비자/호환 종료 범위이고, 이번 단계에서 이들을 위한 ORM 예외를 추가하지 않는다. 스키마 전환으로 종료한 옛 정확 edge는 16개, 제거한 호환 bridge는 4개다. 남은 실제 역사 검사에 필요한 canonical schema import 일곱 개만 정확히 등록했다.
