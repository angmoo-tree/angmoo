# 사회적 맥락·하이브리드 기억 검색 로컬 실행 결과

현재 판정: **구현 및 로컬 검증 수행 / 사회적 맥락 채택 HOLD / hybrid 채택 HOLD**. 기본값은 `legacy_checkpoint`다. HY0–HY15를 모두 실행 범위에 포함했으나 모든 완료 기준이 PASS라는 뜻은 아니다. 성능의 제품 채택 기준, 실제 모델의 사실·범위 품질, 직접 사용자 검증은 닫히지 않았다. 아래의 역사적 기록은 당시 실패와 중간 결과이며 현재 상태는 이 절과 단계별 표를 따른다.

실행일: 2026-09-14 KST. 계획은 workspace의 `docs/plan/09-13 채팅 FTS5·Vec1 하이브리드 기억 검색과 Planner 없는 기억 조회 전환 로컬 구현 세부 계획.md`다. 시작 저장소는 `fix/chat-retrieval-debugging`, clean HEAD `ae9744f060b5680d59486b2474d532dadccf9bf9`였다. 새 branch/issue/PR/push/merge는 수행하지 않았다. 실행 산출물은 workspace `.task-output/hybrid-memory-20260914/`에 있고 실제 키·원래 캐릭터 설정은 저장소에 복사하지 않았다.

## 단계별 상태

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
| 맥락 답변·되묻기 | 기존 정책 | snapshot 포함, 검색 0회 | snapshot 포함, 검색/embedding 0회 |
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
