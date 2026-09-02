# P8-L-P Evidence Bundle·Character Response Generator streaming 계약

P8-L-P는 P8-L-J~N의 durable generation·Router·전문 Planner·BOTH 기반을 실제
World Chat message route에 연결한다. 한 사용자 메시지는 먼저 canonical 저장되고,
코드가 route별 retrieval을 실행해 immutable `evidence-bundle.v1`을 고정한 뒤
Character Response Generator(CRG)를 generation attempt당 최대 한 번 호출한다.
사용자에게 공개되는 generation delta는 검증된 CRG 답변 문자열뿐이다.

## ownership

```text
domains/chat
  request·generation fence, Evidence Bundle, response orchestration,
  public event protocol, assistant atomic commit,
  World thread model binding(default / thread_override)

domains/memory
  canonical/FTS retrieval과 successful Chat candidate lifecycle

domains/relationships
  graph primitive·execution·canonical revalidation

integrations/llm
  Retrieval Router, Canonical Planner, Graph Planner, CRG provider adapters,
  provider-family thinking resolver

runtime/chat
  SQLAlchemy identity/policy composition, NDJSON route,
  successful-response after-commit Memory producer

features/chat
  composer, 300ms delayed single typing presence, CRG delta,
  typed failure·explicit retry·terminal rehydrate,
  World thread model selector and optimistic rollback
```

Chat domain/application/ports는 FastAPI, SQLAlchemy, provider SDK와 runtime을
import하지 않는다. actual owner·World·WorldCharacter·source ID와 permission,
query execution, commit은 코드가 소유한다. CRG는 route를 다시 고르거나 query를
계획·실행하지 않고, 고정된 Evidence Bundle과 recent context로 Character 문장만 쓴다.

## request flow

```text
POST message
→ current thread binding에서 effective model resolve
→ user message + accepted response request + immutable model snapshot commit
→ GET NDJSON events
→ lease + accepted event
→ Retrieval Router
→ route별 Canonical / Graph / BOTH typed workflow
→ canonical revalidation
→ deterministic Evidence Bundle freeze
→ CRG exactly once
→ verified CRG text delta only
→ assistant message + response metadata + committed request atomic commit
→ separate provider-free Memory candidate proposal
→ completed event
```

정상 full-path 논리 호출 상한은 `CURRENT_CONTEXT 2`, `CANONICAL 3`, `GRAPH
3`, `BOTH 4`, `CLARIFICATION 2`다. 모든 경로는 CRG logical call을 정확히
하나 포함한다. request-wide Router/Planner schema repair는 최대 하나이며, explicit
retry는 같은 user message와 response slot을 사용하되 새 request·generation·attempt와
새 full-path budget을 가진다.

## World thread model binding

World Chat thread의 모델 선택은 `default`와 `thread_override` 두 상태만 가진다.
`default` thread는 Local 제품 설정의 현재 기본 모델을 따르고, 설정이 바뀌면 다음
요청 수락 시 새 기본 모델을 snapshot한다. `thread_override` thread는 사용자가 채팅방
header에서 고른 모델을 유지한다. 채팅방 selector의 `기본 모델 사용`은 override를
해제하고 현재 기본 모델로 되돌린다.

실행 중인 generation이 있으면 model PATCH는 `409`로 거절된다. UI는 pending,
streaming, retry 중 selector를 disable하고, model PATCH 실패 시 이전 선택으로
rollback한 뒤 `모델을 바꾸지 못했어요.`와 명시적 재시도를 제공한다. 모델 변경은
실패한 응답을 자동 재시도하지 않는다.

요청이 accepted된 뒤 `chat_response_requests.selected_model`은 immutable하다. 설정이나
thread binding이 이후 바뀌어도 그 request와 diagnostic은 수락 당시 모델을 가리킨다.
명시적 `[다시 시도]`는 새 request·generation·attempt를 만들므로 재시도 시점의 현재
binding으로 effective model을 다시 resolve하고 새 snapshot을 저장한다.

## provider-family thinking compatibility

provider adapter는 모델 이름을 코드가 소유하는 closed family로 분류한다.

- Gemini 3는 `thinkingLevel`만 사용한다.
- Gemini 2.5 Flash / Flash-Lite의 low thinking은 `thinkingBudget: 0`을 사용한다.
- Gemma 계열에는 Gemini thinking config를 보내지 않는다.
- 알 수 없는 family는 provider I/O 전에 fail closed한다.

structured JSON을 요구하는 Router·Planner와 text를 생성하는 CRG 모두 같은 resolver를
사용한다. provider 실패의 durable diagnostic은 node, provider, accepted model,
normalized failure class, provider status/code/error hint, retryable 여부의 bounded
allowlist만 저장한다. API key, prompt, raw provider body와 stack trace는 저장하거나
사용자 stream에 노출하지 않는다.

## Evidence Bundle

`evidence-bundle.v1`은 request ID, scope hash, route, retrieval outcome,
canonical/graph에서 재검증된 item, partial/degraded 상태와 clarification slot의
immutable snapshot이다. 최대 item은 12개, item당 2,000자, 전체 8,000자다.
코드는 normalized text로 dedupe하고 최신순·stable tie-break로 정렬하며 cap을
적용한다. provider payload에는 bounded prose와 opaque reference만 들어가고 actual
canonical source ID는 들어가지 않는다. metadata는 bundle version, deterministic
hash, capability, outcome, partial axis를 저장한다.

no evidence·Memory OFF·projection outage는 존재하지 않는 과거를 보충하지 않는다.
허용된 degraded/no-evidence 상태를 frozen bundle에 표시하고 CRG가 자연스럽게
모른다고 답하게 한다. unsafe·hidden·deleted·blocked·cross-World·unobserved source는
bundle에 들어가지 않는다.

## public stream and UI

protocol은 `chat-generation-stream.v1`, transport는 `application/x-ndjson`이다.
event identity는 request scope, generation ID, attempt number, monotonic sequence로
fence된다. 공개 event는 `accepted`, `delta`, `completed`, typed `failed`,
`cancelled`만 허용하고 `delta` payload key는 `text` 하나뿐이다. Router·Planner
JSON, SQL/graph 결과, raw Evidence Bundle, provider 오류 원문과 reasoning은 공개하지
않는다.

현재 direct provider adapter는 provider 응답 전체를 받은 뒤 safety·shape를 검증하고
최대 48자 transport delta로 나눈다. 따라서 사용자 화면은 점진적으로 갱신되지만,
이 단계는 provider-native token streaming을 구현했다고 주장하지 않는다. 이 순서는
검증 전 partial output을 노출하지 않고 Evidence Bundle을 streaming 중 immutable하게
유지한다.

frontend는 request가 300ms 이상 pending일 때만 Character의 단일 `입력 중` presence를
보인다. 첫 CRG delta, terminal, thread switch에서 즉시 숨기며 backend artificial delay는
없다. user message save 실패의 `[다시 보내기]`와 assistant generation 실패의
`[다시 시도]`는 별도 state다. retry는 latest retryable failure만 허용하고 같은 user
message를 복제하지 않는다. committed terminal delivery가 유실되면 canonical assistant
message를 hydrate하며 CRG를 다시 호출하지 않는다.

## commit and Memory isolation

assistant message, typed response metadata, request terminal state는 fenced transaction으로
원자 commit된다. partial·failed·cancelled response는 assistant row도 Memory candidate도
만들지 않는다. successful commit 뒤 runtime producer가 responding WorldCharacter scope의
committed assistant `CHAT_MESSAGE`를 `AUTOBIOGRAPHICAL_EVENT` candidate로 provider 없이
제안한다. Memory OFF이면 write는 0이고, 같은 source replay는 기존 candidate를 재사용한다.
candidate producer·queue·projection 실패는 이미 성공한 Chat commit을 rollback하지 않는다.

## retry and recovery

- send idempotency key는 user message와 first request를 중복 없이 replay한다.
- explicit retry는 같은 user message·stable response slot, 새 generation·attempt를 쓴다.
- late old-generation event와 scope·attempt·sequence mismatch는 적용하지 않는다.
- terminal request 재조회는 committed assistant 또는 typed failure를 반환한다.
- partial stream text는 transient UI state이며 다음 context와 Memory source가 아니다.
- credential/config/policy failure는 retry button 대신 typed recovery CTA를 사용한다.

## non-scope

이 Hotfix는 `message_threads.model_binding_mode` 하나만 추가한다. Alembic
`20260903_0087`과 Embedded SQLite v7은 기존 thread를 deterministic하게
`default` 또는 `thread_override`로 backfill하고, unknown model은 fail closed한다.
기존 실패 request의 accepted `selected_model` history는 다시 쓰지 않는다. v6→v7은
copy-on-write, manifest digest, rollback 및 installer supported-upgrade fixture 계약을
유지한다. 새 canonical table이나 LadybugDB generation은 추가하지 않는다.

Memory read/inspector와 owner ON/OFF·pin·correction·delete UI는 P8-L-Q/R, held-out
quality·warm/cold latency·cross-runtime user Gate와 전체 causal closeout은 P8-L-S가
소유한다. merge, release와 Production도 별도 사용자 Gate다.
