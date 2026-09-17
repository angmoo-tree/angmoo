# 사회적 맥락·하이브리드 기억 검색 로컬 실행 결과

2026-09-17 에피소드 기억 후속 현재 상태: **사용자 승인 · 기본값 채택 완료 · F1~F4 사용자 수용 기준 PASS · 기존 품질 이슈·미측정·후속 검증 기록 유지**. F1 구조·기능 작동, F2 알려진 품질 이슈 수용, F3 체감 속도 수용·반복 측정 생략, F4 실제 사용자 동시 실행 기능을 기준으로 통과 처리했다. 개별 실패 수정이나 미수행 측정 완료를 뜻하지 않는다. ACTIVITY_THOUGHT_POLICY=thought_v1, MEMORY_GENERATION_POLICY=episode_v1, MEMORY_RECALL_REPRESENTATION=episode_v1을 코드 기본값과 실행 Docker에 반영했다. 기존 social_hybrid·group_or_v1·Vec1 flat·RRF·관계 맥락은 유지한다. 최신 판정·한계·후속 검증은 [에피소드 운영 안내](episode-memory.md)를 따른다. 아래 HY/HR/FI/SD/SP 및 날짜별 후속 시험의 최초 실패·보류·성공 수치는 당시 이력으로 보존하고 최신 수용 판정이나 서로 다른 표본의 결과와 혼합하지 않는다.

기존 HY/HR의 사용자 채택 판정: **사용자 기준 Chat 22/24 = 91.7%, 85% 목표 통과 / Chat·SNS 구조 기본 채택**. 기본값 `CHAT_RECALL_MODE=social_hybrid`, `SNS_SOCIAL_CONTEXT_ENABLED=true`는 지금도 유지한다. 이 22/24는 이후 에피소드 구조의 현재 시험 성공률을 뜻하지 않는다. 아래 시험 당시의 HOLD는 역사 기록이며 나머지 성능·설치·배포 검증 완료와 구분한다.

2026-09-15 FTS 후속 현재 상태: **사용자 승인 / group_or_v1 기본 채택 / FI0–FI12 LOCAL COMPLETE**. 현재 기본은 `CHAT_HYBRID_FTS_POLICY=group_or_v1`, Chat `social_hybrid`, SNS 사회적 맥락 true다. 설정을 명시하지 않으면 새 FTS 정책을 사용하며 기존 `legacy_strict_v1` 명시 설정은 복귀 수단으로 유지한다. 최신 근거는 workspace `.task-output/fts-grouped-implementation-20260915/run-03-default/report.md` 및 FI 계획 §14.3이다. run-01/02 최초 실패·보류 이력은 보존한다.

새 정책의 로컬 선택/복귀는 서버 설정 `CHAT_HYBRID_FTS_POLICY`를 각각 `group_or_v1`/`legacy_strict_v1`로 정하고 앱 runtime을 재구성하는 방식이다. 인덱스 재구축·데이터 삭제·벡터 재생성을 요구하지 않는다. 기본 구성 및 두 명시 정책의 composition·native 회귀를 검사한다. 설치 앱에 설정을 변경하거나 앱을 재시작한 검증은 아니다.

FTS 구현은 기존 토큰 표현과 BM25를 유지하며 단어 묶음 OR 후 문자열을 검증한다. 32그룹/128고유 토큰/MATCH 8KiB, ID 후보 창 최대 200, 반환 최대 50, normalized/raw/metadata 적재 합계 4MiB, 단일 read transaction 및 공통 deadline을 사용한다. 정상 0건의 spacing 보완은 한 번·2,000행/50ms 이내다. PARTIAL 사유와 UNAVAILABLE 오류를 분리한다. 기본 관측은 본문 없는 `fts_search` policy/status/수치이며 MATCH·검증 정보는 요청별 상세 opt-in에서만 수집하고 redaction·잘림/누락 표시를 적용한다.

재현 코드는 `backend/scripts/evaluate_grouped_fts_policy.py`, `evaluate_grouped_fts_native_cached.py`, `benchmark_grouped_fts.py`, `benchmark_grouped_fts_mixed.py`다. 각 CLI는 `--help`에 명시한 합성 입력/출력 경로를 필요로 하며 설치 DB를 자동 탐색하지 않는다. benchmark fixture는 사용자 DB 대신 별도 출력 디렉터리에서 생성한다. 실제 AI Chat 재현에 사용한 동결 corpus·로컬 runner·개별 receipt는 workspace 실행 디렉터리에 보존했다. 실제 자격 증명은 저장소에 포함하지 않았다.

성능 도구의 RSS 측정은 평가 전용 `psutil`이 필요하다. 깨끗한 개발 환경에서는 backend에서 `uv run --with psutil python scripts/benchmark_grouped_fts.py --help` 또는 대응 mixed 스크립트로 실행한다. 제품 검색 경로에 새 패키지를 추가하지 않았다.

이번 실제 Chat 결과는 기존 24개 최초 22/24, 전체 재시험 23/24, 새 20개 20/20이다. q28의 근거 없는 ‘오늘’은 남고, 최초 e12는 검색 전 schema 실패였으며 재시험은 성공했다. e10 FTS-only 공연 취소는 두 실행에서 원문과 답변이 일치했다. run-01 추가 e10 vector-present Chat의 크레딧 소진 429 이력은 보존했다. 결제 후 run-02 실제 비교는 두 정책 각 3/3 공연 취소 답변 성공, 연습 날짜까지 모두 명시는 각 2/3이었다. 새 FTS는 m24 3/3 발견, 기존 FTS는 0/3, vector는 두 정책 모두 3/3 1위였다. 이는 기존 q47 cached-native 비교와 별도인 실제 Supervisor→검색→RRF→CRG 시험이다. 10만 native mixed p95는 legacy/group 3.73/1.98초, 합산 RSS 표본 peak 711/208MiB였다. 이는 10만 기억의 실제 Chat 왕복 시간이나 전체 writer pipeline 비용이 아니다.

최종 FI 로컬 회귀는 Memory·Chat/runtime/아키텍처 1,040개 범위에서 최초 1,039 passed/1 failed, 새 취소 테스트의 필수 인자 누락 수정 후 관련 17 passed다. 원래 실패와 수정 영수증을 모두 보존했고 미해결 회귀는 0이다. 실제 Vec1 extension 및 opt-in diagnostic 성능 검사를 활성화해 skip 없이 실행했다. 아키텍처 경계·memory inventory·diff check도 통과했다. 설치 앱 재시작·직접 USER CHECK·CI·commit/merge/release는 수행하지 않았다. 후속 run-02에서 FI10 확장 부하/취소 단계별 행렬도 완료했다. run-03 사용자 승인과 기본 전환 검증까지 마쳐 FI0–FI12를 로컬 완료 처리했다. 후속 관련 native·정책·worker/runtime 회귀는 51 passed/0 skipped, 아키텍처·inventory·diff 검사는 통과했다.

실행일: 2026-09-14 KST. 계획은 workspace의 `docs/plan/09-13 채팅 FTS5·Vec1 하이브리드 기억 검색과 Planner 없는 기억 조회 전환 로컬 구현 세부 계획.md`다. 시작 저장소는 `fix/chat-retrieval-debugging`, clean HEAD `ae9744f060b5680d59486b2474d532dadccf9bf9`였다. 새 branch/issue/PR/push/merge는 수행하지 않았다. 실행 산출물은 workspace `.task-output/hybrid-memory-20260914/`에 있고 실제 키·원래 캐릭터 설정은 저장소에 복사하지 않았다.

## 최초 HY 실행 당시 단계별 상태 (기본 채택 전)

| 단계 | 구현·실행 결과 | 남은 판정 경계 |
|---|---|---|
| HY0 | 기준선 922 passed / 6 skipped, 구조 기준선과 기능 보존표 기록 | 기존 preservation checker 실패를 별도 유지 |
| HY1 | 모델/profile/배포 자원/worker/예산을 execution-manifest.json에 확정 | 하드웨어 절대 성능 채택 기준을 최초 측정 전에 동결하지 못함; HY13 HOLD |
| HY2 | Relationships 소유 immutable outgoing snapshot, 현재 원본 재검증, bounded Ladybug 읽기 | 전체 관계 수·역방향·과거 사건을 의미하지 않음 |
| HY3 | Supervisor·CRG 동일 snapshot, Graph/BOTH 비노출·실행 차단, 출력 전 재검증, current-context inspector | 실제 사회적 방향·사실 품질은 HY14 HOLD |
| HY4 | World SNS routine/feed/inbox 판단·작성 입력 및 소비 ID/재개·발행 전 검사 연결 | 실모델 비교는 feed comment lane; 나머지 lane은 오프라인 입력·정책 검증 |
| HY5 | 공식 Vec1 0.7 scalar flat NN, 0/1/2·증분·재시작·scope 및 Windows OneFile/Docker 실제 실행 | 설치 프로그램 설치·직접 USER CHECK 아님 |
| HY6 | typed request/axis/usage/source receipt, Planner 없는 Canonical ToolNode, legacy 회귀 | 미지원 연산은 아래 보존표 참조 |
| HY7 | 독립 Google embedding 설정/기존 키 선택, SQLite v12 eligibility, 신규·pending 수락 대상 등록, 100k 원자적 quota | 설치 DB migration은 실행하지 않음 |
| HY8 | eligibility page 복구, content/profile/credential별 durable 재시도, staging 재개/원자적 승격 | 실행 중 손상은 degraded 후 재시작 복구; 대규모 손상·공간 부족의 완전한 복구 행렬 미완료 |
| HY9 | 독립 프로세스/SQLite connection 동시 조회, 동일 scope·기간, document/version/hash RRF 및 원본 재검증 | FTS-only/disabled/partial을 vector 성공으로 합산하지 않음 |
| HY10 | 순위 보존 원문 보충·receipt·근거 freeze·CRG·current-source inspector | 일부 원문 제외는 partial; 전체 원문 무제한 적재 없음 |
| HY11 | 세 모드 실제 workflow/ToolNode, nonlegacy Graph Planner 0, hybrid Canonical Planner 0 | 실제 Supervisor가 검색 자체를 선택하지 않는 오류가 남음 |
| HY12 | embedding 설정·상태, 보유 개수·한도·부분 run 저장/대기 개수, 재시도 capability, 공통 웹/정적 화면 | 브라우저 transport mock과 설치 앱을 구분 |
| HY13 | 0/1/2/1k/10k/100k native 규모, 100k 동시 읽기·타 scope 쓰기, quota 경쟁, 취소 및 복구 시험 | **PERFORMANCE ADOPTION HOLD**; cold OS cache·전체 staging peak·대규모 장애 행렬 미완료 |
| HY14 | 동결 retrieval 48문항, Chat 48요청, SNS 전후 비교, real-workflow browser 10개, 실제 요약 3개 비교 | **QUALITY HOLD**; 요약 누락·라우팅·근거 없는 사실·SNS schema 실패 보존 |
| HY15 | 두 채택 모두 HOLD, 기본 legacy 유지, 모드 복귀·기능 보존·인계 기록 | CI/USER CHECK/설치·release·Production은 수행하지 않음 |

## 책임과 실제 연결

SQLite가 기억과 eligibility의 원본이다. FTS5와 Vec1은 서로 다른 재생성 가능한 파생 DB다. Memory 도메인이 quota·수명·검색 계약을, Relationships가 사회적 맥락 선정과 검증을 소유한다. runtime이 credential·저장소·native process·Chat/SNS 수명을 연결한다. 모델은 scope, SQL, Cypher, 경로, 기억 등록 권한을 정하지 않는다.

사회적 snapshot은 Chat 요청 또는 World SNS 활동 시작에 준비하고 같은 활동의 판단/작성자가 같은 ID/hash를 사용한다. 이후 요청은 새로 준비하므로 같은 채팅방에서도 관계 변경이 반영된다. 무기한 캐시가 아니다. 새 요청의 준비와 별개로 사용 중인 snapshot은 출력·발행 전에 현재 원본 version/권한을 재확인한다. 친숙도·호감·신뢰·긴장·관측된 변화량은 나→상대의 현재 관계 맥락이며 상대의 속마음이나 사건 일지를 만들지 않는다.

SNS 연결: routine generation의 계획/작성, World feed reaction planner와 comment writer, combined inbox의 실제 `_call_json` 입력에 연결했다. legacy 또는 active World가 없는 경로에 World를 추측해 주입하지 않는다. 기존 inbox/관계 관측 신호와 행동 후보·권한·중복 방지 정책은 유지한다. 실제 SNS 평가에서는 게시 실행기를 호출하지 않았고 publish_count=0이다.

## 기술 설정

완전한 값은 `execution-manifest.json`에 있다. Python 3.13.12 / SQLite 3.50.4 (Windows), Docker Python 3.13.15 / SQLite 3.46.1, google-genai 2.17.0, FastAPI 0.141.1, SQLAlchemy 2.0.51, LangGraph 1.2.2, PyInstaller 6.16.0으로 확인했다.

- Vec1 공식 0.7 (`8fc7b115a4`), C source SHA256 `8571bb4f77f9547d11ad11e2f72e0de7d3b2ab44e7930151998bce9377ed4b86`. `flat`/`nn`/cosine/768 float32/finite·nonzero·unit normalization. ANN/none 비교 없음.
- `gemini-embedding-2`, profile `0b7deda170179394239809036ea3f5a7eaa1fa91021d1230d59d86bedbbceda4`. 질의는 `task: search result | query: ...`, 문서는 `title: Memory | text: ...`; 저장된 요약 전문을 사용한다. 키 교체는 profile 변경이 아니다.
- 파생 경로: `data_paths.search/memory-vectors/generations/<server generation>/vectors.sqlite3`. 포인터는 `memory-vectors/current.json`. build-time manifest의 exact SHA를 검사하며 runtime 다운로드·사용자 지정 확장 경로는 받지 않는다. Windows build timestamp 때문에 DLL/EXE byte hash가 빌드마다 달라질 수 있다. source/options 재현성과 byte-for-byte 재현성을 구분한다.
- snapshot 최대 12개/3,000문자, 쿼리당 후보 8개, 준비/재검증 2초. inspector의 현재 관계 검증도 총 2초다. 준비 AI 0회.
- FTS·vector 각 후보 50개, equal-weight RRF k=60, 결합 문서 50개, 최종 기억 최대 20개, 원문 보충 참조 20개, 기억별 근거 20개. query 최대 4,000문자. worker 각 2개로 프로세스 총 4개까지이며 request Session을 공유하지 않는다.
- 검색 제한은 `min(20초, resolved caps.timeout_ms/1000, 요청 잔여시간-CRG 15초)`다. 현재 resolved 기본값은 4초. 질의 embedding과 vector NN은 한 축 안에서 순차이며 이 축 전체가 FTS 축과 겹쳐 실행된다. native Vec1 loop는 SQLite interrupt를 확인하지 않으므로 취소는 격리 프로세스 terminate/join으로 보장한다.
- 배경 projection은 page 64개, tick 1초, embedding 30초/SDK 1회. content/profile/credential revision별 최대 3회 시도와 30/60/120초 간격을 파생 DB에 남긴다. 일반 재시작·pin·키만 변경으로 정상 벡터 전체 재생성하지 않는다.
- 기존 미등록 기억은 FTS-only다. 새로 수락/정정된 기억과 적용 후 pending 수락 결과만 canonical transaction 안에서 eligibility를 등록한다. 등록 정보를 읽지 못하면 모든 기억을 추정하여 외부 전송하지 않는다.
- 현재 보유 100,000개 집계는 active·not deleted·not superseded·(미만료 또는 pinned)이다. OFF는 개수를 바꾸지 않는다. 기존 초과분은 자동 삭제하지 않으며 신규 추가만 막는다. 대체의 순증 0과 만료/pin 경계를 구분한다.
- API `capacity_blocked`, `stored_count`, `storage_limit`, `can_run`, `retryable`, `run_saved_count`, `run_pending_count`를 화면에 표시한다. 실제 run이 없으면 run 개수는 null이며 가짜 0을 표시하지 않는다.

## 기능 보존·미지원 표

| 기능 | legacy_checkpoint | social_context_baseline | social_hybrid |
|---|---|---|---|
| 맥락 답변·검색 전 되묻기 | 기존 정책 | snapshot 포함, 검색 0회 | snapshot 포함, 검색/embedding 0회 |
| 일반 회상의 이름/방향/기간 미해석 | 기존 정책 | 기존 정책 | 검색 허용·조건 보존; 이후 CRG가 답변/확인/불확실성 판단 |
| CANONICAL 검색 후 확인 질문 | 기존 계약 | 기존 계약 | route·근거 이력 유지, 생성 호출 추가 없음 |
| Canonical 검색 | 기존 Planner | 기존 Planner 유지 | 코드 hybrid, Planner 0 |
| memory/message/post/reply/social/activity/relationship-event 종류 | 기존 연산별 계약 | 기존 연산별 계약 | allowlist에 있는 종류만 기억 projection에서 검색 |
| 기간 | 기존 연산 계약 | 동일 | FTS/vector top-K 전 `[from,to)`, 원본에서도 재검증 |
| 특정 연결 원문 보충 | 기존 exact-source 계약 | 동일 | 허용된 hit의 연결 source만 한도 내 보충 |
| 임의 source ID 직접 요청 / aggregate count·rank·compare·group | 기존 지원 연산 | 동일 | 전용 동등 구현 없음; aggregate는 `hybrid_aggregation_unsupported`, search 종류 없는 요청은 `canonical_operations_unavailable` |
| counterpart/thread 필터 | 기존 typed 연산 | 동일 | Memory typed request는 지원; 현재 Supervisor→hybrid 어댑터는 이를 자동 추론하지 않음 |
| Graph/BOTH 모델 도구 | 명시적 legacy 설정의 기존 경로 | schema/parser/resolver/ToolNode 모두 차단 | 동일 차단 |
| 현재 나→상대 관계 | 기존 입력 | bounded current snapshot | 동일 snapshot |
| 역방향·경로·공통 이웃·전체 순위 | 기존 Graph 실험 | 현재 snapshot으로 답을 확정할 수 없음 | 동일; 숨은 Graph Planner fallback 없음 |
| 실패·0건·disabled·partial | 기존 계약 | 기존 계약 | 축별 receipt와 canonical/source 제외 구분; 조회 실패를 기억 부재로 확정하지 않음 |

세 capability fingerprint는 `chat-recall.v1:<mode>`의 hash다. mode identity이며 모든 운영 설정을 포함한 전체 구성 hash가 아니다. profile·deadline·자원 값은 manifest와 request diagnostics에서 별도로 확인한다. GC/Graph 실험과 기존 증거는 삭제하지 않았다.

## 실제 모델 품질 판정

대상 persona는 미도리야 이즈쿠, 생성 모델은 `gemini-3.1-flash-lite`, 시험 요청은 `thinking_level=high`다. 설치 DB의 모델은 확인했지만 schema v9에는 `default_thinking_level` 열이 없어 저장된 high를 확인했다고 주장하지 않는다. 시험에서 high를 명시했다. 원래 persona와 credential만 검증된 물리 경로에서 읽고 합성 World/기억/관계 DB로 평가했다. 설치 데이터는 수정하지 않았다.

Retrieval corpus 동결 SHA256: `4061f9e7ab43668cf70cb54a6c025fd59c4805d9335d7546ca0758f1e8ba450c`. 요약 24개 중 22개에 실제 embedding을 만들고 2개는 미등록 과거 기억으로 남겼다. 질의 48개, 문서 22개로 실제 embedding 70회다. 아래는 **검색축을 강제로 실행한** Hit@10이다. 정답은 사전에 정한 기억/근거이며 벡터 거리 순위를 정답으로 삼지 않았다.

| 자료 | n | FTS | Vec1 | Hybrid |
|---|---:|---:|---:|---:|
| 개발 전체 | 16 | 8 | 14 | 15 |
| 보류 전체 | 32 | 14 | 30 | 31 |
| 개발 바꿔 말하기 | 8 | 0 | 7 | 7 |
| 보류 바꿔 말하기 | 16 | 0 | 15 | 15 |

벡터 적용 대상만 보면 개발 14/14, 보류 30/30이다. 미등록 기억의 vector miss를 의미 검색 실패로 합산하지 않는다. 이 corpus는 원문과 저장 요약이 같아 요약 품질을 증명하지 않는다.

실제 Supervisor→CRG 동결 SHA256 `c4bad0bd1fda518125bc2626b8592d4f3326138e657fef462e4a53611b6da372`. 사회적 문항 12개×legacy/baseline, 기억 문항 12개×baseline/hybrid로 총 48요청을 실행했다. 47 committed, 1 failed다. Graph Planner는 nonlegacy에서 0회다. 검색이 실행된 hybrid의 Canonical Planner도 0회이며 준비 AI/평가 AI는 추가하지 않았다. 추가 repair는 실제 physical call로 기록했다.

기억 문항은 baseline 11개 되묻기/1개 schema 실패, hybrid 10개 되묻기/2개 Canonical이었다. q20은 날짜를 맞혔지만 제공하지 않은 훈련 세부 기록을 덧붙였다. q24는 도시락을 준비하는 주체를 올바르게 답했다. fixture에 실제 World target을 두 명만 넣어 이름 해석·부재가 되묻기에 영향을 주었으며 보류 문항을 결과에 맞춰 수정하지 않았다. 검색기 개선률을 대화 정확도로 바꿔 부를 수 없다.

사회적 맥락은 우호적 상대와 긴장되는 상대를 나눠 협업 방식을 제안하는 등의 변화가 있었다. 그러나 일부 답변은 알려주지 않은 과거 훈련이나 만남을 덧붙였고, 선택된 두 관계를 전체 학급 신뢰로 일반화했다. 현재 outgoing 수치만으로 역방향 속마음·과거 원인·전체 순위를 추론하지 않도록 하는 품질 Gate는 HOLD다.

SNS는 같은 합성 관측 사실·comment/like 후보로 6문항×전후 비교했다. 최초 high/900·1000 output budget에서 MAX_TOKENS·JSON truncation이 발생했다(v1 11결과 중 9실패/2완료, 13 calls). 명시적 high의 planner/writer output 한도를 4096으로 바꾸고 재동결한 v2는 11완료/1실패, 23 calls다. 기존 medium 한도는 유지했다. v2 neutral-with의 DirectLlmJsonError는 재시도해서 지우지 않았다. 두 변형 모두 안전 점검 생략에는 반대했으나 과거 훈련/관찰을 꾸미는 문제가 있어 SNS 품질도 HOLD다. 공개 게시 0회.

요약 보존은 별도 동결 3개 source를 실제 선별 provider에 한 번 전달했다(`summary-quality-v1/`, frozen SHA256 `a8e1c420ac82973315e66f8e8d6daeb6b410b49fecbe8ddc96f1221eb8ad8269`). 3개 모두 retain, 주체·0.1초 대 1.0초·장소/시각은 보존됐지만 날짜·미통지·상대 신뢰 미확정 정보가 빠졌다. 기존 120자 AI 요약 정책의 결과이며 embedding 전 임의로 더 잘라낸 것이 아니다. 정확한 누락 정보는 요약 벡터에서 복원할 수 없다. 원문 보충과 요약 품질은 별도 Gate다.

실제 생성 workflow와 EvidenceService를 실행한 브라우저 10문항이 통과했다. shell/auth HTTP는 fixture transport이며 실서버 API 또는 설치 앱 전체 검증은 아니다. 이 10개의 실제 route는 CURRENT_CONTEXT 5/CLARIFICATION 5여서 브라우저의 native Canonical 실행 성공으로 주장하지 않는다. Canonical 실모델 실행은 위 q20/q24의 production workflow 결과와 별도 native integration으로 확인했다. 최신 UI 재검사는 같은 receipt를 재사용하여 추가 AI 없이 수행한다. 문항마다 DB를 복사해 새 응답 기억이 다음 문항을 오염시키지 않았다.

비용 집계는 `assessment.json`에 남겼다. 기록된 생성 input 374,621 / output 14,842 / thought 161,100 tokens를 기준으로 입력 $0.25/M, 출력+thinking $1.50/M 가정 시 **최소 약 $0.358**이다. 이는 청구 총액이 아니다. embedding token usage 70건은 미제공이며 일부 Planner/실패 usage가 없어 unknown으로 남겼다. 같은 키를 썼다고 embedding을 무료/0원으로 처리하지 않았다. 사전량 추정·실패 v1·수정 v2·재사용된 pilot을 구분하며 작은 임의 총호출 상한은 추가하지 않았다.

## 규모·배포와 실측 한계

Windows i5-1235U, native scalar Vec1, 합성 768차원 데이터다. OS cache를 강제로 비우지 않았다. 직접 호출은 매번 connection을 여는 adapter 호출이며 provider embedding·Chat·FTS 전체 시간과 다르다. 10회 표본의 p95는 탐색적 수치다.

| 벡터 수 | 직접 조회 p50 / p95 ms | 두 worker wall ms | 최초 삽입 wall / parent CPU s | DB bytes |
|---:|---:|---:|---:|---:|
| 1,000 | 46.5 / 73.4 | 596.2 | 0.441 / 0.344 | 3,436,544 |
| 10,000 | 156.6 / 184.7 | 715.0 | 4.180 / 3.922 | 33,910,784 |
| 100,000 | 1,125.6 / 1,344.2 | 1,673.1 | 39.476 / 35.672 | 338,956,288 |

100k+다른 owner 1k+다른 subject 1k의 동시 읽기/쓰기는 조회 pair 5회 각각 1,728/1,176/1,140/1,126/1,128ms, 쓰기 1k씩 763.7/213.9ms, 잘못된 scope hit 0이었다. 25ms sampler의 process-tree RSS peak 101,838,848bytes(약 97.1MiB), live WAL peak 6,975,192bytes(약 6.65MiB), child 최대 2개, 전체 wall 8.07초/parent CPU 2.984초다. 종료된 child CPU는 합산하지 않았다. 원본+복사 677,912,576bytes는 실제 staging의 최악 peak가 아니다. native buffer/SQLite cache를 분리 측정하지 않았다.

99,999개에서 두 독립 SQLite writer가 마지막 슬롯을 동시에 수락해도 한 개만 성공했다. 2후보 AI batch는 하나 저장/하나 pending으로 남고 100k에서 반복 실행해도 추가 AI가 없었다. OFF는 count를 유지하고 실제 만료로 공간을 확보한 후 남은 후보를 처리했다. 실제 사용자 기억을 10만 개 외부 전송하거나 삭제하지 않았다.

공식 extension을 실제 product Docker image와 OneFile sidecar에 포함하고 0/1/2 NN, 다른 owner 0건, worker join을 실행했다. 최종 Docker SO SHA256 `6479ec6adc87e644835c94375be72572a5009cd11e9530ebee57189909c31883`; 미지원 outcome 정정까지 포함한 Windows EXE SHA256 `1496a62546774150b142ca72c053b23cfaf06e1889b60df7fec23719e15977a2`, 54,305,946bytes. 상세 runtime receipt는 `docker-outcome-final-probe.log`, `packaged-outcome-final-probe/receipt.json`이다. 이 패키지는 당시 작업 트리의 diagnostic build이며 설치/배포용 release로 발행하지 않았다. 앞선 빌드 receipt와 hash도 삭제하지 않았다.

## 회귀·오류 정정 기록

- 기준선: Chat/Memory/Graph 922 passed / 6 skipped. architecture 1,099 modules / 4,135 edges / legacy exact edges 0.
- 최초 확대 회귀: 1,194 passed / 8 skipped / 2 failed. FTS child receipt 전환 중 parent가 이전 코드를 로드한 실행과 한국어 10k 성능 기준 초과를 보존했다. 새 process로 native integration은 통과했다.
- 한국어 10k 성능은 독립 재검사에서도 추가 p95 27.86–31.70ms로 기존 25ms 기준을 넘었다. 동일 환경의 baseline module은 PASS였다. progress callback을 100 VM ops마다 호출하던 비용을 1,000 ops로 줄였고 행/byte/시간 제한은 유지했다. 수정 후 기존 성능 assertion 포함 hardening 64 passed / 2 warnings. 단일 실험 PASS를 보편적인 지연 보장으로 해석하지 않는다.
- partial capacity API/runtime 21 passed / 2 warnings; 실제 두-writer 경쟁과 저장/대기 개수도 포함한다.
- 최종 architecture 1,132 modules / 4,279 edges / legacy exact edges 0. 프런트엔드 lint/typecheck/static export PASS. 최종 확대 회귀 및 브라우저 결과는 아래 최종 마감 기록에 추가한다.
- 이전 preservation checker는 시작부터 FAILED: `mark_terminal` durable command 차이, PR258/PR263 API snapshot 차이, committed test introduction evidence 누락. frozen assertion을 완화하지 않았다. checker가 앞선 예외 뒤 protected lineages=0으로 낸 3,438 메시지를 각각 확정 회귀라고 해석하지 않는다.

## 원복·채택·후속 작업

`CHAT_RECALL_MODE=social_hybrid`는 새 사회적 맥락+코드 hybrid, `social_context_baseline`은 같은 사회적 맥락+기존 Canonical Planner, `legacy_checkpoint`는 기존 Graph/BOTH까지 포함한 명시적 보존 모드다. 환경 설정을 변경하고 해당 개발 runtime을 재시작하면 다음 요청부터 적용된다. 이 실행에서는 사용자 설치 설정을 변경하지 않았다. hybrid만 중지할 때는 baseline, 사회적 변경까지 중지할 때는 legacy를 명시한다. 장애가 이 값을 자동으로 바꾸거나 Graph 도구를 다시 활성화하지 않는다.

Embedding OFF는 해당 scope의 새 embedding/query 사용을 중지하고 원본 기억·키 참조를 보존한다. scalar native extension이 없으면 원본 startup을 망가뜨리지 않고 vector_unavailable/FTS partial로 남긴다. 파생 손상 복구는 runtime 재시작 시 등록된 대상만 staging에 재구성하며 파일/등록 손실 상태를 추정한 전체 백필은 하지 않는다. active 손상/marker 오류를 사용자 데이터 삭제로 고치지 않는다. SQLite v12를 구버전 프로그램으로 강제 열거나 downgrade migration하지 않는다.

사회적·hybrid 채택 모두 HOLD이므로 중간 baseline도 기본값으로 올리지 않았다. 남은 핵심은 (1) 실제 populated World의 참조/검색 선택 오류 해결과 새 동결 문항 재평가, (2) 요약 누락·현재 관계에서 과거/역방향/전체를 꾸미는 오류 방지, (3) cold cache·full staging·disk-full 및 실제 규모 복구 Gate, (4) 실 API/설치 앱 직접 USER CHECK다. CI·merge·release·Production은 별도이며 이 로컬 실행에서 완료하지 않았다.

## 2026-09-14 최종 마감 기록

- 확대 회귀 `regression-final-fixed-v2.log`: **1,391 passed, 8 skipped, 2 deselected, 4 failed** (502.43초). 2 deselected는 앞서 hardening 64개에 포함해 실행한 장시간 성능 시험이다. 4개 실패는 추가 migration 뒤 최신 revision/테이블/target 버전을 이전 값으로 기대한 시험이었다.
- 해당 4개를 새 revision 0092→0091 연결 및 정확히 두 테이블 추가로 갱신하고 **과거 88개 migration blob·graph 동일성 검사는 유지**했다. populated v8→v12 시험에 기존 memory row/hash 보존, 새 embedding/eligibility 테이블 0행을 명시했다. `migration-outcome-final.log`: **32 passed** (30.39초). 최초 4개 실패와 수정 후 결과를 별도 남기며 확대 회귀가 처음부터 모두 통과했다고 기록하지 않는다.
- 미지원 hybrid 조회의 결과를 NO_EVIDENCE로 오인하지 않도록 DEGRADED로 전달하고 memory OFF만 MEMORY_OFF를 유지했다. 독립 guard 검증 **5 passed**, 위 32개에는 이 경계와 기존 evidence streaming도 포함된다.
- 세대 pointer 교체에 ENOSPC를 주입해 기존 active와 staging을 보존·재개하는 시험을 추가했다. `disk-full-promotion-final.log`: **3 passed**. 이는 격리 fault injection이며 100k 실제 디스크 가득 참 전체 시험과 다르다.
- 브라우저 최신 UI 재검사 `browser-final-replay.log`: **11 passed** (3.9분). 실제 workflow receipt 재사용 10개와 owner controls/capacity partial counts 1개다. 이 재검사의 추가 생성 AI 호출은 0이다. screenshot 10개를 `browser-final-results/`에 보존했고 근거 dialog를 직접 렌더 확인했다.
- frontend lint/typecheck/static export, frontend architecture, frontend design contract, backend architecture **PASS**. UI-B/UI-F의 기존 committed screenshot 11개와 pixel threshold는 그대로다. 새 HY14 opt-in screenshot call 1개만 inventory에 추가(총 call site 12)하고, deterministic UI-F baseline 또는 USER CHECK를 추가한 것으로 표시하지 않았다.
- 마지막 outcome 수정까지 포함해 Windows OneFile과 Docker를 다시 빌드했다. 두 실제 native probe 모두 **passed**, 0/1/2 결과·타 owner 0건·worker_joined=true, AI 0회. 설치/실사용 데이터 변경 없음.
- 로컬 Git tree secret scan: **2,395 files, 15 binary audited, fatal=0**. 기존 public asset audit 11개는 보존했다. 새 공개 이미지 승인이나 public release를 의미하지 않는다.
- 로컬 기능 커밋: `e61d077d` Memory/Vec1/quota/migration, `0884d6c9` Relationships/SNS snapshot, `0b125847` Chat hybrid/evidence/modes, `439f2631` 공통 설정·근거 UI, `f6ee0a68` opt-in screenshot inventory. 각각의 중간 커밋을 독립 배포 검증한 것은 아니며 결합된 작업 트리를 검증했다. 문서 커밋은 이 인계 문서를 소유한다. push/PR/merge 없음.

최종 판정은 앞의 표와 동일하다. **로컬 기능 구현·검증 자료는 준비됐고 제품 기본 전환은 두 항목 모두 HOLD다.** 성능의 사전 절대 기준·큰 장애 행렬, 실제 모델의 라우팅/사실/요약 보존, 직접 설치 앱 USER CHECK를 남은 Gate로 인계한다.

## Historical checkpoint A — 2026-09-14 initial native probe

Official Vec1 `version-0.7` (`8fc7b115a4`) C source SHA256 `8571bb4f77f9547d11ad11e2f72e0de7d3b2ab44e7930151998bce9377ed4b86`; SQLite 3.53.0 amalgamation archive SHA256 `bf3733d7c71b3ab0f6fd8a9ea0052ad87fa037d94333e14ce09878ba3492c3b0`. MSVC 19.44.35228 x64, `/O2 /DNDEBUG` scalar build (no AVX2 minimum); DLL SHA256 `e28304e5c0bc79769e018352466d9af248c39f055bb5e397b31b6d92c38ce6f9`. Python runtime SQLite 3.50.4 loads it and reports `version 0.7 (Scalar, multi-threaded)`. Host: Intel i5-1235U, 10 cores / 12 logical processors.

- Empty flat table native NN probe raises expected-dimension-0. The adapter must distinguish a verified empty scope before querying; no seed/dummy vector.
- Before commit, newly inserted flat rows were not returned. After each successful commit, one vector returns distance 0; two orthogonal 768-float vectors return distances 0 and 1, including close/reopen. Search eligibility follows committed projection writes.
- First source-header fetch returned HTML; first build failed. Corrected to verified SQLite amalgamation headers and rebuilt successfully. This was build preparation, not an installed-app failure.
- Sources: [Vec1 reference](https://sqlite.org/vec1/doc/trunk/doc/vec1ref.md), [official build guide](https://sqlite.org/vec1/doc/trunk/doc/vec1.md). This is a native development probe, not packaged sidecar/Docker/installer or performance acceptance.

## Historical checkpoint B — early implementation, superseded by current status above

- Windows Ladybug/Graph/snapshot/native Vec1 focused suite: 32 passed. Docker real Vec1 SO/snapshot: 14 passed (read-only pytest cache warning). These do not cover a complete product image or packaged sidecar.
- First Chat integration attempt: 79 failed, 613 passed, 6 skipped. Corrected optional snapshot keyword compatibility and missing config-field defaults. Retest: 699 passed, 6 skipped, 4 warnings, 65.17 seconds. Social workflow tests include same-object inputs and source-change rejection before streaming.
- Native process worker, fusion and social workflow combined: 19 passed. The Vec1 C distance loop does not poll SQLite interrupt; cancellation therefore terminates and joins its isolated read process.
- Memory and current-schema suite: 231 passed, 4 skipped, 1 failed. The failure was the pre-existing fixed 103-table assertion after adding two tables. Updated assertion to 105; focused schema/import/fusion/deadline checks subsequently passed (11 tests).
- Initial 100,000 holdings fixture used an invalid memory-kind enum and failed before the boundary test; corrected to the existing AUTOBIOGRAPHICAL_EVENT value. Real 99,999 + two-candidate boundary then passed (9.93 seconds): one accepted, one pending, one new eligibility row, three blocked attempts without extra AI, OFF count preserved, expiry frees capacity and pending candidate completes.
- At this early checkpoint, hybrid mode remained explicitly unavailable until actual retrieval wiring is complete. No real Gemini generation/embedding calls, browser quality evaluation, SNS publication, CI, adoption or direct USER CHECK is claimed by these checks.


## 2026-09-14 HR0–HR8 후속 결과

현재 hybrid admission은 질문 속 인물 ID·행동 방향 ID·미해석 기간만으로 일반 회상 검색을 차단하지 않는다. 서버의 owner/World/응답 캐릭터 범위·Memory OFF·원문 현재 권한/삭제/버전 검사는 유지한다. legacy/baseline의 사전 정책은 유지한다. 검색 후 확인 질문도 route=CANONICAL이며 검색을 하지 않은 REQUEST_CLARIFICATION과 구분한다.

RecallInterpretationContext는 request/intent/resolved/question/scope/evidence hash에 결합한다. 원래 언급·semantic ref·방향·시간 해석/적용 필터만 CRG에 보내며 검색문 4,000문자·전체 payload 6,500문자 제한이다. 후보 ID/비공개 이름을 추가하지 않는다. CRG plain text를 유지해 runtime final_response_kind는 미분류(null), 질문별 판정은 평가 기록이다. 공유 tracker의 CANONICAL normal_full_path_cap=3은 기존 스키마 값이며 hybrid는 CRG 직전에 Planner 0, Router 1(+기존 repair 1), CRG 1을 별도 검증한다.

최종 실제 gemini-3.1-flash-lite/high 24개: 모두 committed, 최초 schema 24/24, backend 불필요 전환 0. 기억 질문 12개 모두 실제 검색/정답 근거 전달, 핵심 사실 11/12. 신규 경계 8/12. 생성 48 logical/48 physical, Planner·추가 평가 AI 0, 질의 임베딩 physical 21. e03/e05는 두 장소/날짜의 후보를 알려주었지만 동결한 기대인 확인 질문을 하지 않아 엄격한 기준으로 HOLD다. 대안 제시를 허용하는 10/12는 사후 참고값일 뿐 Gate에 사용하지 않는다. 12/12 핵심 사실 Gate에는 미달한다.

남은 실패는 q28의 근거 없는 오늘 조건/답변, e08의 0건에서 사용자 착각 추측, e10의 축제 취소 근거 미전달과 경험 부정이다. 별도 보충 h02/h03에서는 같은 이름의 허용 후보 2개(multiple)로 검색했고, h03은 장소를 특정하는 확인 질문을 했다. h10의 이전 공연 준비 맥락 이후 취소 여부는 근거 미전달로 HOLD다. 보충 3개를 원래 24개 분모에 넣지 않았다.

첫 실제 24개 결과와 수정 후 24개를 별도 보존했다. q20/q24 추가 묘사는 핵심 날짜/행동 방향을 유지하는 한 사용자 기준으로 PASS이며 최초 HY 판정을 삭제하지 않는다. 기존 과거 12개 모델 선택은 12/12, backend 검색 전환 통과는 2/12였고 q28 repair 포함 생성 25회였다.

로컬 회귀: Chat/architecture/inventory 786 passed, 성능 opt-in 6 skipped; 실제 native DLL의 검색/원문 차단·삭제·Memory OFF 포함 Memory 22 passed. 실제 저장 Chat의 thread/evidence 서비스 재조회 3/3, 실제 build의 legacy/baseline/hybrid 모드 분리 검증. 전체 설치 앱·직접 USER CHECK·CI·merge·release 검증은 아니다. 현재 기본 legacy_checkpoint, hybrid/사회적 맥락 채택 HOLD 유지.

상세 결과: workspace `docs/plan/09-14 채팅 하이브리드 기억 검색 차단 정책 개선과 CRG 확인 질문 판단 전환 계획.md` §11 및 `.task-output/hybrid-routing-crg-20260914/run-01/report.md`. 원본은 최종 revision2-responses, 초기 validated-responses, 보충 supplement-responses로 분리되어 있다. 합성 seed 시각/24개 자료이며 10만 개 지연·RSS나 실사용 전체 정확도를 나타내지 않는다.


## 2026-09-14 사용자 확정 기준과 기본 구조 채택

사용자는 e03/e05(두 사건의 장소·시간·날짜를 올바르게 제시)와 e08(불확실성과 조심스러운 혼동 가능성 표현)을 성공으로 확정했다. 현재 채택 기준은 **22/24 = 91.7%**, 사용자 목표 **85% 이상 통과**다. 기존 엄격한 19/24 판정과 원본 응답은 역사 기록으로 보존하며, 새 모델 시험 결과로 바꾸어 설명하지 않는다. 사용자 재판정은 `.task-output/hybrid-routing-crg-20260914/run-01/user-approved-assessment.json`에 별도로 저장했다.

사용자 요청에 따라 **현재 Chat 구조와 SNS 사회적 맥락 구조를 모두 기본으로 채택**했다.

- `CHAT_RECALL_MODE=social_hybrid`: 사회적 snapshot → Supervisor → 필요시 FTS5/Vec1 → 기존 CRG. 기본 Graph 도구·Canonical Planner·추가 평가 AI 없음.
- `SNS_SOCIAL_CONTEXT_ENABLED=true`: SNS 기존 판단·작성 호출에 현재 사회적 snapshot을 기본 제공한다. 채팅 모드와 별도 설정으로 분리해 각 경로를 독립적으로 되돌릴 수 있다. 기존 SNS 행동 권한·스케줄·게시 실행 규칙은 유지한다.
- 명시적 `CHAT_RECALL_MODE=legacy_checkpoint`/`social_context_baseline`은 비교·원복용으로 유지한다. SNS만 끄려면 `SNS_SOCIAL_CONTEXT_ENABLED=false`로 설정한다. 채팅 모드를 legacy로 바꾸는 것만으로 SNS를 끄지는 않는다.
- `app.config.Settings()`의 실제 개발 환경 해석 결과도 `social_hybrid`/`true`다. 별도 환경변수가 없는 실행에서 적용된다. 이미 실행 중인 프로세스에는 재시작 후 반영되며 설치 바이너리 교체·배포까지 수행한 것은 아니다.

남은 개선은 **q28의 오늘 조건/답변 추가**와 **e10의 FTS miss 및 취소 상태 오답**이다. e10 실제 원문은 “아시도와 9월 10일 축제 공연을 연습했고 9월 13일 공연은 취소됐다.”이며 아시도·축제가 포함되어 있다. m24는 eligible=false인 FTS-only 기억이고, FTS는 실행됐지만 0건이었다. 벡터 검색 대상이 아니었던 사실을 의미 검색 실패로 혼동하지 않는다.

**91.7%는 Chat 24문항의 사용자 확정 평가이며 SNS 성공률이 아니다.** SNS 기본 채택은 사용자의 별도 명시적 결정이다. 기존 SNS/사회적 맥락 품질 관찰, HY8 복구·HY13 성능, 직접 USER CHECK·CI·설치·merge·release·Production 검증이 모두 통과됐다는 뜻은 아니다. 현재 제품 기본 채택 결정과 남은 검증/개선 항목을 분리한다.


기본 전환 검증: Chat·사회적 맥락·OSS 경계 **746 passed, 6 성능 opt-in skipped** (`default-adoption-verified.log`). SNS/social/routine/resident 묶음은 최초 **331 passed, 1 failed, 1 skipped**였고, 관계 DB를 갖지 않는 기존 no-action 단위 fixture가 SNS 기본 ON을 가정하지 않은 실패였다. 해당 fixture만 SNS OFF를 명시해 독립된 회계 시험으로 보존했고, 관련 runtime·snapshot 재시험은 **28 passed, 1 skipped** (`default-sns-targeted-final.log`)다. 기본 ON의 snapshot 생성·actor 변경 재검증과 기본 hybrid 실제 composition은 별도 테스트로 통과했다. 기존 legacy Planner 순서 시험도 모드를 명시해 보존했다. 현재 `Settings()` 해석은 social_hybrid/true, diff whitespace 검사는 통과했다. 로그 경로는 workspace `.task-output/hybrid-routing-crg-20260914/run-01/`이다.


## 2026-09-15 FI10 확장 검증과 e10 비교 후 전환 판단

기본 전환 권고 근거와 재현 자료는 workspace `.task-output/fts-grouped-implementation-20260915/run-02/`에 저장했다. FI10 확장 warm 1,600회·새 프로세스 80회·취소 30회 완료. scope 노출·잔존 worker·예상 밖 상태 0, CPU/RSS 증가 Gate 통과. cold 정의는 새 worker 시작이며 OS cache 비우기를 필수 누락 항목으로 추가하지 않는다. 결과 수신 취소는 실제 pipe 패킷 준비 후 역직렬화 전이며 중간 프레임 고장을 주입한 것은 아니다.

10만 추가 부하 warm p95는 충돌 3.123초·긴 입력 3.932초·범위 1.103초·5MiB 행 0.041초다. cap에 걸린 PARTIAL을 일반 검색 성공으로 세지 않았다. 10만 projection 행 쓰기+전체 digest 갱신 5.81~6.30초는 새로 측정한 공통 유지보수 비용이며, 기존 단순 삽입 통계와 구분한다. reader 종료 후 WAL 0 bytes. 최초 manifest의 5초는 단독 benchmark 예산이며 제품 Chat 검색 caps를 바꾸지 않았다.

실제 AI 재현은 backend cwd에서 `uv run python <run-02>/run_e10.py` 경량 진입점을 사용한다. 평가 모듈을 직접 실행하면 Windows spawn 자식에서 부모 전용 import 비용이 추가된다. 최초 잘못된 진입점의 실패 6회·수정 후 AI 없는 precheck·실제 AI 성공 6회를 각각 보존하며 서로 다른 분모로 관리한다. 실행 전 설치 데이터/secret의 물리 경로를 검증하고 별도 합성 DB에서 시험했다. 설치 앱의 실행 검증이나 사용자 직접 확인을 의미하지 않는다.

FI12 완료: 사용자 승인 후 기본을 `group_or_v1`로 변경하고 미지정/명시 정책의 앱 구성과 실제 e10 검색, 관련 회귀 38개를 통과했다. 계획/운영 문서를 동기화했다. rollback은 `legacy_strict_v1` 명시 및 runtime 재구성이다. DB·벡터 재구축이나 memory backfill은 필요 없다. 기본 전환만을 위해 실제 AI 품질 시험을 반복하지 않았으며 추가 외부 AI 호출은 0회다. 설치 앱에 배포/재시작한 결과는 아니다.

## 2026-09-15 FI12 기본값 전환 완료

사용자 채택 승인 후 서버 설정 기본값과 runtime 전달·대표 e10 검색·명시 legacy 복귀를 검증했다. 관련 38 passed/0 skipped이며 실제 Vec1 extension을 사용했다. 새 기본 검색은 묶음 OR→문자열 검증→기존 RRF/원문 재검증이다. 기본값 전환 영수증은 workspace `.task-output/fts-grouped-implementation-20260915/run-03-default/`에 있다. 기존 쓰기 digest 비용과 q28 문제는 별도 후속 항목으로 남긴다.

## 2026-09-15 SD0~SD10 상세 검색 진단 보강

기존 **검색 진단 · 문제 해결**에서 상세 수집을 켠 뒤 새 질문을 보낸다. 완료/실패 후 **진단 새로고침 → 확인할 요청 선택 → 상세 진단 파일 저장**으로 같은 요청의 export v2를 저장한다. 새 `search_trace`는 FTS/벡터의 축 상태·worker 종료 상태·단계별 시간·안전한 실패 코드·근거 연결 별칭을 포함한다. 검색 결과를 받아 cleanup에서 terminate한 경우와, 결과 없이 timeout으로 종료한 경우를 구분한다. `eligible_vector_count=null`은 0개가 아니고, `nn_query_started=null`도 미실행 확정이 아니다.

수집 범위는 대화별 다음 10건/30분, 결과 보관은 최대 60분이다. 기존 조건과 trace를 합쳐 요청당 64KiB, 최대 20건/전체 1MiB이며, OFF·재시작·용량 제한으로 사라질 수 있다. 특히 Docker development StatReload도 메모리 수집 상태를 없앤다. 재현 도중 코드/테스트 파일을 복사하지 말고 서버 재로딩 종료를 확인한 뒤 켠다. 지금 켜도 과거 요청에 소급되지 않는다. 파일은 내려받은 뒤 사용자가 직접 관리해야 한다.

`available`, `pending`, `not_captured`, `not_retained`, `unsupported`, `unknown`을 구분한다. 원문·질문·검색 조건 전체가 기존 상세 영역에 있을 수 있으므로 공개 공유 전 확인한다. 새 단계/연결 trace에는 예외 메시지·traceback·SQL·토큰·경로·원문 본문을 넣지 않고 요청 내부 별칭을 사용한다. 선택한 요청 ID가 바뀐 stale 상세를 다른 요청의 파일로 내보내지 않는다.

| 진단 | 의미와 다음 확인 |
|---|---|
| slot_wait timeout | 슬롯 경합/취소 회수 확인 |
| process start 후 child 단계 미수신 | spawn/import/기동·부하 우선 조사. DB/NN 실패로 단정하지 않음 |
| DB/extension 단계 safe code | 해당 단계의 오류 종류와 실제 실행 경로 확인 |
| eligible 0 + ready | 해당 scope/profile의 정상 0건. 장애와 구분 |
| NN deadline | NN 시작 신호·벡터 수·남은 예산 비교 |
| source_ref 동일, key_ref 상이, dedup kept | hydrate/exact-source 참조와 canonical identity 정책 검토 |
| coverage partial | 확인된 항목만 해석. 미수신/생략을 성공이나 0으로 바꾸지 않음 |

검증은 회귀 118 passed/1 opt-in skipped, cleanup 단일 1 passed, 신규 진단 Docker Linux 28 passed, frontend export 5 passed 및 구조·디자인·lint/typecheck·Next/static 빌드 통과다. 상세 수집·직렬화 p95 OFF 0.19ms/ON 5.96ms, 큰 입력 한도 처리 6.28ms. 기존 기본 검색/RRF/권한/CRG 지침·deadline과 추가 AI 호출 수는 바꾸지 않았다. native 전체 시간은 spawn 및 환경 부하를 포함하므로 이 진단 처리 시간과 구분한다.

실제 재현은 3회로 제한했다. 첫 요청 CURRENT_CONTEXT, 두 번째 aggregation 미지원 및 재로딩으로 미수집, 세 번째 FTS/vector 모두 결과 대기 deadline으로 실패했다. 마지막 파일은 `result_received=false`, `joined=true`, exit=-15, child 단계/NN/eligible count 미확인을 보존했다. **당시에는 deadline만 확정됐고 내부 지연 원인은 미확정이었다. 후속 SP 기동 수정 결과는 아래 별도 기록을 따른다.** 원래 4→8 근거 중복은 합성 fixture에서 4 source/8 reference/8 dedup key 경로를 재현했지만 실제 새 검색의 정상 결과가 없어 원래 요청의 확정 분석과 구분한다.

당시 인계 항목은 AI 없는 Docker worker 기동/import 측정과 양축 실패 후 workflow 처리 확인, 정상 검색 trace의 source/key 대조 후 중복 정책 설계였다. 기동 수정은 아래 SP 결과에서 완료했으며 중복/fallback 정책은 별도로 남는다. 진단 보강을 장애 해결 완료로 표시하지 않는다. 산출물은 workspace `.task-output/search-diagnostics-20260915/run-01/`, 상세 내용은 workspace `docs/plan/09-15 채팅 상세 검색 진단의 벡터 실패 단계와 근거 중복 추적 보강 구현 세부 계획.md` §15에 있다. Docker 재빌드+개발 소스 동기화/에이전트 브라우저 확인을 수행했으며 USER CHECK·CI·MERGE·RELEASE는 별도다.

## 2026-09-15 SP0~SP10 Docker 검색 기동 수정 완료

contributor 모듈의 서버 전용 import를 실제 factory/status/main 실행으로 이동했다. 기존 volume·reload/non-reload·모델/data/identity 초기화 순서와 검색 scope·FTS·Vec1·RRF·CRG 계약을 유지한다. 실제 Docker에 새 파일 SHA256 `af579a2240a2e2c152385d69a0cdb3da139d4be25589af1c16c44a2b72b0d88a` 반영 및 건강 상태를 확인했다.

정상 native 4조건 120/120 성공, 무복사 상세 ON 추가 100/100 성공(p95 1.85초). 별도 파일 복사 부하 중 86/100 성공·14 timeout은 실패 기록으로 남는다. 기존 검색 cap 4초/축 약 3.6초 및 CRG reserve를 유지한다. 기동 경량화가 강한 호스트 부하의 timeout까지 없애지는 않는다.

실제 동일 0.1초 회상 질문 1회가 `gemini-3.1-flash-lite/high`, CANONICAL, 첫 시도 committed로 완료됐다. FTS 20건·벡터 4건, 검색/원문 검증 약 1.87초, CRG 약 4.88초, DB 요청 생성→완료 약 12.1초다. 근거 12개와 사회적 맥락 2개를 UI에서 확인했고 이번 응답에는 검색 축 사용 불가 경고가 없었다. 자세한 물리 호출/시각 해상도/trace 생략 한계는 workspace `.task-output/search-startup-20260915/run-01/real-ai-summary.json`에 있다.

Windows 고유 137개 통과(최초 취소 실패 1개 단독 재시험 PASS), Linux 131개 통과/7개 사유 있는 skip, 현재 inventory/구조 정책 PASS. 추가 전체 역사 보존 검사는 기존 factory/API/ORM/테스트 도입 이력 차이로 FAIL이므로 전체 CI PASS로 표시하지 않는다. 증거는 workspace `.task-output/search-startup-20260915/run-01/validation.md`, 완료 계획은 workspace `docs/plan/09-15 Docker 채팅 검색 프로세스 기동 지연 해소와 경량 진입점 구현 세부 계획.md` §14다.

양축 장애의 오류 UI와 근거 중복 정책은 유지한다. 상세 수집의 자동 만료/재시작 휘발성도 유지한다. 다음 사용자 작업은 현재 Docker에서 일반 사용과 응답/근거를 직접 확인하는 것이며, 설치판·CI·merge·release는 별도 Gate다.

### 2026-09-17 F2 실행 결과

**F2는 실제 CRG 14회 실행 완료이며 품질 전체 통과는 아니다.** 격리 SQLite의 실제 생각 절단·성공 저장·episode apply·원문/생각 조회를 거친 입력에서, 정상 인용 2/2·보존된 생각 활용 2/2·없는 환불 문장 인용 회피 4/4를 확인했다. 하지만 잘린 생각의 과거 경험 창작, 미기록 생각의 사후 확정, 현재 자료 누락을 당시 미기록으로 설명하는 오류가 남았다. 날짜 항목 일부는 공연 예정일과 취소 통보일이 구분되지 않는 시험 자료 한계 때문에 평가 유보했다.

기존 gemini-3.1-flash-lite/high와 CRG 지침을 유지했다. 물리 생성 14회, 재시도 0회, 검색·임베딩·정리 AI 0회. CRG 평균 1.78초·중앙값 1.72초이며 브라우저 전체 응답시간이나 자원 비교 수치가 아니다. 제품 코드·프롬프트·기본값을 변경하지 않았다. 남은 미실행은 F1·F3·F4이고 F2 품질 이슈는 별도로 남긴다. 이전 2026-09-16의 4건 미실행 기록은 당시 이력으로 보존한다. 상세 결과는 workspace `.task-output/episode-f2-20260917/report.md`, 전체 응답·생각은 `responses.md`를 따른다. 이번 작업은 커밋·푸시하지 않았다.

### 2026-09-17 사용자 결정 — F2 실패 기록 유지·낮은 우선순위로 후속 조사

사용자는 이번 실패를 기록만 남기고 중요도를 낮게 두며, 추후 추가 조사 후 해결하기로 결정했다. 요청에 적힌 F1은 대화에서 검토한 생각 잘림·원문 누락 실패 사례인 **F2**를 가리키는 것으로 반영했다. 별도 F1(오늘 SNS 활동 이유 질문)의 상태를 변경한 결정은 아니다.

- 상태: **F2 시험 실행 완료 / 알려진 응답 품질 문제 기록 유지 / 중요도·우선순위 낮음 / 추가 조사·해결 보류**.
- 이번 표본에서 누락·잘림 처리와 응답 반환은 정상 작동했다. 일부 모델 응답이 없는 과거 경험·생각·누락 이유를 만들어낸 사실과 원본 응답은 보존한다.
- 기존 실패를 성공으로 재분류하거나 해결 완료로 기록하지 않는다. 모델 성능과 CRG 지침 등의 영향은 아직 분리 검증하지 않았으며 추후 조사 대상으로 둔다.
- 현재 채택한 구조·기본값을 유지한다. 이 품질 이슈의 즉시 해결을 다음 검증의 선행 조건으로 두지 않는다.
- 이번 결정에 따라 추가 유료 시험, 모델·프롬프트·제품 코드 수정은 진행하지 않는다. 미실행 F1·F3·F4는 별도 상태를 유지한다.

### 2026-09-17 F1 사용자 실사용 1회 확인

12:47 질문의 실제 요청 `[로컬 요청 식별자 비공개]`를 분석했다. **F1 실사용1회 기대 응답 충족**: 12:42 성공 게시글에 연결된 생각143자가 당시 고정 근거에 포함됐고, CURRENT_CONTEXT 답변의 공유 이유 및 ‘함께하는 구조’가 기록과 일치했다. 라우터1+CRG1 총2회, 재시도0회, 장기기억 검색·임베딩0회다. 사용자 메시지 기록→답변 기록4.322초, 라우터2.255초·CRG1.579초, 나머지합계약0.488초. 총보고11,894토큰. 당시 브라우저 전체시간·CPU/RSS는 미측정이므로 추정치로 대체하지 않는다.

이전 F1 미실행 기록 이후 처음 확인한 표본이며 반복 안정성 전체 통과는 아니다. 현재 상태는 F1 실사용1회 확인, F2 낮은 우선순위로 실패 기록·조사 보류, F3·F4 미실행이다. 상세 근거는 workspace `.task-output/episode-f1-20260917/report.md` 및 `request-analysis.json`을 따른다. 추가 AI 호출·제품 코드 수정·커밋 없이 읽기 전용 분석과 문서 기록을 수행했다.

### 2026-09-17 사용자 확정 — F1 구조·기능 작동 기준 PASS

**F1 테스트 통과(PASS), 완료로 기록한다.** 검증 범위는 실제 사용자의 게시글 이유 질문 1회에서 **일일 기억 정리 전에도 오늘 SNS 성공 활동에 연결된 생각을 조회·전달하고, 그 작성 이유를 최종 응답으로 설명하는 구조와 기능이 작동함**이다. 근거는 12:42 게시글의 저장된 생각과 12:47 실사용 요청 `[로컬 요청 식별자 비공개]`의 고정 근거·답변 대조다.

사용자가 주석으로 제시한 6개 시험 유형 중 이번에 직접 확인한 것은 ① 게시글 작성 이유다. ② 댓글 이유, ③ 댓글 당시 상황 해석, ④ 전달 의도, ⑤ 마음/감정, ⑥ 두 활동의 생각 구분을 각각 별도 조건으로 모두 시험한 것은 아니다. 기존 질문의 답변에 일부 의미가 포함됐다고 이를 별도 시험 통과로 세지 않는다.

또한 SNS 활동이 에피소드(상황) 기억으로 만들어질 수 있는 모든 활동·상호작용·묶음 조건의 생성 및 이후 회상을 이번 F1으로 검증한 것은 아니다. 이번 경로는 **오늘 SNS 문맥 → 저장된 생각 → CURRENT_CONTEXT 응답**이며 **SNS → 일일 정리 → 에피소드 생성·검색·회상 전체 경로**의 포괄 시험과 구분한다.

이는 모든 SNS 상황의 정확도·반복 안정성 보장이나 일반 성공률 100%를 의미하지 않는다. 다만 사용자 결정에 따라 이 범위 한계를 F1 미완료 사유로 남기거나 추가 반복 시험을 F1 통과의 필수 조건으로 요구하지 않는다. 확대 검증은 필요할 때 별도 후속 과제로 다룬다.

현재 상태: **F1 PASS·완료(구조·기능 작동 범위), F2 실행 완료·낮은 우선순위로 실패 기록 및 조사 보류, F3·F4 미실행**. 과거 미실행/1회 확인 기록과 원본 측정값은 당시 이력으로 보존한다. 이번에는 문서 판정만 갱신했으며 제품 코드·프롬프트·DB 변경, 추가 AI 호출, 커밋은 수행하지 않았다.

### 2026-09-17 사용자 결정 — F3 체감 속도 수용·반복 측정 생략

**F3: 사용자 체감 속도 수용 확인, 별도 반복 측정은 생략.** 사용자 직접 질문에서 서버 메시지 기록→답변 기록 약4.32초를 확인했고, 사용자는 질문 제출부터 답변을 보기까지 약5초로 체감했으며 수용 가능하다고 판단했다. 이에 따라 F3 반복 측정을 진행해야 할 필수 잔여 작업에서 제외한다.

이는 브라우저 제출→첫 표시→완료를 계측해 반복 시험을 통과했다는 뜻이 아니다. 첫 표시/완료의 독립 시각, 검색·무검색별 브라우저 p50/p95는 측정하지 않았다. 이전 검색 포함 시간 기록은 참고 근거로만 유지하며 새 구조의 검색 경로 전체 체감 시간을 이번 무검색1회로 입증하지 않는다. 속도 편차가 실제 사용에서 문제가 되면 별도 재측정을 검토한다.

현재 후속 상태: **F1 PASS·완료(구조·기능 작동), F2 실패 기록 유지·낮은 우선순위로 조사 보류, F3 사용자 체감 속도 수용 확인·별도 반복 측정 생략, F4 미실행**. 이전 F3 미실행 문구는 당시 이력이다. 이번 작업은 문서만 갱신했고 추가 AI 호출·제품 코드/설정 변경·커밋은 하지 않았다.

## 2026-09-17 F4 단독 채팅 기준 기록

상태: **단독 채팅 기준 1회 기록 완료 · 실제 AI 기억 정리와 채팅의 동시 실행 비교는 미실행**. 사용자 직접 조작에 의한 실사용이며, 사용자 체감 시간과 서버 기록을 구분한다.

- 캐릭터: 미도리야 이즈쿠. 모델: gemini-3.1-flash-lite / high.
- 시험 유형: 오늘 게시글의 작성·공유 이유 확인(실사용 원문은 로컬 증거에만 보관).
- 사용자 체감 제출→응답: **약 5초**. 브라우저 계측값이나 반복 측정 평균이 아니다.
- 서버 메시지 저장 시각: 사용자 2026-09-17 13:07:29.624219 KST → 캐릭터 13:07:34.744429 KST, **5.120210초**. 브라우저 네트워크·렌더링 시간은 포함 여부를 확인할 수 없다.
- 라우터 3.128초 + CRG 1.593초 = AI 구간 4.721초. 나머지 약 0.399초는 문맥 준비·조회·검증·저장 등 합산 잔여 시간이며 세부 단계별 실측으로 분해하지 않는다.
- CURRENT_CONTEXT / committed. 물리 AI 호출 2회(라우터 1 + CRG 1), 재시도·repair 없음. FTS5·Vec1·RRF·질문 임베딩은 실행하지 않았다.
- 입력 11,157토큰, 출력 204토큰, 보고된 reasoning/thought 632토큰, provider total 11,993토큰. CRG thought_token_count는 null이며 이를 0으로 단정하지 않는다. 모델의 reasoning 토큰은 제품의 저장된 캐릭터 생각 필드와 다르다.
- 오늘 SNS 근거 1개 706자에 저장된 자기 생각 143자가 포함됐음을 원본과 대조했다. 응답의 사각지대 관찰·함께하는 구조·공유를 통한 팀 대비라는 이유는 저장된 생각의 취지와 일치한다.
- 요청 구간과 겹치는 memory_maintenance_jobs 실행 기록은 전체 scope 조회 결과 0건이다. 사용자가 요청한 기억 정리 없는 기준 표본으로 기록한다. CPU·메모리·I/O의 동시 수집은 없으므로 자원 수치를 소급해 산출하지 않는다.
- 요청 ID: [로컬 요청 식별자 비공개]. 서버 메시지 ID 184 → 185.
- 다음 비교는 같은 모델·질문 및 CURRENT_CONTEXT 경로인지 확인하고, 실제 정리 AI 실행 구간과 겹쳤는지 검증한다. 이 표본은 하이브리드 장기기억 검색 경로의 기준값이 아니다. 이후 대화 맥락 차이와 모델 변동 때문에 1회 차이를 곧바로 정리 부하로 단정하지 않는다.

근거: workspace `.task-output/episode-f4-baseline-20260917/request-analysis.json`, `report.md`. 이번 기록 작업은 읽기 전용 DB 확인과 문서 갱신만 수행했으며 추가 AI 호출·제품 코드/DB 수정·커밋은 하지 않았다. F1/F2/F3 판정은 유지한다.
## 2026-09-17 F4 사용자 동시 실행 시도 결과

판정: **채팅 정상 완료·정리 AI 2건 완료 확인 / 실제 AI 호출 동시 실행 조건 불성립, F4 통과 미판정**.

KST 시간 순서:
- 정리 작업 1: 13:16:03.798587~13:16:08.633071, succeeded. AI 호출 시작 13:16:03.922064, 지연 4.649초, 물리 호출 1회, episode_selection_completed.
- 사용자 채팅: 13:16:12.869266~13:16:18.148168, 5.278902초, CURRENT_CONTEXT / committed. 요청 [로컬 요청 식별자 비공개], 메시지 186→187.
- 정리 작업 2: 13:16:18.826993~13:16:26.048284, succeeded. AI 호출 시작 13:16:18.905534, 지연 7.110초, 물리 호출 1회, episode_selection_completed.

첫 정리 종료 후 약 4.24초 뒤 채팅이 시작됐고, 채팅 종료 후 약 0.68초 뒤 다음 정리가 시작됐다. 예약 정리 흐름 사이에 채팅이 들어간 것은 확인되나, 실제 정리 AI와 채팅 처리 구간은 겹치지 않았다. 이 순서는 채팅 우선 정책과 양립하지만, 이 타임라인만으로 해당 정책이 다음 작업을 실제 지연시켰다는 인과까지 확정하지 않는다.

| 항목 | 단독 기준 | 이번 시도 |
|---|---:|---:|
| 서버 메시지 저장 간격 | 5.120초 | 5.279초 |
| 라우터 | 3.128초 | 3.470초 |
| CRG | 1.593초 | 1.483초 |
| 기타 합산 잔여 | 0.399초 | 0.326초 |
| 채팅 물리 AI 호출 | 2회 | 2회 |

차이는 약 +0.159초(+3.1%)지만 각 1표본이며 실제 AI 동시 부하가 아니므로 정리 때문에 느려졌다고 판단하지 않는다. 재시도·repair 없음. 채팅 입력 11,198토큰, 출력 260토큰, 보고된 reasoning 702토큰, provider total 12,160토큰. CRG reasoning null은 0으로 단정하지 않는다. 정리 AI 호출 2회는 채팅의 2회와 구분한다.

답변은 사각지대 관찰, 함께하는 구조, 팀 대비를 위한 공유라는 저장된 생각의 취지와 일치한다. 오늘 SNS 근거 1개 및 저장된 생각 연결 확인. FTS5·Vec1 검색 경로 시험은 아니다. CPU/RSS/I/O와 브라우저 제출→표시 시간은 이번에 수집하지 않았다. 추가 projection 작업 2건은 조회 당시 pending이며 정리 AI 성공을 모든 후속 인덱스 갱신 완료로 확대하지 않는다.

근거: workspace `.task-output/episode-f4-concurrent-20260917/request-analysis.json`, `maintenance-analysis.json`, `report.md`. 재시험하려면 실제 정리 AI 진행 중에 채팅이 시작돼야 한다. 이번 확인은 읽기 전용 조회이며 추가 AI 호출·코드 변경·커밋을 수행하지 않았다.


## 2026-09-17 MS0~MS14 구현 및 F4 실제 AI 동시 실행 결과

예약 날짜 차단 제거와 현재 캐릭터의 **지금 기억 정리**를 로컬 브랜치에 구현했다. 수동·예약·정상 종료는 durable receipt와 기존 worker/자료 처리 이력/재시도 예산을 공유한다. 실행 중 변경을 자동 동기화하던 Docker 개발 watch를 통해 embedded v14 / 20260917_0094까지 반영됐다. main merge·push·commit·CI·native 설치판 검증은 진행하지 않았다.

F4 판정: **실제 AI 정리와 실제 채팅의 겹침 성립·양쪽 저장 완료, 동시 실행 기능 PASS(각 조건 1회)**. 기존 사용자의 수동 시도에서 겹침이 없었던 결과를 바꾸는 것이 아니라, 별도 격리 DB에서 수행한 후속 시험이다.

| 항목 | 단독 채팅 | 정리와 동시 채팅 |
|---|---:|---:|
| 서버 workflow 전체 | 5.075초 | 4.085초 |
| 첫 delta 이벤트 | 5.030초 | 4.042초 |
| router provider | 2.928초 | 2.479초 |
| CRG provider | 1.616초 | 1.376초 |
| 채팅 물리 AI 호출 | 2회 | 2회 |
| 완료 | committed | committed |

정리 provider 구간은 UTC 05:26:28.398616~05:26:33.475644, 동시 채팅 서버 구간은 05:26:28.433190~05:26:32.495666이었다. router와 CRG가 실제 정리 AI와 모두 겹쳤다. sleep으로 실제 AI 시간을 늘리지 않았다. 수동·예약·종료 정리는 각각 기억1개를 저장했고 반복 요청은 추가 AI 0회, 이번 전체 실제 AI는 7회다.

두 채팅은 CURRENT_CONTEXT 경로의 별도 동일조건 입력이었다. 이 결과는 브라우저 제출→표시 시간 또는 FTS5/Vec1 검색 부하 측정이 아니다. CPU는 채팅 실행창의 전체 시험 프로세스 누적 차이 0.558초/0.218초이고, RSS는 누적 high-water 269.09/286.46MiB다. 정리만의 순수 자원량·운영 컨테이너 전체·p95를 측정한 것이 아니다. 표본이 1쌍이므로 동시 실행이 더 빠르다거나 모든 부하에서 지연이 없다고 결론 내리지 않는다.

현재 후속 상태: **F1 구조·기능 PASS / F2 실패 기록·낮은 우선순위 조사 보류 / F3 사용자 체감 수용·반복 측정 생략 / F4 실제 AI 동시 실행 기능 PASS·대규모 반복 성능 미측정**. 저장된 backend inventory의 검사와 현재 소스 검사도 구분한다. 새 inventory에서 검출된 2개 package cycle은 HEAD에도 동일하게 존재하며 별도 해소 대상이다.

자세한 운영 계약은 `docs/operations/memory-consolidation-scheduling.md`, workspace 실행 근거는 `.task-output/memory-scheduling-20260917/implementation-report.md`, `live-result.json`, `finish-result.json`, `architecture-audit.json`에 있다. 실사용 USER CHECK로 표기하지 않는다.


## 2026-09-17 15:08 F4 USER CHECK — 실제 동시 실행 PASS

준비 상태 정체 수정 후 사용자가 수동 정리를 실행하고 채팅2건을 직접 보냈다. read-only 운영 기록에서 실제 기억 정리 AI와 겹침을 확인했다. 첫 채팅15:08:08~15:08:13.760은 정리 AI15:08:05.761~15:08:18.471 안에 전체 포함된다. 두 번째 채팅15:08:27~15:08:33.764도 정리 AI15:08:23.878~15:08:28.900과 일부 겹쳤다(모든 시각 KST).

두 채팅 모두 committed, router+CRG 각2회/repair0회. 서버 DB 시각 차이 약5.76초/6.76초이며 created_at 초 단위의 근사값이다. 첫 router3.449초/CRG1.735초, 두 번째 router4.577초/CRG1.556초. 정리는 job2개 모두 완료·실제 AI3회·새 기억3개·남은 경험0개, 수락부터 완료 약40.009초였다. 이번 사용자 실행의 총 AI7회와 앞선 격리 시험7회는 서로 다른 실행이다.

**F4 기능 기준은 USER CHECK PASS**로 기록한다. 실제 동시 실행·채팅 정상 완료·정리 지속/저장·정상 호출 수 유지를 확인했다. 자원 sampler 미수집으로 이번 CPU/RAM/I/O 정량값은 없으며, 검색 경로/대규모 반복 부하와 브라우저 paint 시간을 검증한 것은 아니다. 앞선 격리 시험·겹침 불성립·준비 버그 이력은 보존한다. F2/F3 상태는 유지한다.

상세: workspace `.task-output/episode-f4-usercheck-20260917/report.md`, `result.json`. 이번 로그 분석은 신규 AI 호출·제품 코드/DB/설정 변경·commit/push/main merge 없이 수행했다.

## 2026-09-17 사용자 결정 — F1~F4 수용 기준 PASS 확정

사용자는 F4 실제 사용자 동시 실행 기능 PASS를 포함해 F1·F2·F3도 사용자 판단상 통과로 기록하도록 결정했다. **F1~F4의 최종 사용자 수용 판정은 모두 PASS**다. 기존 추가 기록을 유지하라는 요청에 따라, 이 결정은 과거의 개별 실패·미측정·평가 유보를 수정하거나 없애지 않는다.

| 항목 | 통과의 의미 | 계속 보존하는 한계·추가 확인 |
|---|---|---|
| F1 | 일일 정리 전 오늘 게시글의 저장된 생각으로 작성 이유를 설명하는 구조·기능 작동 | 댓글·답글·다른 SNS 유형, 에피소드 생성/회상 전체 및 반복 안정성의 포괄 검증은 미실행 |
| F2 | 생각 잘림·원문 누락 상태에서도 처리·응답이 작동하며 알려진 품질 문제를 사용자가 수용 | 없는 과거 경험·생각·누락 이유를 지어낸 개별 실패와 평가 유보 유지. 원인 조사·개선은 낮은 우선순위로 남김 |
| F3 | 사용자 체감 약 5초를 수용해 속도 기준 통과 | 반복 브라우저 계측은 생략. 제출→첫 표시→완료 및 p50/p95를 측정한 PASS로 해석하지 않음 |
| F4 | 사용자가 실행한 채팅 2건과 실제 정리 AI의 겹침, 채팅 및 정리의 정상 완료 확인 | CPU/RAM/I/O·반복 부하·검색 동시 실행 성능은 미측정. 앞선 타이밍 불일치·준비 정체 오류·수정 및 재검증 기록 유지 |

추가 확인 사항은 수용 판정 후에도 남기는 품질·성능 검증 항목이다. F2 실패가 해결됐거나 모든 상황·자원·설치 환경의 기술적 검증이 끝났다고 표기하지 않는다. F1·F4 직접 USER CHECK, F2 agent-run 결과에 대한 사용자 수용, F3 체감 수용 및 반복 측정 생략을 구분한다. 코드·DB·프롬프트·기본값 변경, 신규 AI 호출·시험, commit/push/main merge는 이번 문서 갱신에서 수행하지 않았다.

판정 기록: workspace .task-output/episode-followup-acceptance-20260917/report.md. F1·F2·F4 원본 시험 보고서와 응답·진단 파일은 변경하지 않았다.
