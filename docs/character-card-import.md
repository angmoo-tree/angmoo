# 로컬 World·캐릭터·내 프로필 등록 계약

2026-09-27 제품 변경. 기존 World/Character/WorldCharacter/Chat/SNS 서비스를 확장한다.
별도 캐릭터 실행 엔진이나 카드 전용 활동 경로를 만들지 않는다.

## 데이터와 소유권

- `OwnerDefaultWorld`는 설치 소유자와 기본 공간의 영속 결합이다. 유효한 고정 Global만 승계하고, 그 밖에는 `SNS`를 생성한다. 이름을 검색하여 기존 World를 임의 승계하지 않는다.
- `AgentCreationDraft.contract_version=2`는 대상 World, revision, 편집 상태와 7일 만료를 가진다. 키·모델 연결이나 AI 실행은 등록의 선행 조건이 아니다.
- runtime `characters/registration.py`가 Character, WorldCharacter, 단일 소속 binding, 활성 포인터, OFF 설정, 등록 영수증을 동일 Session에서 원자적으로 저장한다. 재전송은 같은 영수증을 읽는다.
- `CharacterWorldBinding`은 신규 등록에 적용한다. 기존 무소속/다중 소속 자료를 자동 재배치하지 않는다. 다른 World에 추가하려면 설정을 복사하여 새 ID로 등록한다. 같은 World의 기존 인물 선택은 기존 프로필로 이동한다.
- `my-profile/ensure`는 World마다 현재 사용자 인물을 재사용한다. 신규 기본값은 사용자/자동 핸들/빈 소개/이미지 없음이다. 보존 인물만 있다면 사용자가 선택해야 한다.
- 내 프로필 PATCH는 이름·핸들·소개·아바타·배너만 수정하고 Character/WorldCharacter ID, 게시글·대화·관계, 기존 상세 설정을 보존한다. version 충돌은 재조회 후 명시적으로 처리한다.

## 캐릭터 카드

PNG 그림을 AI로 해석하지 않는다. PNG `tEXt`의 base64 JSON 또는 JSON 파일을 읽는다. 독립 구현이며 다음 공개 규약의 교환 의미를 따른다.

- [SillyTavern 공식 카드 파서](https://github.com/SillyTavern/SillyTavern/blob/release/src/character-card-parser.js)
- [Character Card V2 규격](https://github.com/malfoyslastname/character-card-spec-v2)
- [Character Card V3 규격](https://github.com/kwaroran/character-card-spec-v3)

V1/V2와 V3 공통 설정을 지원한다. V3 전용 에셋·확장 실행은 지원하지 않는다. PNG에서 ccv3가 있으면 우선하며, 손상된 ccv3에서 chara로 조용히 되돌아가지 않는다. 같은 키 중복, 잘못된 CRC/base64/JSON, 초과 크기·깊이·픽셀은 거부한다.

한도: 파일 20MiB, JSON 2MiB, 개별 PNG 텍스트 3MiB/전체 6MiB, PNG chunk 4096개, JSON 깊이 32/노드 50000개, 이미지 16MP/한 변 8192. 미디어 표시본은 기존 WebP codec으로 다시 저장하여 메타데이터를 제거한다.

| 원본 | 편집 입력 |
| --- | --- |
| name | 이름 |
| personality | 성격; 비어 있으면 description을 읽고 사용자가 보완 |
| description | 캐릭터 배경·설정 |
| mes_example | 말투·대화 예시 |
| scenario | 수동 검토 안내; 자동 경험/기억으로 저장하지 않음 |
| first_mes, alternate_greetings, lorebook, system/post-history instructions, extensions | 원본 전용, 자동 프롬프트 주입 없음 |

`{{char}}`와 V3 제한된 이름 표기만 치환한다. 예시의 `{{user}}`는 대화 상대이다. 나머지 동적 문구는 표시하고 검토하도록 한다. 카드에 없는 관심사·소개를 태그/첫 인사로 임의 채우지 않는다. 길이 초과는 원문을 유지하고 사용자 수정으로 해결한다.

`CharacterCardSource.source_bytes`는 private SQLite 데이터다. 원본 조회는 소유자 한정이며 no-store이다. 만료된 미등록 원본은 삭제 대상이지만 등록 원본에는 자동 만료가 없다. 등록 후에는 편집한 Character 필드가 준비·SNS·Chat의 입력 원본이다.

## UI와 실행

홈/World 생성 완료/World 관리에서 같은 기존 생성 가이드를 사용한다. 직접 작성·카드 가져오기·설정 복사 모두 API 키 없이 OFF로 저장한다. 활동 준비에서 모델·키를 지정하고 기존 준비/승인/ON 계약을 따른다. 외부 실행기용 등록도 동일한 소속 저장 경계를 사용한다.

World의 공개/참여·시간대 환경·규칙·용어 입력은 일반 폼에서 제외한다. 수정 요청은 숨긴 필드를 보내지 않는다. 로컬 소유자의 유효한 private World 접근은 허용하며, 다른 소유자 자료·보관된 World는 계속 차단한다. World 아이콘은 Device Home 썸네일이며 배너와 구별한다.

이전 sessionStorage 초안은 “이전 초안 이어가기”로 명시적으로 전환한다. 설정·미디어와 원래 ID를 유지하며, 구 완료 API가 무소속 캐릭터를 만들지 못하게 한다. 키는 등록 캐릭터에 자동 연결하지 않는다. GET은 만료 파일 정리나 상태 변경을 하지 않는다.

‘나중에 하기’는 초안을 보관한다. 명시적인 ‘이 초안 취소’는 확인 후 기존 draft PATCH에 `status=cancelled`와 revision을 보내며, 등록과 같은 조건부 갱신으로 경합을 처리한다. 취소가 먼저 확정되면 미등록 카드 원본을 정리하고 후속 등록을 거부한다. 등록이 먼저 확정되면 completed 상태를 반환하고 캐릭터·원본·영수증을 보존한다. 파일 정리는 취소 DB commit 이후 수행하며, 실패하면 기존 만료 정리에서 다시 처리한다. 대상 World는 취소하지 않는다.

카드 원본·등록 영수증·완료 초안은 기존 캐릭터/계정 삭제 트랜잭션에서 함께 제거한다. 계정 삭제는 기본 공간 binding도 해제한다. 실패 시 DB와 격리한 미디어를 복구하는 기존 계약을 유지한다.

## 패키지와 migration

SQLite v21은 v20 자료를 보존하고 draft credential nullable 및 신규 참조 테이블을 추가한다. 설치된 실제 사용자 DB의 업그레이드는 이 개발 작업에서 실행하지 않는다.

World 패키지는 최종 설정과 로컬 표시 이미지를 포함한다. 원본 카드·키·관계·기억은 포함하지 않는다. 아이콘은 기존 패키지 required-extension 기능의 `angmoo.world-icon.v1`으로 보존한다. 아이콘을 모르는 구 reader가 조용히 손실시키는 대신 unsupported extension으로 거부하도록 한다. 전체 설치 백업은 SQLite의 등록 카드 원본도 포함한다.

## 검증 경계

로컬 단위/회귀, UI mock API, migration, 실제 AI, 실제 사용자 확인을 구별한다. 외부 평가 카드는 저장소에 커밋하지 않고 URL·Git blob·SHA256을 별도 기록한다. 실제 AI는 Gemini 3.1 Flash-Lite, 재시도 포함 60회 상한이다. 브라우저 static shell 통과를 Windows native 배율 USER CHECK로 확대하지 않는다.

## 로컬 검증 기록

확정 3종 카드의 실제 평가는 `backend/scripts/evaluate_creator_cards.py`로 격리 수행했다. 재시도 포함 59/60회이며 세 카드의 최종 활동 준비를 통과했다. 첫 평가에서 profile 출력 한도와 미등록 place ID 오류가 발견되어, 출력 한도 4096과 World별 유효 place enum으로 수정했다. 형식 검증을 완화하거나 AI 호출을 추가하지 않았다.

SNS V2 두 합성 시나리오×3카드의 통합 선택/Inbox/Feed/Routine 생성 경계를 확인했다. 실제 스케줄러·기억 검색·게시·그래프 쓰기를 모두 잇는 자연 활동 평가와 구 버전 대비 통계적 품질 평가는 아니다. 사용자 직접 화면 확인과 Windows native 배율 검사는 별도 후속 사항이다. 자세한 실행 기록은 workspace의 `docs/plan/09-27 World·캐릭터·내 프로필과 실리태번 카드 통합 구현·검증 결과.md`를 따른다.
