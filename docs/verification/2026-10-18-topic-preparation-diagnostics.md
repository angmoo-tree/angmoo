# 주제 재생성 진단·개수 계약·저장된 활동 키 표시 보완

- 작업 브랜치: `feat/preparation-output-language`
- 시작 커밋: `9c3ff87627242ea5be69086e1967084705dff4bd`
- 범위: 관련 로컬 검증과 로컬 커밋. Publish·PR·CI·main 병합은 수행하지 않는다.
- 실제 Bram 재생성과 AI 호출은 사용자가 실행한다. 실행 중인 Docker 재빌드·재시작과 운영 DB 변경은 수행하지 않았다.

## 구현 계약

### 진단

`topic_preparation_failed` 뒤에 `topic-preparation.v1` JSON을 백엔드 WARNING 로그로 남긴다. 별도 DB 테이블, 관찰 세션, 상시 파일 갱신, 추가 AI 호출은 만들지 않는다.

| 필드 | 의미 |
| --- | --- |
| `request_id`, `world_id`, `world_character_id` | 같은 요청과 소유 범위를 연결하는 식별자 |
| `stage` | `admission`, `input_validation`, `generation`, `output_validation`, `apply`, `failure_record` 중 실패 위치 |
| `code`, `exception_type` | 안전한 오류 분류와 예외 종류 |
| `validation` | 최대 4개 허용 필드 경로·검증 유형. 임의 추가 필드 이름은 `unknown_field`로 표시 |
| `topic_count` | 응답이 목록으로 파싱됐거나 검증을 통과했을 때 확인한 항목 수. 확인 불가하면 null |
| `response` | JSON 형태, 길이, 파싱 여부, 허용된 finish reason. 응답 원문은 제외 |
| `logical_calls`, `sdk_attempts` | 해당 요청의 기존 Direct LLM tracker가 기록한 논리 호출·SDK 시도 수 |
| `call_counts_observed` | 호출을 실제 계측했는지 여부. 주입된 시험용 generator는 false와 null을 사용 |
| `provider_calls`, `elapsed_ms` | 최대 4개 호출 결과·시간·실패 유형·HTTP 상태, 요청 시작부터 실패까지의 시간 |

키·키 지문·암호문·프롬프트·페르소나·생성 주제 원문·임의 예외 메시지·원문 미리보기는 이 새 로그에 포함하지 않는다. 진단 출력 실패가 원래 실패 상태 기록이나 롤백을 방해하지 않는다. 성공 요청에는 실패 로그를 남기지 않는다.

과거 실패 요청의 기록되지 않은 AI 응답은 복구할 수 없다. 이 변경은 다음 실행부터 원인을 분리해 확인하도록 한다.

### 검증과 보존

- 활성 주제 생성 지침, AI 응답 스키마, Pydantic 검증, 적용 직전 개수 검사를 **1~24개**로 맞춘다. 초기 일과와 함께 생성하는 주제도 기존 1~24개 계약을 유지한다.
- 이름 길이·scope·추가 필드 거부·정규화·이름 바인딩·World 소유권·출처 변경·요청 중복·lease 검증을 유지한다. 잘못된 응답을 잘라서 성공 처리하지 않는다.
- JSON 오류의 추가 AI 재시도는 하지 않으며 기존 `sdk_attempts=1`을 유지한다.
- 실패 시 기존 주제 ID·source 링크·과거 게시글 링크를 보존한다. 쓰기 도중 오류도 트랜잭션을 롤백한 뒤 실패 상태를 기록한다.
- 과거 자료 정리용 `replace_source_topics(topics=[])`와 은퇴한 World 자료의 보존 처리는 생성 API의 개수 계약과 구분하여 유지한다.
- AI 호출을 기다리는 동안 DB 트랜잭션을 유지하지 않는다. 진단 때문에 새로운 DB 쓰기를 추가하지 않는다.

### 화면

- “캐릭터 활동 API key 사용”과 영어 “Uses the character activity API key”로 실제 설정 이름을 표시한다.
- 소유권 확인 후 현재 World 캐릭터의 저장된 `sns` credential metadata를 조회한다. 읽기 과정에서 키를 복호화하거나 AI를 호출하지 않는다.
- 저장된 모델·thinking을 표시하며 미저장 상태에는 가짜 기본 모델을 표시하지 않는다. 키가 없으면 한국어·영어 안내를 제공한다.
- 설정에서 아직 저장하지 않은 선택은 반영하지 않는다. 저장 성공 시 주제 목록을 유지하면서 metadata를 다시 읽는다.
- World 캐릭터 화면의 연결 버튼은 같은 화면의 활동 키 설정으로 스크롤하고 포커스를 옮긴다. 기존 상세 화면에서는 지원되는 World 설정 경로로 연결한다.
- 이미 실행 중인 요청은 기존대로 접수 시 확정된 credential snapshot을 사용한다. 현재 설정 표시는 과거 결과의 생성 모델을 뜻하지 않는다.
- 디자인 근거: **LOCAL**. 기존 SettingsCard·Button·토큰과 공용 feature 화면을 재사용하며 Next와 static/Tauri를 별도 구현하지 않는다.

## 관련 검증 결과

- 백엔드 6개 관련 시험 파일: **116 passed (56.61s)**. 생성 경계 1·24개, 0·25개 거부, 잘린 JSON, 필드 오류, HTTP 오류 진단, 저장 롤백, 로그 출력 실패, metadata 읽기, 기존 중복·출처·권한·이름·언어 계약을 확인했다.
- 브라우저: **8 passed (37.9s)**. Next와 실제 static shell 개발 서버에서 각각 한국어·영어 저장된 설정 표시, 설정 이동, 저장 후 갱신, 실패 시 10개 기존 주제 보존, 키 미등록 표시를 확인했다. 모든 API와 provider 응답은 합성 자료다.
- Backend·Frontend 아키텍처 경계, Frontend 디자인 계약, ESLint, TypeScript 타입 검사 통과. 번역 카탈로그도 16개 namespace·2640개 source key의 키·파라미터·복수형 정합성 검사를 통과했다.
- 전체 백엔드·프론트엔드 시험, 실제 Google AI 품질 확인, Windows 설치본·Tauri 네이티브 실행, CI는 수행하지 않았다. static shell 개발 서버 검증은 배포용 정적 빌드 검증과 구분한다.
- 첫 검증에서 발견한 시험용 credential 삭제의 FK 위반, 잘못 지정한 static 시험 진입점·영어 기대 문구는 시험 설정을 수정했다. React refs 검사는 props 분리를 수정하여 해제 지시 없이 통과했다.
- Next 개발 서버가 static shell에 생성한 `AGENTS.md`와 `CLAUDE.md`는 생성된 지침 그대로 보존한다. 시험용 tsconfig 경로·포맷 변경은 원래 내용으로 복구했다.

로컬 자료: `artifacts/topic-preparation-20261018/`의 `backend-tests.txt`, `frontend-lint.txt`, `frontend-typecheck.txt`, `frontend-catalog.txt`, `browser-results.json`, `browser/` 화면 캡처.

## 사용자가 재생성할 때

새 코드를 Docker에 재빌드해 적용한 뒤 활동 API key 설정의 모델·thinking을 확인하고 주제 재생성 버튼을 누른다. 실패했다면 같은 실행 시각의 다음 로그를 조회한다.

```powershell
docker compose -f compose.yml -f compose.dev.yml logs --since 10m backend |
  Select-String 'topic_preparation_failed'
```

표시 상태와 기존 주제 목록, 요청 ID, 실패 단계·검증 유형을 함께 확인한다. HTTP 200만으로 재생성 성공이라고 판정하지 않는다. 성공 판정은 `state=ready`와 새 주제의 적용 결과를 기준으로 한다.
