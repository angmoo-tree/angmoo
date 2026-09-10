# 채팅 회상 진단

채팅의 **검색 진단 · 문제 해결**을 펼치면 해당 대화의 최신 요청 또는 이전 응답에 저장된 조회 과정을 볼 수 있다. Docker 기여자 환경과 static/Tauri는 같은 Chat 컴포넌트와 공통 백엔드를 사용한다. 진단은 추가 AI 호출이나 검색을 실행하지 않는다.

## 읽는 순서

1. `router`: 실제 선택한 경로. CURRENT_CONTEXT/CLARIFICATION은 검색 미선택이며 검색 실패와 다르다.
2. `planner`와 `step`: 검증된 계획, repair 여부, 실제 실행/의존성 때문에 건너뜬 단계. step의 queries는 primitive 호출 수이며 내부 SQL 문 개수는 아니다.
3. `search`: 실제 FTS5, SQLite fallback, canonical direct, graph projection/canonical fallback. FTS 후보 수와 최종 원본 재검증 결과는 다른 단계다.
4. `validated_result`/`revalidation`: 후보·검증 후 결과·관측 가능한 제외 사유. DB WHERE에서 이미 제외된 행 수는 별도 COUNT 조회를 하지 않으므로 기록하지 않는다. 없는 수치는 0으로 해석하지 않는다. Graph 결과는 관계·근거·노드 등 서로 다른 단위를 포함한다.
5. `both_merge`: 실행 recipe, 병렬 여부, 의존성 중단, 중복·join 제외. 병렬 관측은 CANONICAL 다음 GRAPH 순서로 합쳐 표시한다. 전체 시간순 로그가 아니다.
6. `evidence_deduplication`/`evidence_limit`/`today_selection`: 실제 조립·상한 적용·Today SNS 추가. `crg_input`과 `evidence_kind`가 최종 답변 생성 서비스에 전달한 근거다. 모델이 이를 정확히 활용했다는 보장은 아니다.

요청 상태가 failed/cancelled이거나 중간 단계까지만 있으면 부분 기록이다. `not_recorded`는 도입 전 요청, 기록 실패 또는 정리된 기록일 수 있으며 0 hit가 아니다. `expired`는 아직 남은 행의 만료를 감지한 상태다. 이미 보관 정리로 삭제된 행과 애초에 생성되지 않은 행을 구분하기 위해 영구 tombstone을 추가하지 않는다. `omitted_events`가 있으면 이벤트 상한으로 일부 관측이 생략된 것이다.

## 저장과 개인정보 경계

- 기본: `chat_retrieval_diagnostics`에 versioned JSON. 최대 16KiB/요청, 1,000행, 7일. 다음 쓰기 때 만료/개수 정리를 수행한다. 앱이 꺼져 있는 동안 파일을 물리적으로 지우는 별도 서비스는 없다. 요청 복구 metadata와 분리하며 기존 checkpoint의 SAVEPOINT로 저장한다. 토큰마다 별도 commit하지 않는다.
- 기본 필드: 코드가 정한 경로/operation/상태/이유 코드, 수치와 조건 적용 여부. 질문, 검색어, 메시지·기억 본문, canonical ID, API key, provider raw exception/추론 원문은 넣지 않는다.
- 상세: owner+World+thread에서 명시적으로 켠 뒤 접수되는 다음 10요청 또는 30분. 프로세스 메모리에서만 보관하며 결과는 최대 60분, 20건, 전체 1MiB, 요청별 64KiB이다. TTL은 접근할 때 정리하며 재시작/OFF로 소멸한다. admission snapshot을 사용하므로 실행 도중 켜도 이미 접수된 요청을 소급 수집하지 않는다.
- 상세에는 실제 검색어와 제한된 조건이 포함될 수 있다. 명시적 **상세 진단 파일 저장**만 로컬 파일을 만든다. 다운로드한 복사본은 사용자가 관리한다. 기본 진단, SSE, World Package, 일반 evidence DTO에 상세 값을 넣지 않는다.
- 읽을 때 현재 대화 owner/World/참여자 접근을 재검증한다. 다른 owner·World·thread는 접근할 수 없다. 접근 권한이 사라진 기록은 읽을 수 없으며 기본 보관 정리/상세 TTL도 적용된다.
- migration `20260910_0091`, embedded SQLite v11은 빈 진단 테이블만 추가한다. 기존 요청의 조회 내용을 복원하지 않는다. 기본 진단은 기존 사용자 DB에 있는 로컬 runtime 데이터이며 배포 artifact에 사용자 DB가 포함되는 것은 아니다.

## Docker에서 기본 진단 읽기

브라우저에서 현재 대화의 진단을 보는 방법을 우선 사용한다. HTTP API는 기존 local frontend origin/owner 인증을 그대로 요구한다.

`GET /api/v1/worlds/{world_id}/chat/threads/{thread_id}/diagnostics?request_id={request_id}`

`PUT .../diagnostics/capture` body `{"enabled":true}`로 해당 대화의 상세 수집을 켠다. `false` 또는 DELETE는 해당 scope의 상세 admission과 결과를 지운다.

컨테이너의 실제 active generation DB 경로를 확인한 뒤, 기본 진단만 읽는 read-only 도구도 사용할 수 있다:

```powershell
docker compose -f compose.yml -f compose.dev.yml exec -T backend python /workspace/scripts/diagnostics/read_chat_retrieval_diagnostics.py --database <실제-active-generation-DB-경로> --request-id <request-id>
```

도구는 `mode=ro`와 `query_only=ON`으로 열고 진단 테이블만 조회한다. 임의의 오래된 generation을 현재 DB로 간주하지 않는다. 설치형 Windows의 DB를 조사할 때에는 별도의 물리적 설치 식별 절차를 먼저 수행한다.

## 구조와 검증 원칙

관측 계약은 `app/contracts/retrieval_observation.py`, Chat 저장/권한/API는 Chat 도메인, 실제 검색 관측은 기존 memory/relationships와 runtime adapter가 소유한다. 저장소나 logger가 재검색하지 않는다. UI는 `features/chat`의 기존 World Chat에 조합한다. hosted reference 분류는 **LOCAL**이며 기존 semantic Button·색상 token을 사용한다.

자동 검증은 합성 데이터/fake provider를 사용한다. 실제 질문에 대해 올바른 기억을 찾아 답변하는지와 자연어 Router가 어느 경로를 선택하는지는 별도의 USER CHECK다. 진단 기능 통과를 회상 품질 통과로 간주하지 않는다.
