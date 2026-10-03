# 다국어·사용자 시간대·Gemini SNS 통합 구현과 로컬 검증

작성·검증일은 2026-10-04 KST다. 계획 식별자와 artifact 디렉터리의 `20261003`은 시작한 계획의 날짜를 유지한다. 기준은 workspace의 [통합 구현 계획](<D:/project_code/angmoo-workspace/docs/plan/10-03 Angmoo 다국어·사용자 시간대와 Gemini SNS 스키마·누락 복구 통합 코드 구현·검증 세부 계획.md>)이다.

작업 repo는 `D:/project_code/angmoo-workspace/angmoo-tree-angmoo`, 브랜치는 `feat/0.1.0-release-readiness`다. 시작 HEAD는 `8f4e92b9201284e7777b0927f0d1bc649a6e049b`이며 시작 작업 폴더는 clean이었다. 통합 이슈 [#360](https://github.com/angmoo-tree/angmoo/issues/360)을 생성했다. P00–P26 및 P28–P30의 구현·격리 로컬 검증을 수행하고, P27 실서비스 검증은 조건 미준비로 `NOT_RUN / FOLLOW_UP`에 둔다. 로컬 완료, 실제 AI 품질, 사용자 실행본 적용은 별개다.

최종 수집·실행 집계와 보존 검사 결과는 문서 하단의 최종 마감 기록을 따른다. 한 번 실행한 전체 suite와 이후 수정한 파일의 전체 재검사를 합쳐 마지막 결과를 대조했다. 이전 실패를 지우거나 XML의 완료 시각만으로 최신 결과를 선택하지 않았다.

## 1. 구현된 사용자 동작과 소유 경계

- 명시적으로 저장한 UI 언어 `ko`/`en`을 우선한다. 저장 선호가 없는 최초 감지는 Korean 계열만 `ko`, 다른 locale와 감지 실패는 `en`이다. 두 모드에서 언어 버튼의 이름과 접근성 이름은 `Korean`, `English`다.
- 감지한 기억·검색 locale 및 runtime timezone은 UI 선택과 독립이다. 첫 정상 활성 화면의 lease, session hash, CAS revision, 단조 sequence를 확인하며, 잘못된 감지나 늦은 응답은 마지막 정상값을 지우지 않는다. 수동 timezone 편집을 새로 노출하지 않았다.
- UTC event 순간은 그대로 저장하고 날짜·시간 표시는 Intl로 처리한다. 현지 day/month의 시작과 끝을 각각 UTC로 계산한다. DST의 23/25시간 day, gap, overlap 및 일회성 질의 지역을 지원한다. 24시간 checkpoint 보존·lease·cooldown은 UTC 경과 시간이다.
- 접수한 SNS·Chat·기억·관계 작업은 환경 snapshot을 보존한다. 감지값이 바뀌어도 진행 작업이나 유료 요청을 새로 만들지 않는다. idle의 미래 일정만 작은 batch로 새 revision에 맞추며 잠긴 작업과 cooldown은 보호한다.
- 시간대 이동은 새 quota를 지급하지 않는다. UTC 소비와 원 reservation ID의 보호 구간 합집합을 계수하고, outcome unknown과 legacy aggregate를 보수적으로 유지한다. 월말 지연 정산도 기존 reservation ID를 사용한다.
- Angmoo가 작성한 활성 AI instruction은 영어다. 감지 기억 locale, 캐릭터의 명시 발화 언어, Chat의 현재 의미, 원 persona/source를 별도 입력으로 전달한다. 최종 모델이 해당 지시를 얼마나 잘 수행하는지는 실서비스 후속 검증이다.
- Memory 문서·query·postcheck에 같은 Unicode 경계 정책을 적용한다. `art`/`coffee`/`A-17`/`v1.2`의 내부 오탐을 거절하고 Korean/CJK, combining mark 및 Persian ZWNJ를 보존한다. bounded FTS projection 재구축 중에는 preparing 상태를 반환하며, 수정·삭제 fence를 다시 확인한다.
- Gemini의 scalar const는 같은 타입의 singleton enum으로 낮추고 null branch와 required를 보존한다. unsupported·충돌은 전송 전에 거절한다. 일반 댓글 intent/purpose 누락은 첫 적격 STOP에 한해 기존 JSON 복구 기회를 한 번 공유한다. 두 번째 실패나 Combined 복구 뒤 Writer 연쇄 복구를 새로 허용하지 않는다.
- Home·Feed·캐릭터·게시글·답글·주제 제안·외부 연동 토큰·Provider API key를 의미에 맞게 안내한다. 원문, 이름, 카드 PNG/JSON bytes, URL, enum, World package hash와 과거 alias를 화면 번역으로 재작성하지 않는다.

상세 owner와 활성/퇴역 구분은 [소유 inventory](multilingual-timezone-gemini-sns-owner-inventory-20261003.md)를 따른다. 저장소에 남은 Korean instruction 후보 29곳을 모두 활성 요청으로 간주하지 않았다. 지원 V2 context에 전달되지 않는 과거 수동 message와 퇴역 tool-loop를 구분했다.

## 2. 단계별 구현·검증 대응

| 단계 | 실제 구현·확인 | 주요 증거 owner |
| --- | --- | --- |
| P00 | 지정 branch·clean baseline·사용자 실행본/자료 보호 경계를 고정 | `progress.json`, 시작 Git 상태 |
| P01 | 통합 이슈 360 생성 | 이슈 URL, 단일 이슈 범위 |
| P02 | 활성 AI/route/환경/달력/검색/용어 소유 inventory | owner 문서, `source-owner-inventory.json` |
| P03 | 독립 Draft 2020-12 schema oracle, frozen corpus, 실패 fixture | `test_gemini_schema_missing_contract`, before XML/corpus |
| P04 | const·nullable·required·원본 불변 converter | `providers/gemini.py`, independent source/wire tests |
| P05 | strict missing 판단·첫 STOP 공유 1회·Combined receipt | output recovery/planner/Combined owner tests |
| P06 | 실제 Gemini SDK를 MockTransport에 연결한 최종 HTTP/native 검증 | schema/language provider boundary tests |
| P07 | additive SQLite v27·Alembic 0105·환경/이력 모델 | Identity migration, full migration/installer fixture tests |
| P08 | owner 인증·UI preference·CAS/lease·last valid 환경 API | `tests/identity/test_local_environment.py` |
| P09 | Browser/WebView 감지 입력·인증 scope·복귀·동기화 lifecycle | user environment script, actual SQLite browser tests |
| P10 | provider별 i18next instance·16 namespace·SSR/HTML lang | catalog/user-environment scripts, Next/static browser |
| P11 | 신규 World template·common runtime zone·User placeholder | default-space, package, Creator/card tests |
| P12 | 현지 달력·DST·UTC와 elapsed retention 분리 | calendar/accounting/cross/retention tests |
| P13 | frozen admission·bounded 미래 idle schedule reconciliation | `test_environment_admission`, lifecycle tests |
| P14 | quota ID 합집합·월/일 guard·legacy/unknown·SQLite 경쟁 | `test_calendar_accounting`, Local Bot/media/translation suites |
| P15 | 출시 화면·일반 명칭·Intl·ARIA/whole-message plural | catalog, product browser, canonical visual |
| P16 | typed API/NDJSON/UTC retry·safe error·entry 지원 경계 | shared transports/proxy/product browser |
| P17 | 활성 AI 영어 instruction·원문·발화 언어 분리 | owned instruction inventory, boundary captures |
| P18 | admitted 기억 locale·기존 Selector query·Chat/Routine·hint | memory/episode/media/selector/cross tests |
| P19 | 관계 주체 언어·keep·ID/World/direction 문맥 | relationship review and relation context suites |
| P20 | 닫힌 상대 날짜·활동 의미·legacy 다국어 parser | `test_multilingual_time_resolution`, cross calendar oracle |
| P21 | extraction/query/postcheck의 공통 Unicode literal 경계 | memory lexical/grouped/legacy boundary tests |
| P22 | TopicMatcher 영어 raw span·기존 ko/CJK 의미 보존 | topic matcher/topic pipeline suites |
| P23 | projection profile·bounded rebuild·restart/delete/correct | `test_multilingual_projection_lifecycle`, held-out benchmark |
| P24 | 실제 runtime/DB/SDK mocked HTTP의 교차 계약 | X01–X18 대응표, new contracts 285 PASS |
| P25 | production Next/static 격리 backend·기능·accessibility·pixel | 환경 18, 기존 제품 104 PASS/10 기존 SKIP, visual 36 PASS |
| P26 | 전체 수집·분할 backend 회귀·보존·구조·lint/build | 최종 노드 집계 및 아래 명령/로그 |
| P27 | 비밀 없는 지정 설정 metadata만 확인; 실제 전송 0 | 조건 미준비 `NOT_RUN / FOLLOW_UP`, §6 |
| P28 | owner·107 기준·검증·미측정·재개 문서 | 이 문서, 계약 대응표, 로컬 artifact |
| P29 | 명시 stage·signoff 로컬 단위 커밋 | §7 커밋 기록, 최종 Git clean 확인 |
| P30 | 로컬 상태·격리 자료·후속 검증·범위 제외 인계 | §6·§8 및 최종 마감 기록 |

원 계획의 다국어·시간대 `I.P00–I.P22`는 통합 P07–P23/P25–P30과 I01–I53으로, Gemini `G.P00–G.P12`는 P03–P06/P24/P26–P30과 G01–G36으로 연결했다. 두 원 계획의 테스트 번호를 합쳐 새 pytest 수라고 부르지 않는다. [107개 계약 대응표](multilingual-timezone-gemini-sns-contract-matrix-20261003.md)는 각 I/G/X 기준에 실제 node/명령·소스 검토와 범위 한계를 연결한다. 과거 원 계획 문서를 일괄 완료로 덮어쓰지 않았다.

원 단계와 실제 통합 실행의 대응은 다음과 같다.

| 원 단계 | 통합 실행 |
| --- | --- |
| I.P00 / I.P01 | P00·P02 / P03 |
| I.P02–I.P08 | 차례로 P07–P13 |
| I.P09–I.P18 | 차례로 P14–P23 |
| I.P19 / I.P20 | P25 / P26 |
| I.P21 | P27의 R01–R06 조건부 후속; R07/R08 범위 제외 |
| I.P22 | P28–P30 |
| G.P00 / G.P01 / G.P02 / G.P03 | P00 / P02·P03 / P02 / P03 |
| G.P04 / G.P05 | P04·P05 / P04·P05·P06 |
| G.P06 / G.P07 / G.P08 | P06·P24 / P06·P24 / P06·P17·P24 |
| G.P09 / G.P10 / G.P11 / G.P12 | P26 / P28 / P29 / P30 |

## 3. 회귀 실패를 보완한 방식

초기 전체 business partition은 4,498개 수집, 4,340 PASS·106 FAIL·52 SKIP였다. 이 실행은 최종 수정 전 결과이며 성공으로 재표기하지 않는다. 원 XML과 failure JSONL은 보존했다. 실패한 파일 전체, 제외한 structural partition 전체, final collection을 다시 검사했다.

주요 보완은 다음과 같다.

- canonical env route에서 기존 demo mutation guard를 빠뜨린 경계를 typed dependency로 복원했다. owner 삭제는 그 owner의 환경과 이력만 제거한다.
- 최소 SQLite fixture에 환경/설치 identity 소유 모델을 명시했다. v25/v26 fixture의 과거 schema를 새 v27 ORM으로 만들었다고 간주하지 않고 frozen predecessor를 재현했다. 옛 manifest/revision/hash는 수정하지 않았다.
- World metadata timezone 수정의 기존 transaction 검사는 계속 수행한다. runtime zone을 별도 정책으로 이동했으므로 해당 테스트는 metadata rollback/commit과 runtime 재예약 0을 검사하며, 실제 일정 전환은 별도 Identity admission 통합 검사가 담당한다.
- 과거 Seoul quota fixture에는 감지된 Seoul 환경과 올바른 UTC 생성 순간을 함께 기록했다. v27의 UTC event 계수 정책에 맞췄으며 quota 제한을 높이지 않았다.
- 새 SDK 언어 입력에 맞는 fake signature를 갱신하고, strict refs/결과/호출 수 검사는 유지했다. `User` placeholder 기대값만 새 계약에 맞추고 원 PNG bytes·선택 metadata·편집 persona 검사는 유지했다.
- stale architecture/embedded/L4 inventory는 실제 source hash로 정식 갱신했다. preservation의 immutable Git object/range만 cache하고 HEAD·현재 파일·주입 reader는 매번 다시 읽는다. 변조·다른 ref·미승인 source 변경 거절 검사를 보존했다.
- Alembic 기대값에 0104→0103 및 0105→0104를 명시했다. 과거 88개 blob hash 검사를 유지하며 graph 104개·head 0105·추가 환경 table 2개를 검사한다. 해당 전체 파일 8 PASS다.
- 계약별 증거 검토에서 const+enum/type 충돌과 미지원 reference/union의 직접 사례가 부족하여 14개 독립 검사 node를 추가했다. 원 schema/wire 값 집합 비교와 missing/recursive/unsupported의 정확한 오류를 검사한다. 변환기 자체 변경 없이 해당 전체 파일 38 PASS다.
- raw 서버 오류를 UI 문자열로 기대하던 브라우저 fixture는 authored 안전 메시지와 원문 비노출을 검사한다. 일반 서버 실패를 성공으로 만들거나 HTTP 상태를 바꾸지 않는다.
- native memory의 기존 8초 deadline은 유지했다. 다른 긴 Git 검사와 분리한 idle 실행에서 관련 전체 파일 22 PASS·3 기존 SKIP였다. 시간 제한 증가로 통과시키지 않았다.

structural checker가 기준 파일을 읽은 뒤 새 커밋이 추가된 실행과 마지막 metadata 반영 뒤 재검사는 구분한다. 최종 preservation은 exact committed preimage, ancestry, append-only 기록, 보호된 node와 assertion을 대조한다. test node 제거·신규 skip·visual 허용치 완화로 실패를 숨기지 않았다.

첫 공식 preservation 검사에서 제품 동작 회귀와 별개의 증거 연결 공백 세 곳을 확인했다. 이름을 바꾼 tendency 테스트의 원 lineage 목적지 9곳을 실제 새 이름으로 연결하고, 교체된 `_TRANSLATION_USAGE_LOCK`의 정확한 변경 전 AST와 현재 부재를 기록했다. Identity table assertion의 이번 작업 전 상태는 과거 승인된 모델 경로 표현을 사용하는 두 export predicate와 연결했다. 이후 공식 비교에서도 변경 후 두 predicate가 같은 승인 경로로 정규화되어야 함을 확인했다. 이번 작업의 미커밋 assertion 기록에 공식 checker와 동일한 보호 파일 map·ASGI map·커밋된 root binding을 적용했다. 실제 의미 차이가 보완된 것은 해당 변경 후 predicate 두 개이며, 나머지 assertion은 같은 의미의 AST 표현으로 기록했다. 역사에 커밋된 128개 기록은 수정하지 않았고, 현재 테스트 코드의 `public` 바인딩 검사는 유지했다. 실제 source blob·정의 AST·나머지 predicate와 검사 규칙을 바꾸지 않았다. 원 실패 로그는 `refactor-preservation-release.log`, 경로 표현 불일치 재검사는 `refactor-preservation-release-path-mismatch.log`, 최종 공식 검사는 `refactor-preservation-release-final.log`에 구분한다.

## 4. 명령과 evidence

아래 `artifacts/multilingual-gemini-20261003/`는 ignore된 로컬 검증 자료다. clone에는 포함되지 않는다. 공유 가능한 판단·수치·명령은 이 문서와 계약 표에 남긴다. 키·실제 대화·사용자 DB 전체는 Git에 포함하지 않는다.

| 검사 | 실행·자료 | 확인 범위 |
| --- | --- | --- |
| backend 전체 수집/회귀 | `collection-release-collected.json`, `backend-business-final.xml`, `backend-structural-release.xml`, `backend-affected-release.xml`, `final-regression-audit.json` | 전체 partition과 마지막 수정 파일 재검사 합집합. 한 번의 최종 HEAD pytest로 오인하지 않음 |
| 새 통합 검사 | `new-contracts-final.xml` | 285 PASS; fake/network-denied local contract |
| installer predecessor | `installer-fixture-v27-final.xml` | 1–26의 populated synthetic upgrade+unsupported 27 PASS. 설치판 실행 아님 |
| schema/성능 | `contracts-before.json`, `contracts-after.json`, `benchmark-*-release-final.json` | 원본/wire 및 변환 크기·시간, lexical 품질/용량 |
| 전체 계약/노드 보존 | `refactor-preservation-release*.log`, exact product/introduction 기록 | baseline을 재생성하지 않고 승인된 이름/소스/AST/hash만 append |
| architecture/design | `*-boundary-release.log`, `*-inventory-release.log` | backend 1,361 modules/5,505 edges, frontend 14 features, legacy 경로 0, design route gaps 0 |
| catalog | `pnpm --dir frontend test:ui-catalog`; `catalog-release.log` | 16 namespaces/2,375 source keys, key/params/plural parity |
| 환경/HTTP | `pnpm --dir frontend test:user-environment`; `environment-release.log` | isolated instance/SSR/escaping/detection/UTC/typed errors, late auth transition 12조합 |
| proxy | `test:world-package-proxy`, `test:character-card-proxy`; proxy release logs | 기존 Next proxy·card boundary |
| typecheck/lint | `pnpm --dir frontend typecheck`, `pnpm --dir frontend lint` | 최종 UI source 통과 |
| Windows build | `pnpm --dir frontend build`, `build:static`; `build-windows-transport-*.log` | production Next 및 static-export |
| Linux build | `build-linux-release-final.log` | 로컬 toolchain image, network none; 두 production build |
| 실제 격리 backend browser | `playwright.internationalization.config.ts`; `browser-environment-release.xml` | 18 PASS, 실제 FastAPI/SQLite/session/CAS, fake Provider |
| 기존 제품 기능 | `browser-product-functional-release.xml` | 104 PASS·10 기존 HY14 prerequisite SKIP |
| canonical visual | `browser-visual-canonical-release-final.xml` | 36 PASS, digest-pinned Playwright 1.62.1 Noble, 최종 검사는 snapshot 자동 갱신 없음 |

browser는 두 production entry와 실제 지원 route를 검사했다. viewport/keyboard/44px/200%/long English/console/HTML lang을 확인했으며, 실제 Tauri WebView·설치판·사용자 Docker의 품질 판정으로 확대하지 않는다. HY14의 10 skip은 별도 workflow/실서비스 자원이 필요한 기존 조건부 검사다. 새 다국어 검사를 skip하지 않았다.

backend의 기존 52 SKIP은 명시 performance 실행 6, public runtime에 포함하지 않는 hosted lifespan 1, 실제 Vec1 extension 미제공 21, Postgres graph 환경 미제공 1, 보안 동시성 Postgres 환경 미제공 19, 선택적 사용자 원본 미제공 3, scheduler Postgres 환경 미제공 1이다. 이 항목들은 PASS로 합산하지 않는다. 합성 lexical benchmark나 SQLite 경쟁 검사를 해당 미실행 환경의 품질 증명으로 대신하지 않는다.

canonical PNG의 의도한 일반 명칭·시간/문구 차이는 이미지·기능 비교와 exact committed hash로 검토했다. UI-B 색/contrast foundation과 최대 pixel 차이 25·threshold 0.1은 유지했다. Windows 글꼴 차이를 canonical 갱신 근거로 사용하지 않았다.

## 5. 검색·schema·bundle 측정과 비용

동일 합성 corpus SHA256 `8a0645c3a5670eaf7ba247f8df61f766e58762e1445665bda411b203484bfa66`를 사용했다. 33문서, 69query이며 한국어 12경험은 tune 8/holdout 4로 구분한다. 실제 embedding이나 실제 사용자 DB가 아니다.

| 측정 | 이전 → 이후 |
| --- | --- |
| tune 40 / held-out 20 Recall@5·precision·MRR | 모두 1.0 → 1.0, negative false positive 0 → 0 |
| multilingual 9 precision | 0.8889 → 1.0 |
| multilingual negative false positive | 1 → 0 (`v1.2`와 `v1.20` 구분) |
| held-out p50 / p95 | 2.0718 / 2.5706ms → 2.1794 / 2.7173ms |
| 측정 projection 파일 합계 | 73,728 → 73,728 bytes; 이 fixture의 `angmoo-memory-recall.sqlite3`만 |
| 일반 Feed/Inbox wire JSON | 1,113 → 1,185 bytes (+72) |
| capable Feed / Inbox wire JSON | 1,787 → 1,829 (+42) / 1,738 → 1,843 (+105) |
| Writer wire JSON | 844 → 907 bytes (+63) |

100회씩 잰 최종 converter p50/p95는 일반 Feed 1.3572/1.6778ms, capable Feed 2.1648/2.8854ms, 일반 Inbox 1.3614/2.2799ms, capable Inbox 2.4671/3.0368ms, Writer 1.4972/1.8478ms다. 실제 서비스 응답 지연이 아니다. 소규모 로컬 검색 지연은 환경 영향을 받으며 일반 성능 보장을 하지 않는다.

동일 Linux production toolchain의 공개 JS/CSS 파일 합계를 비교했다. Next raw 2,434,592→3,037,231 bytes, gzip 718,142→857,883 bytes다. static raw 1,469,830→1,956,261 bytes, gzip 394,156→497,728 bytes다. 번역 catalog와 i18next를 모두 준비하는 현재 구현의 증가분이다. 모든 route chunk 합계이며 한 페이지의 초기 전송량이나 설치 데이터 총량으로 해석하지 않는다. `bundle-size-comparison.json`에 파일별 측정을 보존했다.

## 6. P27 실제 서비스 검증 상태와 후속

실제 API 전송은 **0회**다. 지정된 Bram의 연결과 공통 인식 설정에서 비밀 없는 model/thinking/profile metadata만 최소 read-only 조회했다. 사용자 DB 전체를 복제하지 않았고 credential을 복호화·전송·문서화하지 않았다. 키의 실제 서비스 사용 가능 여부는 아직 확인하지 않았다.

| 경로 | 확인된 저장 설정 | 실제 실행 |
| --- | --- | --- |
| Bram SNS | Gemini 3.1 Flash-Lite, high | NOT_RUN |
| Chat | Gemini 3.5 Flash-Lite, high | NOT_RUN |
| 기억 요약 | Gemini 3.1 Flash-Lite, high | NOT_RUN |
| embedding | Gemini Embedding 2, 기존 profile·768차원 | NOT_RUN |
| 공통 이미지 인식 | Gemini 3.1 Flash-Lite, medium | NOT_RUN |

미실행 사유는 **모든 worker·복구·준비 요청이 공유하는 durable 물리 호출/비용/시간 장부 및 최대 요청 비용 예약이 준비되지 않았기 때문**이다. metadata가 있다는 사실을 키 검증 완료나 실제 AI 품질 PASS로 대신하지 않는다. 계획 P27.4/§18.3에 따라 로컬 구현은 별도로 마무리하고 R01–R06을 조건부 후속으로 남긴다.

후속은 R01의 격리 실행본 source/build·schema·guard/ledger/receipt 확인, R02의 실제 Gemini 최소 schema 수용·정상/제한 복구, R03의 자연 활동 관찰, R04의 다국어 AI·기억·관계 품질, R05의 실제 이미지 인식, R06의 실제 embedding 검색이다. 자연 적격 누락이 발생하지 않으면 `NOT_REPRODUCED`이며, 그 자체를 복구 품질 PASS로 기록하지 않는다. Windows 설치형/사용자 Docker 실제 동작 R07/R08은 `EXCLUDED_SCOPE`다. 이 제외를 미완료 후속이나 로컬 실패로 집계하지 않는다.

후속 실행 시 반드시 다음 기존 확정 조건을 이어받는다.

1. 정상 credential 등록·권한 해석 경로로 독립 test owner와 연결한다. encrypted row를 다른 binding으로 복제하지 않는다. World 1개·캐릭터 4개·12경험·16질문·4이미지·4선호 환경 fixture를 사용한다.
2. 실제 요금·요청 입력/출력 한도와 session ID를 확인하고 첫 전송 전에 공유 장부를 준비한다. 최대 비용·호출을 원자적으로 예약하며 미확정 usage는 보수적으로 유지한다.
3. 전체 3 USD, 생성·인식 합산 120회, embedding 40회, 그 120회 안에서 인식 최대 6회를 지킨다. 2 USD부터 신규 자연 활동을 중단한다. 준비·실패·재시도·batch HTTP도 계수한다.
4. 첫 실제 호출부터 사례 최대 30분·자연 관찰 최대 60분·전체 90분이다. model/thinking·SDK attempts=1·기존 정상10/복구5/전체15 한도를 유지한다.
5. 전송 전 guard와 잔여 예약을 검사한다. 재시작·언어/시간대 변경으로 예산/기한을 초기화하거나 추가 자동 세션을 만들지 않는다. 실제 calls/usage/확정 비용/미해결 예약/관찰 completeness/품질을 분리하여 남긴다.

## 7. 로컬 커밋과 보존 근거

아래 단위들은 signoff 로컬 커밋이다. push·PR 생성·Hosted CI·act·main merge는 수행하지 않았다. `.github/workflows/windows-installer.yml`의 v26 predecessor matrix 변경은 코드로 검토·로컬 fixture 검사를 했으며 Hosted CI가 실행됐다는 뜻이 아니다.

| SHA | 단위 |
| --- | --- |
| `dd96e488b578c061d1226247b1a093a400ce83e4` | 환경·달력·v27·AI 언어·schema·누락 복구·검색 backend |
| `e1633532241dade1d641d87b54214976a5532461` | immutable Git 증거 cache, mutable 후보 미캐시 |
| `77aa85f75e3f8ae6157d0aa41ac07a3018cc058c` | ko/en UI·catalog·감지·공통 entry·첫 시각 검토 |
| `ecd8d2cff6f6d2dedd79367cacdbe17c9e747027` | pinned range 재사용·mutable ref/reader 재검증 |
| `8368f245b9dcfdce0a33d3a5e97c4e5906cff175` | canonical fixture·승인 소스 보존 연결 |
| `072c45104f05fba477df005d7c682585e4b9dd9b` | v27 진단·frozen calendar fixture |
| `0e2fc098b66bc5dad517429f72bbd8431bf8b859` | 환경 auth/삭제 privacy·v27 predecessor/기존 보안 fixture |
| `b5c4b4a28627745778da299806842bbfb9a80238` | HTTP auth scope·번역된 전체 문구·UI 상태·최종 visual |
| `3d2c97d7b0eca5727b0db736db5ca6d6857d3c80` | User placeholder·최종 source inventory |
| `7aa2e40cb8f72e7d2aff1ad5c7fa4705649f87a4` | additive v27 Alembic graph/metadata 기대값 |
| `81e440826abf43256a520c3ba4cba8802187007e` | const 충돌·reference/union 거절의 독립 검사 14개 추가 |

`security/post_refactor_contract_changes.json`에는 각 실제 커밋의 exact source blob/AST/assertion/frontend asset delta를 append했다. `security/refactor_backend_additions.json`에는 정식 committed-source capture로 새 source/node lineage를 append했다. 과거 checkpoint·manifest를 현재 소스와 같도록 재생성하지 않았다.

## 8. 중단·재개와 실행본 적용의 경계

로컬 artifact는 보존한다. 합성 SQLite/검색 projection·benchmark corpus·browser capture·trace·before failure 자료이며 실제 사용자 전체 DB/키가 아니다. 검증용 container는 작업 소유의 `--rm`/network none 실행이었다. 이 문서는 사용자 Docker·Windows 앱을 빌드/재시작했다는 보고가 아니다.

검증 결과를 다시 읽을 때는 다음을 사용한다. 새로운 source 변경/실패가 없으면 이미 통과한 장시간 전체 회귀를 이유 없이 다시 돌리지 않는다.

```powershell
Set-Location 'D:\project_code\angmoo-workspace\angmoo-tree-angmoo'
git branch --show-current
git status --short
git log -1 --oneline
Get-Content -LiteralPath 'artifacts/multilingual-gemini-20261003/progress.json'
Get-Content -LiteralPath 'artifacts/multilingual-gemini-20261003/final-regression-audit.json'
```

후속 실서비스는 §6과 원 계획 §17.3–§17.7의 준비를 완료한 뒤 별도 실행한다. 사용자 Docker/설치판 확인이 새로 요청되면 그 요청의 범위에서 별도로 진행하며, 설치판 진단은 workspace AGENTS의 physical identity helper를 먼저 따른다. 이미 시행하지 않은 배포·설치·실제 AI를 이번 로컬 PASS에 포함하지 않는다.

## 9. 최종 마감 기록

2026-10-04 KST, 검증 소스 HEAD `81e440826abf43256a520c3ba4cba8802187007e`에서 필수 로컬 검사를 마감했다. 초기 FAIL 로그와 후속 PASS를 보존하고 명시 실행 순서로 전체 수집과 대조했다.

| 마감 대상 | 최종 실제 상태 |
| --- | --- |
| backend collection / 실행 합집합 | 4,969개 수집·대조, 4,917 PASS·기존 52 SKIP·FAIL 0·미수집 0 |
| 보호 source/API/ORM/node/assertion | 공식 `check_refactor_preservation.py --contracts --nodes`, 실제 exit 0 |
| frontend stock/assertion/fixture/asset/lock | 공식 `check_refactor_frontend_preservation.py`, 실제 exit 0 |
| 이력 변조·범위 외 변경·연결 충돌·실제 Identity table 회귀 | 정규화 후 관련 전체 파일 56 PASS, `preservation-metadata-normalized-release.xml`; 앞의 51 PASS도 보존 |
| assertion 연결 | 179개 node·132개 이력 전이, 불연속 0 |
| I01–I53·G01–G36·X01–X18 | 실제 node·별도 명령·소유 검토를 연결한 107개 `LOCAL_CONTRACT_PASS`. pytest 107개 또는 실제 AI 품질 PASS라는 뜻이 아님 |
| Next/static 격리 실제 backend / 기존 제품 기능 / canonical visual | 각각 18 PASS / 104 PASS·기존 10 SKIP / 36 PASS |
| architecture/design·catalog·typecheck/lint·Windows/Linux Next/static build | 해당 로컬 명령 PASS. Hosted CI·실제 Windows 앱 실행 아님 |
| P27 실제 API·embedding·자연 활동 | 전송 0회, R01–R06 NOT_RUN/FOLLOW_UP; 공유 비용·호출·시간 장부 준비 필요 |
| R07/R08 | Windows 설치형·사용자 Docker 실제 검증 EXCLUDED_SCOPE |
| 작업 소유 서버 | fixture 포트 18399·3361·3362 listener 없음; 종료 확인 후 DB/캡처/증거 보존 |

P00–P26·P28–P30의 로컬 구현·검증·문서·소유 커밋을 완료하는 마감 단위는 `docs(verification): finalize multilingual timezone and Gemini local contracts`다. 앞의 11개 소스/테스트 단위는 수정하거나 합치지 않는다. 마지막 단위에는 검증 문서 3개와 보존 증거 metadata 3개만 명시 stage한다. 이 문서가 포함된 마감 커밋 자체의 SHA와 커밋 직후 `git status --short`의 실제 clean 확인은 로컬 `local-closeout.json`에 기록한다. 소스 검증 HEAD와 문서/증거 마감 HEAD를 구분한다.

`final-regression-audit.json`은 한 번의 최종 전체 pytest 실행이 아니라 business/structural 전체 partition과 이후 변경 파일의 전체 재검사 합집합이다. 모든 현재 node가 하나의 마지막 유효 결과로 연결된다. 52 SKIP·기존 browser 10 SKIP의 사유는 §4대로 남기며 실제 서비스/기기 품질을 합산하지 않는다.

문서와 증거 마감 이후 제품 소스 변경은 없으며 branch publish/push·PR·Hosted CI·act·main merge·사용자 Docker/설치판 적용은 수행하지 않는다. workspace 통합 계획의 §20에도 동일 실행 상태를 추가한다. workspace 문서는 제품 repo 커밋에 자동 포함되지 않는다.
