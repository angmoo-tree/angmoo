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
  public event protocol, assistant atomic commit

domains/memory
  canonical/FTS retrieval과 successful Chat candidate lifecycle

domains/relationships
  graph primitive·execution·canonical revalidation

integrations/llm
  Retrieval Router, Canonical Planner, Graph Planner, CRG provider adapters

runtime/chat
  SQLAlchemy identity/policy composition, NDJSON route,
  successful-response after-commit Memory producer

features/chat
  composer, 300ms delayed single typing presence, CRG delta,
  typed failure·explicit retry·terminal rehydrate
```

Chat domain/application/ports는 FastAPI, SQLAlchemy, provider SDK와 runtime을
import하지 않는다. actual owner·World·WorldCharacter·source ID와 permission,
query execution, commit은 코드가 소유한다. CRG는 route를 다시 고르거나 query를
계획·실행하지 않고, 고정된 Evidence Bundle과 recent context로 Character 문장만 쓴다.

## request flow

```text
POST message
→ user message + accepted response request commit
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

P8-L-P는 schema, migration, Embedded SQLite v6, LadybugDB generation을 바꾸지 않는다.
Memory read/inspector와 owner ON/OFF·pin·correction·delete UI는 P8-L-Q/R, held-out
quality·warm/cold latency·cross-runtime user Gate와 전체 causal closeout은 P8-L-S가
소유한다. merge, release와 Production도 별도 사용자 Gate다.
