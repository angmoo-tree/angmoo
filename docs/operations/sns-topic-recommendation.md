# SNS 주제 추천 구현과 로컬 검증

## 상태

2026-09-18 C안 구현. 브랜치 `feat/sns-relationship-context`, 시작 HEAD
`0e667dffbeb8361f9782e842188af7f308a2cce9`.

**로컬 코드·자동 검증과 직접 USER CHECK는 별도다.** C10 사용자 확인은 아직 수행하지 않았다.
이 변경에는 PR, push, 원격 CI, main merge, 설치 앱 업데이트가 포함되지 않는다.

## 구현 경계

- Social이 사전·출처 연결·게시글 연결·전달 기록을 소유한다. World/캐릭터 생성 명령은 주입된
  `on_created` 협력을 같은 트랜잭션에서 호출한다. HTTP 완료 흐름은 runtime에 주입된 준비 기능을 호출한다.
- `runtime/social/topic_preparation.py`가 승인 프로필·World·기존 일과 키를 조합한다.
  `runtime/social/topic_scope.py`가 같은 Session에서 유효 소속·삭제 여부를 검증한다.
  service가 runtime이나 다른 도메인의 ORM을 직접 조합하지 않는다.
- World Creator와 캐릭터 설정은 동일한 Social 주제 패널과 API를 사용한다. feature 간 조립은 composition에 있다.
- `frontend/ARCHITECTURE.md`, `frontend/DESIGN.md`, `backend/ARCHITECTURE.md`를 기준으로
  현재 import inventory를 재생성해 검사했다. 검사 예외는 추가하지 않았다.

## 저장과 전환

- Alembic `20260918_0095` / `20260918_0096`, embedded SQLite v15 / v16.
- 신규 7개 테이블: catalog, topic, source, eligible post, post-topic, preparation, delivery.
- 새 원문 저장 명령만 `social_recommendation_posts` receipt를 만든다. migration/import/edit는
  기존 글에 receipt를 만들지 않는다. 존재 여부가 재시작 후에도 유지되는 추천 자격이다.
- 기존 keyword 모드를 topic 모드로 전환하되 자율 활동 ON/OFF, 승인 프로필, 기존 원문·관계·기억을 보존한다.
- 과거 글 분류, 최근 200개 backfill, 업데이트 시 기존 관심사 초기화는 없다.
- SNS FTS projection의 startup rebuild/commit listener를 시작하지 않는다. 기존 파일을 삭제하지 않는다.
  사용자 검색과 Chat/Memory의 검색 인덱스는 별개다.

## 주제 준비

| 상황 | 실행 |
| --- | --- |
| 새 World | 초안 생성에서 일회 marker 저장 → 최초 공개에서 준비 시도. 키가 없으면 pending 유지 |
| 새 캐릭터 | 새 World 진입 marker → 최초 승인 시 기존 AI 프로필의 키워드·core/adjacent interests 재사용 |
| 기존 자료 | GET/startup/활동 준비로 생성하지 않음. 사용자의 다시 만들기 요청 필요 |
| 명시적 생성/재생성 | 기존 agent-purpose 키, `gemini-3.1-flash-lite`, thinking `high`, 1회 호출 예산 |

신규 캐릭터의 관심 표현은 이미 승인하는 프로필 응답에서 얻는다. 새 비슷한 필드나 추가 분류 호출을 만들지 않았다.
World 키는 편집자가 같은 World의 소유 캐릭터를 명시적으로 선택한다. 새 World에는 선택 가능한 키가
아직 없을 수 있으며, 이 경우 World는 정상 저장되고 이후 버튼으로 주제를 준비한다.

요청별 원본 digest, request ID, 5분 lease를 저장한다. 생성 중에는 쓰기 트랜잭션을 유지하지 않는다.
결과 적용 전에 원본·권한·키 참조·활성 자격 증명과 fingerprint를 다시 확인한다.
중복 요청은 추가 호출하지 않고, 실패·늦은 결과는 이전 정상 연결을 보존한다.
재시작 후 만료된 running은 읽기에서 재실행 가능한 실패 상태로 표시한다. **버튼으로 재시도하며,
자동으로 미준비 자료를 훑거나 과거 요청을 무제한 재호출하지 않는다.**

현재 World 목록 또는 유효 소속 캐릭터 관심사에 연결된 주제만 새 글에 사용한다.
활동 OFF는 관심사를 제거하지 않는다. 탈퇴·비활성 소속·삭제된 캐릭터는 현재 사용 집합에서 제외한다.
마지막 현재 연결이 사라져도 과거 주제 ID/게시글 연결은 보존하고, 재사용하면 같은 ID를 쓴다.

## 게시글 연결

- 게시글 writer에는 사전이나 64개 후보를 주지 않는다.
- AI 글은 제목·본문·유효한 최종 `topic_signature`, 사용자 글은 제목·본문으로 전체 사용 가능 사전을 매칭한다.
- 이름의 NFKC·대소문자·공백 정규화 후 포함 규칙을 사용한다. Trie로 전체 이름을 검사하고 최종 최대 6개만 연결한다.
  더 긴 이름, 입력 필드 순서, 안정적인 ID 순으로 동률을 정한다.
- 사전에 없는 표현은 등록하지 않는다. `풋볼`/`축구` 같은 의미상 동의어 누락은 허용된 한계다.
- 설명이 없거나 형식/300자 제한을 위반하면 정상 본문은 유지하고 원문만 사용한다. metadata 보충 AI는 없다.
- 기존 brief fallback은 기존 이력 소비자용으로 보존하지만, 추천 근거로 인정하는 최종 설명은 별도 receipt에
  본문 digest와 함께 보존한다. Feed에 주는 설명도 이 유효 출처를 사용한다.
- 수정용 `match_post`는 과거 receipt가 없는 글을 승격하지 않으며 이전 설명을 자동 재사용하지 않는다.
  현재 제품에는 일반 게시글 본문 편집 API가 없으므로, 새 편집 화면을 이 작업에서 만들지는 않았다.
- 매칭 캐시는 World 버전·현재 소속·현재 트랜잭션별, Session당 최대 8개다.
  다른 Session에 미커밋 사전을 퍼뜨리지 않는다. 캐릭터별 영구 사전 복제는 없다.

## 추천과 전달

최신 10 → 관심 5 → 관계 3 → 탐색 2, 최대 20개.
부족분은 관심→관계→탐색→최신으로 보충하며 실제 출처를 기록한다.
개인화 추가분에는 작성자당 2개 제한이 있고, 먼저 확보한 최신 10개는 이 제한으로 제거하지 않는다.

초기 수집량은 24/32/16/8이다. 최대 3회, 원시 검토 합계 최대 200개다.
일반 인덱스로 한정된 구간을 읽은 뒤 이미 본 글·차단·자격을 검사한다. 대부분 이미 본 자료에서도
20개를 채우기 위해 전체 이력을 무제한 스캔하지 않는다. 따라서 한도 밖에 다른 미노출 글이 있어도
이번 실행의 결과는 20개 미만일 수 있다. 후보를 제외한 경우 예산 안에서 다시 선정한다.
실행 안에서는 본문·행동 조회를 재사용하고 전달 직전에는 원본을 다시 검증한다.

관계 후보는 현재 팔로우, 최근 30일 직접 성공한 댓글/답글/반응/팔로우를 사용하며 작성자는 최대 16명이다.
단순 노출과 높은 긴장 수치를 관계 교류로 바꾸지 않는다. 탐색은 관심사 교집합이 없거나 주제가 없는 글이다.
노출 작성자의 최근 200개 기록은 다양성 점수에만 사용하며 영구 관심사를 학습하지 않는다.

본문은 글당 1,200자, 전체 18,000자 안에서 전달한다. 최종 배열은 0~19,
planner/writer 전체 프롬프트는 각 64,000자 안전 한도를 둔다. 후보 수와 행동 1회 계약은 별개다.

- 준비/전송/불확실/전달 완료를 구분한다. 응답이 실제로 도착하면 JSON 해석·행동 성공 전에 노출을 확정한다.
- 응답이 잘못되거나 NO_ACTION·행동 실패여도 이미 전달된 글은 다시 추천하지 않는다.
- 키 오류 등 호출 전 실패는 노출이 아니다. 응답 없는 타임아웃은 uncertain이며 재전달 가능성을 숨기지 않는다.
- 실제 전달 후 관찰을 기록하고 관계 snapshot을 새로 만든다. 최종 최대 20명 작성자 관계는 배치 조회한다.
- 최소 영구 노출은 남기고, 자세한 전달 trace는 캐릭터별 최근 200건/30일로 제한한다.
  오래된 중단 상태 trace도 정리하되 노출 사실은 제거하지 않는다.

## 화면과 API

`GET /api/v1/worlds/{world_id}/recommendation-topics`와 선택적 `world_character_id`:
주제·상태·키 연결 대상·승인 필요 여부·최근 실제 Feed 확인. GET은 생성하지 않는다.

`PUT .../key`: 명시적 키 대상 저장. `POST .../regenerate`: 원본 주제 준비/재생성.
인증·owner 검사, 현재 소속 및 키 목적 검증을 사용한다. provider 오류·키 값은 응답에 노출하지 않는다.

UI provenance는 **LOCAL**이다. 기존 Button/Field/Select/InlineError와 semantic token을 사용한다.
새 외부 에셋·색상·화면 route가 없으며 Next와 static 조립이 같은 컴포넌트를 사용한다.

## 로컬 검증 증거

- Social + migrations + embedded data migration: **189 passed**.
- World/WorldCharacter/RoutinePosts/작성/direct LLM/계정 삭제 회귀: **145 passed, 1 skipped**.
- 이후 신규/기존 승인 구분 추가: 생성·승인 route 묶음 **21 passed**.
- 마지막 추천 후보/설명/전달/provider 변경 영향 검사: **13 passed**.
- 실제 최신 import inventory 구조 검사, frontend 구조·디자인 검사, embedded migration 계약 검사 통과.
- Next production build와 static build, lint 통과. 직접 브라우저 화면/실제 키 검증은 C10에서 확인한다.
- 합성 DB에서 Alembic 0095/0096와 embedded v16 parity, 기존 v2 및 v14 전환과 FK/데이터 보존 검증.

초기 회귀 실패는 이전 모드/테이블 수 fixture, DI를 연결하지 않은 route fixture,
이미 본 글만 남은 빈 결과 사유 코드에 있었다. 이를 수정한 재검증 결과를 위에 기록했다.
React render 중 ref 변경 lint 오류도 effect로 옮겨 수정했다.

측정 도구: `backend/scripts/measure_topic_recommendation.py`.
실제 설치 DB를 열지 않고 임시 SQLite/WAL에 1만 글·50 캐릭터·주제·관계·1만 노출을 구성한다.
동시성 1/2/4 각 200회, 첫 조회, 5,000개 Trie, SQL 조회 계획, 테이블/인덱스별 공간,
프로세스 CPU/RSS를 기록한다. 이 RSS는 fixture와 ORM 등 측정 프로세스 전체이며 기능의 추가 메모리만을 뜻하지 않는다.
기존 FTS와 비교 구현/벤치마크는 없다. 실제 주제 생성/행동 AI 지연·요금은 측정하지 않았다.

[최종 측정 JSON](sns-topic-recommendation-measurement.json): query p95는 동시성 1/2/4에서
137/198/339ms, 프로필 로딩 포함 준비 p95는 140.05/200.16/343.49ms였다.
1만 노출 조건 준비 p95 93.79ms, Trie 5천 개 준비 13.64ms, 이름 매칭 p95 1.34ms.
보충 검증 직후 동시성 4의 query p95가 541ms였으나 실행 중 중복 읽기를 줄여 목표 500ms 안으로 돌아왔다.

## 직접 USER CHECK와 로컬 실행

README의 contributor 경로에서 **현재 체크아웃을 실행**해야 한다. 기본 production 이미지나
이미 설치된 앱은 이번 로컬 코드를 포함한다고 볼 수 없다.

```powershell
Set-Location D:\project_code\angmoo-workspace\angmoo-tree-angmoo
git branch --show-current
git log -1 --oneline
docker compose -f compose.yml -f compose.dev.yml up --watch
```

실행 후 `http://127.0.0.1:3000`에서 다음을 확인한다.

1. 기존 World/캐릭터 화면에 들어가기만 하면 주제가 생성되지 않는지.
2. World 편집의 추천 주제에서 키 대상을 연결하고 World/캐릭터 다시 만들기를 실행할 수 있는지.
3. 승인된 관심사가 서로 다른 캐릭터 3명으로 새 AI 글·사용자 글·무주제 글을 준비한다.
4. 각 캐릭터 활동 후 최근 전달된 Feed의 출처·구성·본문 반응·지연을 확인한다.
5. NO_ACTION 후에도 재노출이 없는지, 이전 글이 제외되는지, 재시작 후에도 유지되는지.
6. 프로필/World 저장 후 갱신 필요 표시, 재생성 실패 시 정상 주제 보존, 중복 클릭을 확인한다.
7. 새 World의 키 미준비 상태, 새 캐릭터 승인 시 주제 준비, 수정/탈퇴의 대상 범위를 확인한다.

사용자가 직접 확인한 환경·항목·체감·문제를 기록한 뒤 C10을 판정한다.
현재는 **USER CHECK PENDING**, C11의 최종 완료 판정도 그 결과에 달려 있다.
