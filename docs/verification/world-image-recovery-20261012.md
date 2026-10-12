# 2026-10-12 사용자 프로필·World 이미지 미리보기 복구

## 범위와 작업 상태

- 브랜치: `feat/0.1.0-release-readiness`; 시작 HEAD `ada65f86`, clean.
- 계획: workspace `docs/plan/10-12 사용자 프로필 이미지 업로드 계약과 World 이미지 권한 조회·미리보기 복구 코드 구현 세부 계획.md`, I00–I19.
- 구현과 관련 검증을 완료하고 변경 파일만 로컬 커밋한다. PR/push/원격 CI/main merge는 실행하지 않는다.
- 새 DB 필드/migration/backfill/이미지 재생성/AI 호출은 없다. 원본 사진·프로필·DB·키·volume은 수정하지 않는다. 원본 판독은 Docker canonical pointer를 따른 mode=ro 연결만 사용했다.
- 같은 소유 컴포넌트와 기존 크롭 UI를 재사용한 **LOCAL** 수정이다. 사용자 문구와 ko/en catalog는 변경하지 않았다.

## 최종 구현

1. Worlds API serializer는 `version`, `media_type`, `content_type`, `data_base64`만 전송한다. 공용 Characters 업로더의 filename 계약과 서버 extra=forbid를 유지한다.
2. Worlds service/media가 기존 World read policy와 현재 icon/banner 참조·filename·World 경로·symlink·실파일을 검증한다. 다른 World·이전/임의 파일·없는 파일·접근 거절은 404다.
3. API `/api/v1/worlds/{world_id}/media/{filename}`와 기존 `/media/worlds/{world_id}/{filename}`는 동일 서비스를 사용한다. main이 compatibility router를 조립하고 공통 정적 mount 목록은 확장하지 않는다. 응답은 private/no-store와 nosniff다.
4. 기존 DB URL/파일을 유지하며 Next proxy/static sidecar transport가 World URL을 API로 해석한다. safe URL과 media hook을 통해 인증 fetch→blob 표시를 연결한다. auth/runtime 변경·늦은 결과·unmount에서 기존 결과를 숨기고 revoke한다.
5. 실제 upload 회귀에서 발견한 identity_read의 기존 handle/banner_url 응답 누락도 보완했다. 저장된 banner가 정상 응답 및 reload에 포함된다. schema/저장 구조는 그대로다.

## 검증 결과

중복 재실행 숫자를 합산하지 않는다. 아래는 서로 다른 환경/묶음이며 일부 node는 겹친다.

| 검증 | 결과 | 실제 범위 |
| --- | --- | --- |
| Host Python 핵심 이미지 회귀 | **21 passed** | World 실제 저장 URL/API GET, 픽셀·크기, 공개/private/draft/archived/member 정책, private 전환·탈퇴, 현재/다른/없는 파일, traversal/symlink, 내 프로필 strict schema·owner/version·실제 이미지 GET/reload, 기존 World 업로드/CAS/archive·저장 회귀 |
| 실제 app factory와 기존 owner identity | **4 passed** | full/public factory의 두 실제 route 등록, 기존 owner 변경/reentry·외부 소유자/World 거절 |
| Linux Docker network-none | **22 passed** | 새 World·내 프로필 이미지 및 기존 World mutation 경계. 실제 production app/tests 파일을 read-only mount하며 원본 data volume/키는 mount하지 않음 |
| 기존 World UI 관련 12개 | **12 passed** | ko/en × Next/static의 crop 취소·충돌·최신 version·통신 실패·제거·미저장 입력·runtime 전환. 합성 업로드 응답도 실제 `/media/worlds/...` 형태로 변경 |
| 네 이미지 표시 시험 | **4 passed** | ko/en × Next/static, 390×844, 실제 chooser/crop, 네 필드만 전송, avatar/banner/icon/banner의 768×768 또는 1024×384 decode, 현재 URL·World 초안 유지, reload 및 권한 실패 fallback |
| Node 실제 함수 계약 | **passed** | 추가 metadata가 있는 요청 객체의 네 필드 serializer, Next/static media URL·기존 asset/public/blob, launcher token 및 runtime 전환 |
| 수정 TS ESLint·frontend typecheck | **passed** | 수정 4개 TS 파일 lint, 공통 transport/API 변경의 타입 연결 |
| 필요한 정적 화면 export | **passed** | 동일 static feature/transport를 실제 컴파일하여 브라우저 검증. 일반 Next 전체 build와 모든 화면 시험은 실행하지 않음 |
| frontend 구조·디자인·catalog | **passed** | raw colors 1157/35 files 유지, 두 LOCAL screenshot 호출을 55→57로 명시 등록. canonical PNG 11개/환경/허용 오차 불변; ko/en 16 namespaces/2598 keys parity 유지 |
| backend 새 구조 위반 | **0** | 실제 inventory 1502 modules. 시작 시 남아 있던 4개 원인/6개 메시지와 동일. 전체 구조 PASS로 바꾸거나 예외를 추가하지 않음 |

브라우저 결과 JSON 및 profile-images/world-images PNG는 `artifacts/world-image-recovery-20261012/browser`에 저장한다. 이들은 합성 데이터의 기능/렌더 확인이며 canonical UI-F PNG 또는 실제 모바일·설치 앱 USER CHECK를 대체하지 않는다.

### 개발 중 확인·보완한 사항

- 최초 filename 차단을 해소한 뒤 배너 HTTP 응답의 누락을 실제 저장→조회 회귀에서 발견하여 projection을 수정했다.
- 작은 fixture 원본을 서버가 강제로 확대하지 않는 기존 thumbnail 계약에 맞춰 실제 frontend crop 크기의 fixture를 전송한다. membership fixture는 기존 DB 허용 값 left를 사용한다.
- 새 영어 시험이 서로 다른 namespace의 `Edit My Profile`/`Edit my profile`을 합친 locator를 사용해 실패했다. 실제 Worlds namespace를 따르는 locator로 바로잡고 ko/en을 다시 확인했다. 제품 번역 문구를 시험에 맞춰 바꾸지 않았다.
- 화면의 실제 scroll owner를 따라 profile/World 미리보기 영역을 각각 캡처했다. 전체 document 스크린샷만으로 아래 이미지 표시를 확인했다고 주장하지 않는다.
- 새 테스트의 괄호·VM Event fixture 및 import 타입 경로 오류는 수정 후 재검증했다. 최종 제품 기능 실패로 남겨 두지 않았다.

## 현재 Docker 적용과 원본 자료 판독

기존 `angmoo-backend-1`/`angmoo-frontend-1`에서 새 service/main route/profile projection/frontend serializer/runtime transport 파일의 자동 source sync를 직접 확인했다. 두 컨테이너는 healthy다. 원본 컨테이너를 수동 재생성하거나 volume을 교체하지 않았다.

대상 World는 현재 **draft/private**다. 익명 실제 HTTP GET은 새 World 정책의 `404 world_not_found`로 거절되는 것이 정상이다. 기존 canonical pointer의 현재 DB를 mode=ro로 연결하고 소유자 membership 정책을 사용하는 서비스 읽기로 다음을 확인했다.

- 기존 World icon: image/webp, 768×768, 파일/주소 유지.
- 기존 World banner: image/webp, 1024×384, 파일/주소 유지.

이 확인은 실제 원본 파일·World 접근 서비스의 판독이다. 원본 브라우저의 인증된 GET을 직접 측정한 결과와 구분한다. 브라우저 연결 도구는 초기화 단계에서 `failed to write kernel assets`로 실패했으므로 원본 사용자의 화면은 직접 조작하지 않았다. 사용자 프로필은 이전 422 요청이 저장되지 않았기 때문에 원본을 자동 재업로드하지 않았으며 사용자의 재저장은 USER CHECK로 남는다.

## 단계 ledger

| 단계 | 판정 | 근거 |
| --- | --- | --- |
| I00–I02 | 완료 | 시작 branch/clean·지침·원인 재확인·workspace 계획 저장 |
| I03 | 완료 | 정확한 프로필 API serializer·Node/브라우저 strict payload |
| I04–I06 | 완료 | World read service·API/legacy router·실제 full/public 조립 |
| I07–I08 | 완료 | URL 해석·safe URL·scoped authenticated hook |
| I09–I11 | 완료 | 실제 GET/권한/경로/프로필/version 및 response projection 회귀 |
| I12–I14 | 완료 | 실제 URL fixture·네 이미지·기존 crop/실패/scope·Next/static 계약 |
| I15 | 완료 | 관련 lint/type/export·구조·디자인·번역·새 위반 0 |
| I16 | 완료 | 격리 network-none Linux Docker 22개 통과 |
| I17 | 완료, 관찰 경계 명시 | 자동 source sync/healthy·익명 접근 거절·원본 소유자 서비스 readonly 판독. 원본 브라우저 및 프로필 재업로드는 USER CHECK |
| I18–I19 | 완료 | 결과/architecture/provenance/계획 갱신·선택 stage·로컬 commit, 실제 SHA는 git log로 확인 |

## 보존과 범위 밖

현재 파일을 공개 정적 mount로 열거나 schema의 추가 필드 검사를 완화하지 않았다. World/사용자 사진을 이동·삭제·재생성하지 않았고 기능 검증은 합성 DB/이미지를 사용했다. 기존 backend 구조 4건, World 추천 준비 종료의 오래된 시험, 실제 AI 품질, 설치 앱/실제 모바일은 이번 완료 결과와 별개다.
