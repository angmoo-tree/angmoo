# 10-08 Chat·SNS 상황기억 관찰 검증과 차단 기록 복구 구현 결과

작성일: 2026-10-08 · Asia/Seoul

대상: [관찰 증명·관계 스냅샷·차단 기록 복구 I00–I29](</D:/project_code/angmoo-workspace/docs/plan/10-08 Chat·SNS 관찰 증명과 관계 스냅샷 검증·차단 기록 복구 코드 구현 세부 계획.md>)

제품 저장소: `D:\project_code\angmoo-workspace\angmoo-tree-angmoo`

브랜치: `feat/0.1.0-release-readiness`

시작 HEAD: `66c7b978e3e21dd79acb86ff6efd2f6d1d70bb5c`

상태: 제품 구현 및 집중 검증 완료. 전체 회귀·보존 검사와 최종 로컬 커밋 결과는 마무리 후 아래에 추가한다.

## 1. 바뀐 동작

Chat·SNS가 실제로 전달한 최종 입력과 성공 결과를 영속 상황 접수에 결합한다. Inbox에서 다른 캐릭터의 답글을 실제 입력으로 전달했다면 해당 접수의 검증 문맥 안에서 관찰을 증명한다. Feed 관찰 행을 새로 만들거나 claim·lease·처리 상태를 변경하지 않는다. evidence의 `observation_id`에는 실제 Feed 외래 키만 사용하며 manifest ID를 대입하지 않는다.

관계 배경은 준비된 snapshot의 state/actor/target/version/view/facts digest로 고정한다. 전달한 버전 6 뒤 정상적인 활동으로 현재 버전이 7이 되어도 과거 입력을 7의 digest로 대체하지 않는다. 현재 owner·World·thread·membership·차단·원문 공개 범위는 계속 검사한다. SNS 공개 행동 직전의 관계 현재성 검사는 완화하지 않는다.

저장, correction lineage, prior 기억, canonical recall, HotBrief, 관계 정리와 원문 hydration에 같은 검증 문맥을 연결했다. 원문 변경·숨김·비공개나 권한 상실은 전달 증명이 있어도 거절한다. 기존 삭제 원문의 요약 보존 정책은 유지하고 삭제 본문은 재주입하지 않는다.

저장·재검사 자체는 생성·요약·선별 AI를 호출하지 않는다. 정식 기억·근거·출처·접수·복구 이력·색인 자격은 같은 transaction에서 처리하고 색인 provider I/O는 기존 파생 처리 경로에 남긴다. 실제 AI가 기억을 유용하게 활용하는지는 fake 검사로 판정하지 않는다.

## 2. 소유 경로와 구조

| 경로 | 책임 |
| --- | --- |
| Memory contracts/policies | immutable 전달 fragment·관계 준비 기준·source access·검증 port와 순수 판정 |
| `repository/situation_validation.py` | 저장 manifest hash·원래 admission digest·scope/call/성공 결과·entry binding 복원 |
| runtime Chat/SNS situation memory | 최종 payload의 JSON 경로·실제 구간 및 prepared 관계 capture |
| `runtime/memory/situation_sources.py` | canonical 출처·현재 권한·상황 전용 전달 증명·구체 실패 사유 |
| situation apply/reads/packets, runtime episode details | 공통 적용과 저장 이후 lineage·전달 범위 재검증 |
| situation runs/recovery/recovery management | bounded 재검사, scope lock/lease/CAS, 저장 포기·자료 정리·중복 방지 |
| Memory router/schema, runtime memory HTTP | 기존 owner/session/CSRF 및 주입한 runtime validator를 사용하는 네 API |
| Frontend `features/memory` | 실패 목록·전체/개별 재검사·개별 포기·요청 결과/취소/접근성·ko/en |

Backend/Frontend ARCHITECTURE 및 Frontend DESIGN에 책임·UX 계약을 추가했다. 다른 feature 내부 import, test-only 허용 조건, 새 queue나 별도 관찰 DB는 추가하지 않았다.

## 3. 재검사·포기·UI 계약

실패 경험의 설명·사유·시각·안내 아래에 **다시 확인**과 **이 경험 저장 포기**를 제공하고, 실패 개수 옆에 **저장하지 못한 경험 다시 확인**을 제공한다. 대상은 현재 선택한 캐릭터·World이다. 전체 저장 포기는 제공하지 않는다.

목록은 20개 cursor page와 높이 440px 내부 스크롤을 사용한다. 전체 재검사는 화면 밖 후보도 100개/page로 처리하고 고정 cutoff 이후 신규 접수를 제외한다. 개별 재검사는 정확한 receipt sequence/state version을 대상으로 한다. 통과하면 같은 정식 저장 연산으로 applied, 실패하면 구체 사유·revision을 남기고 blocked를 유지한다. 최초 completed run 결과를 덮어쓰지 않는다. 검사가 끝난 부분 성공과 worker error를 구분하며 오류는 같은 요청으로 재시도한다.

포기 Dialog는 취소에 기본 focus를 둔다. owner의 unapplied blocked만 discarded로 종료하며 Memory OFF/닫힌 epoch에서도 정리를 허용한다. 살아 있는 scope lease와 경합하면 거절한다. 중복 요청은 최초 결과를 재사용하고 같은 활동 재접수로 terminal 기록이 부활하지 않는다. queued/error/deferred 후보 포기는 해당 run의 audit·skipped와 함께 원자적으로 처리한다.

포기 접수의 identity/content digest/sequence/version/시각/요청 종료 표식은 보존하고 description/result/manifest 연결을 정리한다. manifest는 공유하지 않을 때만 삭제한다. 원래 채팅·SNS, 다른 정식 기억·공유 manifest·완료 실행은 보존한다.

기존 카드 여백·그림자·semantic token과 공유 Button/Dialog를 재사용했다. 44px 버튼, keyboard/focus/Escape/focus 반환, 진행 공통 잠금, scope 취소·늦은 응답 차단 및 ko/en를 확인했다.

## 4. Forward migration과 호환

| 항목 | 결과 |
| --- | --- |
| SQLite/Alembic | **v32 / 0109**, v31 / 0108에서 정식 forward delta |
| ORM | **169개 table** |
| 신규 table | `memory_situation_recheck_attempts` |
| 변경 table | `memory_situation_runs` work_kind; `memory_situation_receipts` discarded/state_version/포기 시간·요청/nullable manifest |
| v32 schema digest | `c10c4c5989a10b1427af8b1720bde2294734f787ae4d0c7ae0eb154af728f062` |
| 과거 migration/manifest | 동결 유지. v31과 이전 hash 재작성 없음 |

업그레이드는 coordinator의 unpublished staging DB에서 두 변경 table만 재구성한다. 기존 컬럼·키·설정·run·receipt·외래 키·sequence high-water mark를 보존한다. 빈 접수의 sequence 행 부재와 0도 각각 보존한다. filled/empty fixture 및 fresh ORM/Alembic/embedded schema를 대조하고 staging 실패 시 원본 DB·선택 marker hash가 유지되는지 확인한다.

v1 serializer/content identity와 구 pending-save request key를 보존한다. 불충분한 과거 관계·전달 증명은 자동 보강하거나 통과시키지 않는다. 원본 사용자 볼륨의 Bram 접수를 자동 재검사·포기하지 않았다.

## 5. I00–I29 구현 기록

| 단계 | 수행 내용 |
| --- | --- |
| I00 | branch/HEAD/clean 및 workspace/frontend AGENTS·아키텍처·디자인 확인 |
| I01 | 원인 문서·Bram artifact와 최신 capture/source/apply/read 연결 재대조 |
| I02 | file-backed DB로 관계 6→7 및 타인 Inbox 답글 재현 |
| I03 | Chat SocialContext/GraphRecall·SNS refs와 실제 최종 전달 경계 확인 |
| I04 | typed proof·관계 준비 기준·검증 문맥/source access·recovery DTO |
| I05 | 순수 관찰·관계 판정, 현재 권한 검사 유지 |
| I06 | v1 hash·v2 entry/payload binding·검증 revision |
| I07 | 영속 manifest/receipt/result에서 trusted context 복원 |
| I08 | 실제 Chat workflow의 prepared 기준 capture·성공 접수 |
| I09 | 실제 Inbox reply-to-reply 최종 input/result·원자적 접수 |
| I10 | self/Feed 유지, 상황 문맥의 situation_delivered·실제 FK |
| I11 | 과거 관계 기준과 현재 scope/actor/target/block 검사 분리 |
| I12 | 원문·thread·participant·routine·proposal·image·prior 구체 사유 |
| I13 | 신규 저장·재검사 공통 atomic apply |
| I14 | access/prior/correction의 같은 lineage |
| I15 | 실제 recall/HotBrief/review 호출자 및 숨김 뒤 재검증 |
| I16 | 직접 detail도 유효 전달 범위만 hydrate |
| I17 | v32/0109 모델·forward delta·최소 audit/terminal 표식 |
| I18 | blocked 후보·판정·이력·100개 page·cutoff |
| I19 | 기존 consumer blocked_recheck·lease/CAS/rollback |
| I20 | bounded 목록·전체/개별 API·owner/CSRF/version/request identity |
| I21 | manual/scheduled/quit 경합·재시작·terminal 제외 |
| I22 | 개별 discard·OFF/닫힌 epoch·적용 경합 보호 |
| I23 | 상세 정리·shared manifest/다른 기억·재접수 종료 유지 |
| I24 | 기존 Memory UI에 목록·개별 두 버튼·전체 버튼 |
| I25 | ko/en·keyboard/focus/status/44px·responsive |
| I26 | 집중 검사 수행. 전체 회귀 결과 아래 실행 기록에서 확정 |
| I27 | migration/Frontend/구조 수행. 보존 검사 아래에서 확정 |
| I28 | 아키텍처·디자인·보고서 및 계획·원인 상태 동기화 |
| I29 | 이 작업 파일의 local commit. 최종 SHA 아래에서 확정 |

## 6. V01–V29 증거 지도

| 검증 | 증거 |
| --- | --- |
| V01–V03 | 실제 Chat/SNS receipt workflow와 durable reader; prepared 6→7 applied, Feed 없는 Inbox 저장·원래 Feed/self 경로 |
| V04–V06 | 미전달 path/text/raw manifest, ordinal/ID/role/target/range/digest/call, scope/result 변조·foreign HTTP 거절 |
| V07–V08 | prepare/capture 사이 관계 변화, 현재 source·participant·scope·관계 참조 검사·공개 currentness 보존 |
| V09–V10 | body/hidden/private/participant 변화, 삭제 요약·prior/correction/current-version·private 정책 회귀 |
| V11–V13 | actual canonical recall/prior/HotBrief/review, 직접 bounded hydration·selection 이후 변화 거절 |
| V14–V16 | request/receipt/empty/legacy 재전송, 개별/전체 audit·원 completed run 불변, OFF/closed/삭제 부활 방지 |
| V17–V18 | 102개 100+2, cutoff 뒤 신규 제외, idempotency/stale lease/rollback/restart, schedule/quit 경합 |
| V19–V20 | populated·empty v31 forward/fresh parity, 역사/키/FK/sequence, staging failure 원본 보존 및 canonical/index 분리 |
| V21–V22 | ko/en Next/static·request key·scope·worker error·keyboard, 구조/보존·lint/typecheck/build |
| V25–V28 | discard 집계·원문/다른 기억 보존, owner/CSRF/OFF/closed/버전/손상 proof, queued/lease/rollback/replay·shared manifest |
| V29 | 확정 세 버튼 위치·20개 pagination·부분 결과·scope 취소·focus·OFF 권한 분리 |
| V23 | **보류. 실제 AI/임베딩 API 호출 0회.** 실제 검색·답변 도움·언어 품질은 미검증 |
| V24 | **격리 Docker synthetic/fake 64개 통과.** 원본 volume/Compose 서버·실제 AI·설치 앱과 구분 |

## 7. 로컬 실행 기록

- Docker: 64 passed, 3 warnings, 509.81s. `angmoo-backend-dev:latest` Linux/Python 3.13에 현재 app/tests/alembic을 read-only 연결하고 `--network none --rm`, UID/GID 10001, 임시 synthetic DB를 사용했다. 원본 volume·secret을 사용하지 않았고 컨테이너는 제거됐다. 이후 발견한 빈 sequence 경계 수정은 별도 재검증 기록으로 추가한다.
- Browser: 최초 Next/static·ko/en 40 passed, worker-error·관련 부분 결과 12 passed. 총 52회 실행, **고유 44개 case**. 360px/1100px screenshot과 한국어 mobile 실제 판독. 두 번째 실행은 변경된 case와 관련 case만 재검증했다.
- Frontend: lint/typecheck, UI error contracts 53개, UI catalog 16 namespace/2,679 source key, Next build/static build 통과.
- 최종 관찰·복구 집중 검사: 53 passed, 3 warnings, 250.80s. actual Chat/Inbox 접수, 원문·proof 변조와 권한, recall/prior/HotBrief/review, 재검사·포기·audit/rollback/lease·HTTP를 검증했다.
- 현재 head 연계 검사: 86 passed와 fixture 보완 전 빈 migration 4건 및 기존 hosted matrix 1건 실패. 빈 fixture에 공식 schema version table을 포함시킨 후 전체 v32 migration 파일을 다시 실행하여 **8 passed, 53.11s**를 확인했다. 기존 populated/empty의 schema·역사·sequence 단언을 완화하지 않았다.
- canonical 수량 판독: 실제 reader의 synthetic Inbox 답글 한 건을 저장한 결과 **item 1, evidence 2, situation source 2, vector eligibility 1, Feed observation 0, provider call 0**. 새 기억만 검색 자격을 등록하며 별도 저장 AI나 기존 전체 검색 준비는 실행하지 않는다.
- 집중 backend와 전체 회귀·보존 검사의 최종 수치·재검증·commit 결과는 아래 최종 기록에 추가한다.

원자료는 Git에서 제외되는 `artifacts/situation-recovery-validation`에 보관한다. 이 보고서에는 credential·실제 대화 원문을 복사하지 않는다. 로컬 구조 검사 script 실행과 GitHub Actions 등 CI 파이프라인 수행은 별개다.

## 8. 운영·품질 경계

1. 현재 local branch의 구현·build 결과다. 원본 Docker volume·설치 앱을 자동 업그레이드하지 않았다.
2. 기존 blocked 복구 여부는 해당 접수의 원래 증명으로 판정한다. 불충분한 역사 자료를 임의로 만들어 복구하지 않는다.
3. 실제 Bram 유료 재검증·embedding·자연 활동·다음 답변의 도움·설치 앱 USER CHECK는 미수행이다.
4. PR·원격 CI·push·main merge·branch/worktree·배포·설치 앱 변경은 수행하지 않았다.

기존 예외: `test_p8_l_d_requires_real_v3_installer_fixture_in_hosted_matrix`는 `windows_installer_hosted_predecessor_missing:v29`로 실패한다. hosted workflow/PowerShell runner가 v28까지만 등록한 사전 상태이며, 현재 로컬 fixture builder는 모든 readable predecessor v1–v31을 생성·검증한다. 앞선 영속 접수 구현 계획 2.1의 **“CI 파이프라인·일괄 CI 실행·GitHub Actions·CI 설정 변경은 하지 않는다”**를 유지해 `.github/workflows/windows-installer.yml`과 hosted runner 등록은 변경하지 않았다. 이 검사를 삭제·skip하거나 성공으로 바꾸지 않는다. 따라서 전체 suite ALL PASS 또는 실제 설치 업그레이드 완료를 주장하지 않는다.
