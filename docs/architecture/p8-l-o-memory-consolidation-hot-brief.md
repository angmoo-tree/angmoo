# P8-L-O Memory consolidation·hot brief 계약

P8-L-O는 foreground Chat과 분리된 canonical Memory maintenance 경계다. 이
단계는 `memory_candidates`를 bounded batch로 다시 검증해 `memory_items +
memory_item_evidence`로 확정하고, accepted item에서 재생성 가능한
`memory_hot_briefs` cache를 만든다. P8-L-P의 Character Response Generator,
streaming과 사용자 화면, P8-L-Q/R의 Memory read·control UI는 구현하지 않는다.

## ownership

```text
domains/memory/domain
  threshold·lane·budget·digest·hot brief contract

domains/memory/application
  schedule·claim·source revalidation·accept/reject·brief rebuild·retry/drain

domains/memory/ports
  canonical consolidation repository·leased queue·UoW·optional provider

domains/memory/infrastructure
  SQLAlchemy candidate/item/brief/job translation and lease fencing

integrations/llm
  optional direct provider; summary proposal only
```

Application/domain code는 SQLAlchemy, SQLite path, provider SDK, API route를
import하지 않는다. provider adapter는 actual owner·World·Character·candidate ID,
SQL/FTS/Cypher, TTL과 permission을 받지 않는다. `candidate-1` 같은 opaque ref와
코드가 먼저 검증한 bounded deterministic summary만 받는다.

## schema와 canonical boundary

P8-L-F가 만든 다음 SQLite v6 table을 그대로 사용한다.

- `memory_scope_settings`
- `memory_candidates`
- `memory_items`
- `memory_item_evidence`
- `memory_hot_briefs`
- `memory_hot_brief_items`
- `memory_maintenance_jobs`

새 migration·Embedded schema version·LadybugDB generation은 없다. item과
evidence는 한 write operation으로 저장되며 retry는 동일 source/digest item을
중복 생성하지 않는다. hot brief는 source item ID+version set, set digest,
high-water mark, generation과 contract version을 기록하는 파생 cache다. item
accept·정정·pin·delete·expiry 또는 Memory OFF가 active brief를 invalid 처리한다.
brief replacement는 selected source ID+version을 다시 조회해 바뀌었으면
`memory_hot_brief_source_version_conflict`로 중단한다.

## v1 threshold와 bounded budget

값은 `MEMORY_CONSOLIDATION_POLICY_V1`과 generated inventory가 고정한다. 바꾸는
경우 같은 contract/inventory PR과 corpus 회귀가 필요하다.

| input/bound | v1 | 이유 |
| --- | ---: | --- |
| pending candidate count | 8 | ordinary 1회마다 maintenance/provider를 부르지 않으면서 작은 local batch 유지 |
| estimated validated summary characters | 4,000 | 장문 source가 count보다 먼저 bounded batch를 열 수 있음 |
| prior consolidation 이후 최소 간격 | 15분 | 이미 brief가 있는 저빈도 scope의 pending을 무기한 방치하지 않음 |
| invalid brief active-item refresh | 16 | hot brief가 상한에 닿기 전에 재생성 |
| candidate batch | 최대 32 | DB claim·source revalidation·provider fan-out 상한 |
| batch continuation | pending 0까지 | 32개 처리 뒤 남은 수가 임계값 미만이어도 idempotent 후속 job 생성 |
| hot brief source items | 최대 24 | prompt/context와 cache 크기 상한 |
| optional provider input | 최대 12,000자 | 대략 3K 한국어/혼합 token 수준의 input ceiling |
| provider output | 최대 2,048 token | candidate별 짧은 summary proposal ceiling |
| provider call | claimed batch당 최대 1 | hidden JSON repair·overload retry 0 |
| lease | 2분, renew 가능 | 30초 provider timeout 뒤 terminal write 여유 |
| maintenance attempt | 최대 3 | 무한 retry 금지 |
| shutdown drain | 최대 8 job + deadline | 앱 종료가 maintenance 때문에 무기한 막히지 않음 |

이 값은 provider-free SQLite fixture, 32-source/12K-character worst-case ceiling과
logical cost bound를 기준으로 한 첫 contract다. 실제 local model별 warm/cold
p50·p95, token cost와 품질 비교는 P8-L-S held-out Gate가 소유한다. live provider
benchmark를 통과했다는 의미로 확대하지 않는다.

## automatic과 immediate lane

```text
ordinary successful source
→ provider-free eligibility/candidate upsert
→ code threshold evaluation
→ threshold 전 provider 0
→ due일 때 idempotent automatic job

explicit remember request
→ 동일한 candidate/evidence boundary
→ request key 기반 idempotent immediate job
→ foreground Chat request/call tracker와 별도 budget
```

두 lane 모두 provider를 쓰더라도 한 claimed batch에서 physical call은 하나다.
adapter는 generic Direct LLM의 overload retry와 JSON repair를 모두 끈다. job retry는
새 lease/attempt로만 일어나고 `attempt_count <= 3`이다. Router, Canonical Planner,
Graph Planner, BOTH coordinator와 이후 Character Response Generator의
`RouteAwareCallTracker`를 가져오거나 변경하지 않는다.

## processing order

```text
claim + lease commit
→ enabled scope/version 확인
→ pending candidate batch
→ canonical source·World·visibility·membership·block·observation 재검증
→ invalid candidate bounded reject
→ optional provider용 opaque source envelope
→ lease renew commit
→ optional provider 최대 1회
→ provider proposal 또는 deterministic summary
→ source를 다시 읽고 item + evidence accept
→ active source item set 재조회
→ deterministic hot brief + exact version fence
→ pending tail이 있으면 idempotent batch continuation enqueue
→ job terminal + continuation atomic commit
→ existing after-commit private FTS projection
```

Provider output은 summary proposal만 소유한다. 코드는 실제 candidate mapping,
source digest, scope/version, memory kind shape, retention과 evidence를 다시
검증한다. unknown·duplicate opaque ref, invalid schema, timeout, overload와 adapter
부재는 deterministic fallback으로 degrade한다. provider failure는 successful
source, canonical item, 기본 Chat을 rollback하지 않는다.

## failure·shutdown

- Memory OFF/missing scope는 provider 0으로 claimed job을 terminal skip한다.
- source hidden/deleted/blocked/unobserved는 provider 전에 candidate를 reject한다.
- provider failure는 diagnostic code와 physical call count를 남기고 deterministic
  item·brief를 완성한다.
- canonical/brief write failure는 lease-fenced job retry로 돌아가며 세 번째 claim
  뒤 `failed`가 된다.
- 한 batch의 최대 32개를 처리한 뒤 남은 candidate는 개수가 8 미만이어도
  `batch_continuation`으로 이어서 처리하며, pending 0에서만 연쇄를 끝낸다.
- item+evidence가 이미 확정된 뒤 derived brief만 실패해도 item을 삭제하지 않는다.
- shutdown drain은 deadline과 최대 8 job 중 먼저 닿는 경계에서 멈춘다.
- plaintext credential, raw private transcript, provider body, source summary를
  application log에 남기지 않는다.

## executable Gate

- threshold 전 ordinary provider call 0
- Memory OFF provider/candidate processing 0
- automatic claimed batch provider 최대 1
- explicit immediate lane provider 최대 1, foreground budget 0
- provider failure deterministic fallback과 canonical item 보존
- source identity·World·visibility·membership·block·observation 재검증
- candidate replay item 중복 0
- brief generation·exact item-version fence·OFF invalidation
- same-scope lease, renew, stale worker fencing
- retry 최대 3, shutdown drain 최대 8/deadline
- 32개 초과 backlog의 sub-threshold tail까지 bounded continuation으로 drain
- direct adapter overload retry 0, JSON repair 0
- schema/migration/frontend/live Chat route 변경 0

P8-L-O는 background capability를 닫지만 live Chat producer·streaming과 UI를
구현하지 않는다. 실제 successful Chat source가 after-commit으로 candidate를 만들고
worker lifecycle에 연결되는 제품 경로는 P8-L-P/S에서 별도 검증한다.
