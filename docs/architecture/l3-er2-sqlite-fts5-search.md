# L3-ER2 SQLite FTS5 검색 projection 계약

상태: PR F 구현 계약, production OFF

## 1. 경계

SQLite canonical DB는 사용자 상태의 유일한 원본이고 FTS5는 언제든 지우고 다시 만들 수 있는 파생
projection이다. 검색 adapter는 canonical schema에 FTS table·trigger를 추가하지 않고 다음 별도 파일을
소유한다.

```text
<runtime-root>/search/generations/<generation>/angmoo-search.sqlite3
```

frontend·Tauri·domain use case는 이 파일을 직접 열지 않는다. `SearchIndexPort`와
`RebuildableSearchIndexPort`를 통해서만 접근한다.

## 2. 문서와 provenance

검색 문서는 다음 범위를 보존한다.

- `document_id`, `world_id`, `kind`
- 선택 `character_id`, `counterparty_id`
- canonical `source_id`, 선택 `source_event_id`
- 선택 `occurred_at`
- deterministic JSON metadata

`post`, `comment`, `event`, `memory`는 같은 index를 사용할 수 있지만 `kind`와 source provenance를
잃지 않는다. 조회 시에는 `world_id`가 항상 필수이며 character·counterparty·kind filter를 추가할 수
있다.

## 3. CJK 검색과 fallback

기본 tokenizer는 SQLite 내장 `unicode61 remove_diacritics 2`다. 한글·한자·일본어 run에는 Python에서
deterministic bigram term을 함께 만들어 부분 어절 검색을 보완한다. FTS token 결과가 없으면 동일한
World·character·counterparty·kind 범위 안에서만 정규화 문자열 substring fallback을 수행한다.

이 전략은 lexical recall 계약이지 의미 검색 계약이 아니다. 의미 검색은 별도 `VectorRecallPort`로만
정의하며 정확도·용량 근거가 생기기 전까지 adapter·embedding model·extension·container image를
추가하지 않는다.

## 4. 삭제·숨김·tombstone

canonical source가 삭제·숨김·취소·tombstone 상태가 되면 canonical transaction은 durable outbox를
함께 기록한다. projector가 그 command를 처리할 때는 하나의 projection transaction에서 해당
`document_id`를 제거하거나 `searchable=False` upsert를 전달한다. rebuild 입력도 searchable source만
포함한다. 따라서 command 적용 후 비활성 source는 query-time 사후 필터에 의존하지 않고 index에서
즉시 제외된다. outbox가 아직 처리되지 않은 짧은 구간은 상위 read use case가 canonical 상태를
재검증하며, PR F는 production read path를 아직 전환하지 않는다.

## 5. rebuild·digest·doctor

- rebuild는 `BEGIN IMMEDIATE` transaction에서 기존 projection을 교체한다.
- duplicate `document_id` 입력은 fail-closed 처리한다.
- digest는 document와 provenance를 `document_id` 순서로 직렬화한 SHA-256이다.
- doctor는 SQLite integrity, FTS5 table, metadata/FTS row count, 저장 digest와 현재 digest를 확인한다.
- drift 또는 index 손상은 canonical 손상이 아니며 canonical source에서 rebuild해 복구한다.

## 6. 현재 비범위

- production PostgreSQL·Neo4j runtime 변경
- PostgreSQL→SQLite 사용자 데이터 migration
- vector extension·embedding model·semantic ranking
- P8-L memory 정책 또는 GraphRAG 검색 전략 변경
- public release

PR F는 합성 parity corpus와 전체 회귀로 이 경계를 증명하고, production canonical switch는 ER7 사용자
승인 전까지 수행하지 않는다.
