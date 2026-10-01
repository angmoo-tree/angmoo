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

V1/V2와 V3 공통 설정을 지원한다. V3 전용 에셋·확장 실행은 지원하지 않는다. PNG의 전체 chunk·CRC·텍스트 누적량·종료를 확인한 다음, 대소문자를 정규화한 `ccv3`의 물리적 첫 항목을 우선한다. `ccv3`가 없으면 `chara`의 첫 항목을 선택한다. 같은 키의 중복 자체는 오류가 아니다. 선택한 정의가 손상됐거나 버전·공통 필드 검증에 실패하면 같은 키의 다음 정의나 다른 키로 대체하지 않는다. 최신 설정을 추정하거나 여러 정의를 병합하지 않는다.

| PNG 정의 | 선택 | 기본 중복 안내 |
| --- | --- | --- |
| chara A, chara B | A | 표시 |
| ccv3 C, ccv3 D | C | 표시 |
| chara A, ccv3 C | C | 없음: 서로 다른 키 한 개씩 |
| chara A, chara B, ccv3 C, ccv3 D | C | 표시 |

선택하지 않은 정의의 Base64·JSON은 실행하거나 검증하지 않지만, 해당 chunk도 CRC·텍스트·chunk 누적 한도 검사에 포함한다. 잘못된 PNG CRC/base64/선택된 JSON, JSON 중복 key·비유한 수, 초과 크기·깊이·노드·픽셀은 계속 거부한다. JSON 객체 안의 같은 key 중복과 PNG 안의 같은 카드 keyword 반복은 다른 계약이다.

한도: 파일 20MiB, JSON 2MiB, 개별 PNG 텍스트 3MiB/전체 6MiB, PNG chunk 4096개, JSON 깊이 32/노드 50000개, 이미지 16MP/한 변 8192. 미디어 표시본은 기존 WebP codec으로 다시 저장하여 메타데이터를 제거한다.

브라우저 카드 업로드는 PNG/JSON을 Base64로 감싼 JSON 요청으로 보낸다. 파일 20MiB 상한과 별개로 업로드 **요청 본문**은 Next 중계 서버와 백엔드에서 모두 `28_262_144`바이트 이하로 제한한다. 일반 API의 1MiB 본문 상한은 카드 업로드 경로에 적용하지 않는다. 백엔드의 `data_base64` 필드는 최대 `28_000_000`문자이며, 전송을 통과한 파일도 위 형식·크기 검증을 거친다. 정적/Tauri 실행에는 Next 중계 서버가 없지만 백엔드의 동일한 카드 요청·파일 상한이 적용된다.

이 계약은 실제 Next 중계 경로의 상한·413 거절 테스트와 격리된 contributor backend를 이용한 원본 카드 업로드 검증으로 확인한다. 기존 UI 모의 응답 테스트와 실제 서버 업로드 증거는 구별한다.

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

가져온 PNG는 중복 정의와 기타 메타데이터를 포함한 전체 bytes로 보관한다. 표시용 WebP와 원본은 별개이며, 사용자 편집·등록 때문에 원본 PNG를 다시 작성하지 않는다. 새 가져오기의 parser provenance는 `angmoo-card-import-v2`이고 기존 저장 원본의 provenance는 조회만으로 변경하지 않는다.

import 응답과 private `card-source` 조회는 선택 정책 `sillytavern-first-match-v1`, 선택 keyword·0부터 시작하는 occurrence·동일 key 개수·중복 여부·선택 JSON bytes SHA-256을 `metadata_selection`으로 제공한다. 전체 원본의 SHA-256과 선택 JSON SHA-256은 구분한다. JSON 파일에는 이 요약이 `null`이다. 기본 조회는 선택된 한 정의의 `document`를 반환하며 `?include_document=false`는 `document=null`과 요약·검토 항목만 반환한다. 두 조회 모두 `Cache-Control: private, no-store`와 `X-Content-Type-Options: nosniff`를 사용하고 기존 Next 중계도 이 헤더를 전달한다. 공개 Character DTO에는 원본이나 선택 정보가 포함되지 않는다.

같은 keyword의 정의가 여러 개면 생성 화면에 추가 승인 없는 안내를 기본 노출한다. 새로고침에서는 요약만 조회하고, 실패하면 편집 내용 유지와 ‘카드 정보 다시 불러오기’를 제공한다. 원문 조회는 ‘원문 보기’ 요청에만 수행한다. 원문 보기는 선택된 JSON이며, 전체 PNG의 모든 정의를 보여주거나 최종 편집값을 원본으로 교체하지 않는다. 기존의 카드 교체 확인·취소, 대상 World 분리와 늦은 응답 차단을 유지한다.

잘못된 카드의 422 안내는 안전한 형식·크기·손상·버전 메시지로 구분한다. 소유자가 아닌 조회는 404, revision/완료 충돌은 409, 만료된 초안의 카드 가져오기는 410이다. 실패한 가져오기는 이전 초안과 원본을 보존하고 commit 또는 표시 이미지 쓰기 실패 시 이번 시도에서 만든 파일만 정리한다.

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
