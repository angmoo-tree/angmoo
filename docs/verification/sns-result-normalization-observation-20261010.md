# SNS 상황기억 정규화 복구·설명 진단 구현 결과 — 2026-10-10

요청한 workspace 계획의 **I00–I29, 30개 단계**를 현재 로컬 브랜치에서 수행했다. 신규 접수의 저장 표현 비교, 기존 차단 기록의 증명 기반 복구, 설명 누락의 구조 진단, 별도 coverage, 외부 수집기를 구현했다. 기본 검증 V01–V17의 해당 범위를 확인했고 **V18 실제 AI 자연 관찰은 실행하지 않았다**. 원본 차단 기록의 재검사·원본 서버 조작도 수행하지 않았다.

- 저장소: `D:/project_code/angmoo-workspace/angmoo-tree-angmoo`.
- 브랜치: `feat/0.1.0-release-readiness`.
- 시작 HEAD: `b8104fac3ac99f01573d633fba6db9751cd25adf`; 시작 제품 working tree는 깨끗했다.
- 이번 결과는 이 문서를 포함한 로컬 커밋으로 보존한다. PR·push·CI·main 전환/병합·새 worktree·설치/배포는 하지 않았다.
- 실행 계획: [10-10 구현 계획](<../../../docs/plan/10-10 SNS 상황기억 본문 정규화 오탐 복구와 설명 누락 관찰 강화 코드 구현 세부 계획.md>).
- 운영 판독: [10-07 가이드 §17–19](<../../../docs/plan/10-07 SNS V2 4회 활동·이미지 생성·인식·기억 검색·예약 정리 통합 관찰 세션 실행과 판독 가이드.md>).

## 구현 계약

Social의 `stored_output()`은 유효한 최종 초안에 기존 `sanitize_visible_post_title/body`를 적용한다. 실제 Post는 동일 Session에서 독립적으로 읽고 다시 정규화하지 않는다. `None`·잘못된 자료형은 빈 문자열로 승격하지 않는다. Routine target는 실제 실행 소유자가 확정한 **생성 Post 자신의 ID**, Inbox/Feed 답글 target는 실제 direct parent다. Like·Chat에는 이 본문 정규화를 적용하지 않는다.

기존 차단 receipt는 원본 hash를 고치지 않는다. Memory는 무결성을 확인한 admission과 저장 자격을 가진 context를 분리한다. 새 명시적 v4 재검사에서 Runtime의 제한된 read-only checkpoint resolver가 정확한 activity/lane/manifest와 원 planned hash를 증명한다. 정규화한 예정 내용이 원 final hash 및 실제 canonical 결과와 같고 기존 scope/source/access 검사를 통과하면 `memory_situation_result_bindings`에 hash·identity 증명을 추가한다. 증명과 기억은 기존 UoW에 참여하며 실패·용량 부족에는 남지 않는다.

v2/v3 run의 검증 revision은 고정한다. 새 v4를 추가해도 v3 부모 binding의 소비 기능은 유지된다. 승인 후 상세·recall·hydration·prior/HotBrief·관계 소비의 공통 `restore_context()`는 저장된 증명을 사용한다. checkpoint가 없어져도 읽을 수 있지만 이후 source 변경·접근 상실은 계속 차단한다. 처리 이력 삭제는 proof FK만 `SET NULL`로 정리하며 증명에 캡처된 원 run ID와 증명 자체를 유지한다. 사용자 저장 포기·scope 삭제의 기존 정리 경계도 유지한다.

SQLite **v35 → v36**, Alembic **20261010_0112 → 20261010_0113**은 빈 증명 table만 추가하는 forward delta다. 과거 manifest/DDL을 변경하거나 upgrade/startup/GET에서 차단 경험을 자동 재검사하지 않는다. FTS·vector 등록은 승인된 새 기억에 기존 incremental 경로를 적용한다. 접수/복구 자체에 provider 호출은 없다.

`inspect_situations()`는 Memory의 기존 parser 결과와 우선순위를 보존하며 필드 부재/null, 빈 목록, target 누락/중복, description 부재/null/type/empty/길이/Unicode와 order를 판독한다. Runtime은 그 결과를 안전한 shape로 투영한다. 실제 JSON 객체를 얻은 후, 기존 base validator 전후에 callback을 연결하고 physical/JSON/stage attempt·입력 hash·최종 Writer 선택을 전달한다. 진단 오류는 생성·저장 결과를 바꾸지 않는다.

새 session에만 `situation-observation.v1` capability를 기록한다. 이벤트는 `situation_output_shape`, `situation_output_parsed`, `situation_receipt_committed`이고, 마지막 이벤트는 실제 outer commit 이후에만 기록한다. 16개 항목·64자 안전 ID·16 KiB 이벤트 상한, 기존 queue/sink lifecycle을 유지한다. 새 이벤트에 API 키·암호문·prompt·SNS 본문·설명 원문·thought를 넣지 않는다. **Core schema3의 `complete_recording`과 보완 `situation_evidence_complete`는 독립이고 둘 다 AI 품질 판정이 아니다.**

외부 [PowerShell 수집기](../../scripts/diagnostics/Invoke-SnsMediaMemoryObservation.ps1)는 기존 승인된 session의 status/probe/export만 수행한다. [Python probe](../../scripts/diagnostics/sns_media_memory_probe.py)는 실제 성공 execution/receipt 효과, World/actor/본 구간/carry-in과 `posts.reply_to_post_id`로 대상을 제한한다. JSON ISO 문자열은 `DateKind String`으로 보존하고 offset을 한 번 UTC로 변환한다. 60초 이상 간격의 연속 probe 오류 3회 뒤 degraded로 전환하고, tail 이후 최대 5분 flush 대기와 export를 거쳐 유한하게 종료한다.

## I00–I29 수행 기록

| 단계 | 결과와 증거 |
|---|---|
| I00 | 지정 branch/HEAD·깨끗한 초기 Git 상태·실행 경계 확인. 원본 보존 및 실제 AI 제외. |
| I01 | Routine own-post target, reply direct target, 최종 combined/Writer 선택과 실제 Social 저장 경계를 재추적. |
| I02 | raw/actual digest가 형식 차이로 갈라지는 합성 과거 receipt와 checkpoint 재현. |
| I03 | Social `social-visible-text.v1` strict projection 추가. 기존 sanitizer 단일 소유 유지. |
| I04 | Routine title/body 예정 표현을 정식 저장 표현으로 계산. 실제 값은 독립 비교. |
| I05 | Inbox/Feed reply 및 Writer override의 최종 설명·초안 연결. Like 의미 유지. |
| I06 | 신규 접수·멱등·same-UoW·rollback 관련 회귀 확인. 실질 내용 차이는 차단. |
| I07 | typed `SituationResultBasis`/binding 및 순수 승인/검증 policy 추가. |
| I08 | Runtime의 bounded read-only exact checkpoint resolver 조립. saver 초기화/graph 재개/추측 없음. |
| I09 | append-only binding model/repository와 v36/0113 frozen DDL·manifest·forward delta 추가. |
| I10 | 최신 v4와 고정 v2/v3 구분. 부모 binding revision capability 보존. |
| I11 | 기존 blocked_recheck의 lease/savepoint/UoW에 승인 연결. 실패·capacity에는 proof/item rollback. |
| I12 | 공통 context 복원에 승인 proof 연결. checkpoint 및 처리 이력 정리 후 읽기·현재 source guard 검증. |
| I13 | 실제 5건의 일관된 사본에서 개별 재검사. 5건 복구·원 hash/credential 유지·중복 없음. |
| I14 | Memory 순수 parser 지원 함수로 상세 구조 reason 구현. 원 parser 상태/우선순위 보존. |
| I15 | combined/split의 JSON 객체 전후 callback으로 base 실패와 auxiliary 누락 구분. |
| I16 | 실제 physical/JSON/stage attempt·입력 hash와 마지막 Writer 선택 연결. callback 때문에 추가 호출 없음. |
| I17 | opt-in capability·sink allowlist·상한 및 OFF/sink 오류 비간섭 구현. |
| I18 | 기존 Session outer commit hook에 안전한 receipt/effect/결과 ID 진단 연결. savepoint rollback에도 오기록 없음. |
| I19 | 보완 evidence/coverage export 추가. stage/payload가 다른 재개·Writer 이벤트를 합치지 않음. 보완 파일 오류는 core export와 분리. |
| I20 | 다음 session용 외부 probe의 실제 parent 열·성공 effect·scope 식별 수정. 빈/비어 있지 않은 smoke 통과. |
| I21 | 모든 외부 JSON의 ISO 문자열 보존 및 offset/UTC codec 사용. 모호한 DateTime·offset 없는 값 거절. |
| I22 | collector health·3회 degraded·유한 flush/export 구현. 최종 probe 오류 후 실제 script export/종료 시험 통과. |
| I23 | 10-07 가이드 §17–19의 실제 이벤트·분모·구 session 미지원·사본 결과 반영. |
| I24 | **판단 완료, frontend 변경 N/A.** 기존 Memory 범용 실패 안내와 재검사/포기 UI로 충분. ko/en 제품 문자열 변경 없음. |
| I25 | sanitizer·접수·generation·parser·observer·coverage 관련 좁은 pytest 수행. |
| I26 | historical recovery·pinned revision·forward migration·읽기·재검사·failure preservation 관련 pytest 수행. |
| I27 | 네트워크 차단·fake provider·합성 키·독립 filesystem의 Docker 회귀 및 외부 smoke 수행. 원본 volume mount 없음. |
| I28 | 변경 Python 문법·새 import 경계·Git diff·문서/링크/명령 및 기능별 제한 재검토. |
| I29 | 실제 변경 파일을 명시하여 현재 branch에 로컬 커밋. workspace 문서는 원래 위치에 저장. |

## V01–V18 판독

| 검증 | 판독 |
|---|---|
| V01 | 이번 변경의 새 import 경계 위반 0. 아래 기존 순환 2건은 시작 HEAD의 동일 import edge로 확인하여 별도 기록. |
| V02 | 기존 Social sanitizer 회귀와 raw formatting mismatch 재현 통과. |
| V03 | Routine 제목·개행·escape·탭의 신규 pending→applied와 strict invalid 필드 거절 통과. |
| V04 | Inbox/Feed의 정확한 final Writer 답글 복구·like 및 기존 generation/대체 회귀 통과. |
| V05 | 기존 admission 멱등/UoW와 outer/nested rollback 진단 회귀 통과. |
| V06 | 원 planned/final hash 재현·다른 초안/근거 부재/실제 내용 변경의 실패 통과. |
| V07 | populated v35 forward delta, FK/불변 기존 행·암호화 material 보존, Alembic parity, 실패 미승격·key/marker 보존 통과. |
| V08 | v2/v3 pinned run은 v4 결과 proof를 승인하지 못함. v3 parent capability 및 기존 unknown revision 방어 유지. |
| V09 | 기존 개별/전체 재검사·lease/CAS/discard 회귀와 활성 epoch 종료·capacity rollback 통과. |
| V10 | checkpoint/처리 이력 삭제 후 승인 context 복원, source 변경 시 거절. 기존 읽기/recall/복구 consumer 회귀와 공통 경로 확인. |
| V11 | 실제 5건 사본 전부 복구, 원 hash·credential 보존, 5 item/5 proof/5 incremental 등록, 같은 요청은 같은 run. |
| V12 | fake 응답에서 missing 세부 원인·duplicate/invalid/order 구분. business parser 상태 불변. |
| V13 | actual combined callback 및 두 물리/JSON 시도의 base 실패→성공 연결 통과. superseded stage/payload는 coverage 모호성으로 판정. |
| V14 | description 원문 미출력, bounded allowlist·OFF/sink 비간섭·outer/nested rollback committed 0 확인. |
| V15 | 구 export는 unsupported. canonical receipt/committed 이벤트 누락 분리. 보완 jsonl/coverage 파일 쓰기 실패에도 core coverage/export 유지 확인. |
| V16 | 빈/글·답글·부모·media 존재 SQL, 잘못된 열 거절, +09/Z/-05 동일 순간, 240+30분, 모호한 시간 거절, 실제 PS smoke·degraded 정책·최종 export/종료 통과. |
| V17 | 격리 Docker 관련 회귀 통과. PowerShell host 전용 검사는 Windows에서 수행하고 Docker에서 N/A. frontend diff N/A. 문서/명령 검사는 아래 기록. |
| V18 | **보류 / 미실행.** 실제 AI 자연 활동·유료 호출·한국어 품질 재관찰·원본 차단 경험 적용은 이번 결과에 포함하지 않음. |

## 실제 5건 사본 결과

원본이 멈춰 있던 시점에 canonical read-only backup과 정확한 5 activity의 checkpoint 65행을 별도 사본으로 확보했다. WAL 자료는 별도 임시 복제에서 일관된 읽기 자료로 만들었고 복제 전후 원 자료 hash를 확인했다. 최종 재검사는 **v36 delta를 적용한 새 사본**에서만 실행했다. 키 원문/대화/SNS 본문은 결과 파일에 출력하지 않았다.

| receipt sequence | actor | 사본 결과 | 원 planned/final/content/manifest hash |
|---|---|---|---|
| 119 | Elias Finch | RECOVERED_COPY | 유지 |
| 124 | Red | RECOVERED_COPY | 유지 |
| 127 | Elias Finch | RECOVERED_COPY | 유지 |
| 130 | Red | RECOVERED_COPY | 유지 |
| 143 | Bram | RECOVERED_COPY | 유지 |

새 기억 5개, 정상화 proof 5개, vector incremental eligibility 5개가 생성됐다. 같은 재검사 요청을 다시 제출하면 같은 run ID였다. 모든 copied credential 행과 기초 canonical 사본 파일 hash가 보존됐다. **원본 재검사 0회, 실제 API 호출 0회.**

증거: `D:/project_code/angmoo-workspace/.local-diagnostics/sns-result-normalization-20261010/five-copy-classification-final.json`. 과거 설명 누락 2건의 버려진 원 응답은 새 진단으로 소급 복원하지 않았으며 구조 원인은 계속 UNKNOWN이다.

## 실행한 관련 검사

전체 suite/CI 대신 실제 변경과 소비 경로만 선택했다. 결과 파일은 동일 `.local-diagnostics/sns-result-normalization-20261010` 아래에 있다.

| 실행 묶음 | 최종 결과 | 로그 |
|---|---|---|
| Windows: 새 복구/migration/진단/collector, 기존 접수/generation/sanitizer/SNS observer/gap 회귀 9개 파일 | **101 passed** | `windows-final-regression.log` |
| 외부 collector: portable pwsh 탐색, SQL·시간·실제 smoke·정책·probe 실패 후 export/종료·단계별 health | **10 passed**; 앞 묶음과 8개 중복 | `collector-stage-health-final.log` |
| 보완 export 파일 오류 2건 및 OFF/sink 오류 재확인 | **3 passed**; 앞 묶음과 OFF case 중복 | `auxiliary-export-faults-complete.log` |
| 최종 구조 진단·coverage: carry-in 시작 이전 분모 분리와 export 오류를 포함한 전체 관련 파일 | **24 passed**; 앞 묶음과 중복 있음 | `situation-diagnostics-final.log` |
| 네트워크 없는 Docker: 새 복구/migration/진단/collector 4개 파일 | **47 passed, 1 skipped**; skip은 Windows PowerShell 전용 정책 검사 | `docker-final-regression.log` |
| Docker: 최종 진단·baseline 분모·export 오류 추가/재확인 | **24 passed**; 위 Docker 묶음과 중복 있음 | `docker-diagnostics-complete.log` |
| 기존 source/상세/recall/재검사/직접 전임 migration 등 관련 consumer 묶음 | 74 passed, 초기 신규 fixture 3건 실패는 마지막 회귀에서 수정·통과 확인 | `consumer-collector-tests.log`, `reply-revision-tests.log`, 최종 Windows 로그 |
| 변경 Python 문법 및 현재/시작 HEAD import 대조 | Python 38개 문법 통과, 새 경계 오류 0 | `static-baseline-result.json` |

초기 실패는 숨기거나 기준을 완화하지 않았다. fake lane의 tracker 부재, 새 revision 기대값, tuple/list 직렬화 비교, Windows SQLite handle 닫힘, epoch 종료 시점, Routine의 실제 own-post target를 바로잡았다. 제품에서는 진단 비간섭·savepoint rollback 처리, proof의 이력 FK 수명, 정확한 provider node/attempt 연결을 보강했다. 최종 관련 시험에 남은 제품 실패는 없다.

현재 구조 검사에 남은 **기존** 순환은 다음 두 쌍이다. 해당 네 모듈의 import edge가 시작 HEAD와 같음을 대조했다. 전체 구조 검사가 전부 PASS라고 보고하거나 예외 policy로 숨기지 않았다.

- `identity.service.world_credentials ↔ identity.service.world_image_credentials`.
- `memory.contracts.activity_situation ↔ memory.contracts.situation_source_binding`.

문서 3개의 UTF-8·fence·로컬 링크 69개와 JSON 예제를 확인했다. 계획과 수행 기록 각각에서 I00–I29 30개, V01–V18 18개의 연속성과 중복 없음을 확인했다. 문서의 PowerShell 블록 15개와 실제 PS1/PSM1 파일 2개의 AST 문법 오류는 0이었다. 내장 Python 조회 예제도 실행 없이 문법을 확인했다.

## 재검증 명령과 운영 경계

기존 의존 환경을 사용한다. 아래는 관련 regression이며 설치·빌드·전체 CI 명령이 아니다.

```powershell
Set-Location -LiteralPath 'D:/project_code/angmoo-workspace/angmoo-tree-angmoo/backend'
& .venv/Scripts/python.exe -m pytest tests/memory/test_situation_result_normalization.py tests/migrations/test_situation_result_binding_upgrade.py tests/runtime/test_situation_observation.py tests/runtime/test_sns_media_memory_collector.py -q
```

외부 smoke는 다음과 같이 **이미 존재하는 승인된 session**에 실행한다. session ID와 data root는 실제 승인 대상의 값으로 바꾼다. smoke는 새 session이나 서버를 시작하지 않는다.

```powershell
& 'D:/project_code/angmoo-workspace/angmoo-tree-angmoo/scripts/diagnostics/Invoke-SnsMediaMemoryObservation.ps1' -DataRoot '/var/lib/angmoo' -SessionId 'sns-기존세션의32자리16진수' -DockerContainer 'angmoo-backend-1' -OutputRoot 'D:/project_code/angmoo-workspace/.local-diagnostics/새수집결과' -ReadOnlySmoke
```

기존 5건을 원본에서 복구하려면 별도 승인된 명시적 재검사를 사용한다. 이번 작업은 원본에 버튼을 누르거나 활동·예약·설정을 바꾸지 않았다. 파일을 수정한 소스의 구현/사본 결과와 Docker 원본·Windows 설치 앱의 적용 상태를 혼동하지 않는다. 실제 설명의 사실성·언어 준수와 자연 활동 효과는 다음 별도 관찰에서 판독한다.
